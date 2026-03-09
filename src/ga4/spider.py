"""Site spider for checking GA4/GTM tag implementation across pages."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# GTM container loaded from googletagmanager.com
GTM_PATTERN = re.compile(
    r"googletagmanager\.com/gtm\.js\?id=(GTM-[A-Z0-9]+)",
    re.IGNORECASE,
)

# GTM noscript iframe (belt-and-braces: also detects noScript iframe variant)
GTM_NOSCRIPT_PATTERN = re.compile(
    r"googletagmanager\.com/ns\.html\?id=(GTM-[A-Z0-9]+)",
    re.IGNORECASE,
)

# GTM script loaded from a first-party / server-side domain
GTM_SGTM_PATTERN = re.compile(
    r'(?:src|href)=["\']https?://(?!(?:www\.)?googletagmanager\.com)'
    r'([^"\']+/gtm\.js\?id=(GTM-[A-Z0-9]+))',
    re.IGNORECASE,
)

# gtag.js with measurement ID
GTAG_PATTERN = re.compile(
    r"googletagmanager\.com/gtag/js\?id=(G-[A-Z0-9]+)",
    re.IGNORECASE,
)

# gtag('config', 'G-...') or gtag("config", "G-...")
GTAG_CONFIG_PATTERN = re.compile(
    r"gtag\s*\(\s*['\"]config['\"]\s*,\s*['\"](G-[A-Z0-9]+)['\"]",
    re.IGNORECASE,
)

# Any standalone G- measurement ID in page source
MEASUREMENT_ID_PATTERN = re.compile(r"\b(G-[A-Z0-9]{6,10})\b")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_AGENT = "Mozilla/5.0 (compatible; GA4HealthCheck/1.0)"

# File extensions that are never HTML pages worth crawling
_NON_PAGE_EXTENSIONS = frozenset(
    {
        ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg",
        ".ico", ".css", ".js", ".mjs", ".ts", ".map", ".woff", ".woff2",
        ".ttf", ".eot", ".otf", ".mp3", ".mp4", ".webm", ".ogg", ".wav",
        ".zip", ".gz", ".tar", ".rar", ".7z", ".exe", ".dmg", ".pkg",
        ".xml", ".rss", ".atom", ".json", ".yaml", ".yml", ".txt",
    }
)

# URL schemes we don't want to follow
_SKIP_SCHEMES = frozenset({"mailto", "tel", "javascript", "data", "ftp"})


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PageTagInfo:
    """Tag implementation info for a single page."""

    url: str
    status_code: int = 0
    error: str = ""
    gtm_containers: list[str] = field(default_factory=list)  # GTM-XXXXXX IDs found
    gtag_ids: list[str] = field(default_factory=list)        # G-XXXXXXX measurement IDs
    ga4_config_calls: int = 0   # Number of gtag('config', 'G-...') calls
    has_gtm: bool = False
    has_gtag: bool = False
    has_server_side_gtm: bool = False  # GTM loaded from first-party domain
    script_count: int = 0              # Total <script> tags


@dataclass
class SpiderResult:
    """Aggregated spider results across all crawled pages."""

    site_url: str
    pages_crawled: int = 0
    pages_with_ga4: int = 0
    pages_without_ga4: int = 0
    pages_with_gtm: int = 0
    pages_with_errors: int = 0
    gtm_containers: list[str] = field(default_factory=list)   # Unique GTM IDs found
    measurement_ids: list[str] = field(default_factory=list)  # Unique G- IDs found
    has_server_side_gtm: bool = False
    double_tagging_pages: list[str] = field(default_factory=list)  # Multiple GA4 impls
    untagged_pages: list[str] = field(default_factory=list)        # Missing GA4
    page_results: list[PageTagInfo] = field(default_factory=list)


# ---------------------------------------------------------------------------
# HTML link extractor (HTMLParser subclass — no regex on href)
# ---------------------------------------------------------------------------


class _LinkExtractor(HTMLParser):
    """Collect href values from <a> tags."""

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        for name, value in attrs:
            if name == "href" and value:
                self.hrefs.append(value)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        # self-closing tags like <a /> (rare, but handle anyway)
        self.handle_starttag(tag, attrs)


class _ScriptCounter(HTMLParser):
    """Count <script> tags in an HTML document."""

    def __init__(self) -> None:
        super().__init__()
        self.count: int = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            self.count += 1

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag == "script":
            self.count += 1


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_url(url: str) -> str:
    """Ensure URL has https scheme and no trailing slash on the root."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    # Rebuild without fragment; keep path as-is
    return parsed._replace(fragment="").geturl()


def _url_path_depth(url: str) -> int:
    """Return number of path segments — used to prioritise shallow pages."""
    path = urlparse(url).path.strip("/")
    if not path:
        return 0
    return len(path.split("/"))


def _extract_links(html: str, base_url: str) -> list[str]:
    """Parse *html* and return internal links relative to *base_url*.

    Uses :class:`_LinkExtractor` (HTMLParser subclass) — never regex on href.
    Filters:
    - Same hostname only
    - Excludes non-page extensions (.pdf, .jpg, .css, .js, …)
    - Excludes anchors-only, mailto:, tel:, javascript: schemes
    - Excludes URLs with query strings (usually dynamic/duplicate content)
    - Strips fragments; deduplicates; returns absolute URLs.
    """
    base_parsed = urlparse(base_url)
    base_host = base_parsed.netloc.lower()

    extractor = _LinkExtractor()
    try:
        extractor.feed(html)
    except Exception:
        # HTMLParser can raise on malformed input; return what we have so far
        pass

    seen: set[str] = set()
    results: list[str] = []

    for href in extractor.hrefs:
        href = href.strip()
        if not href:
            continue

        # Skip known non-HTTP schemes
        lower = href.lower()
        for scheme in _SKIP_SCHEMES:
            if lower.startswith(scheme + ":"):
                break
        else:
            # Pure fragments only — skip
            if href.startswith("#"):
                continue

            # Resolve to absolute URL
            absolute = urljoin(base_url, href)
            parsed = urlparse(absolute)

            # Must be http(s)
            if parsed.scheme not in ("http", "https"):
                continue

            # Same domain only (www.example.com == example.com treated as same host)
            link_host = parsed.netloc.lower()
            if link_host != base_host:
                # Also allow www <-> non-www variant of the same root
                base_root = base_host.lstrip("www.")
                link_root = link_host.lstrip("www.")
                if base_root != link_root:
                    continue

            # Exclude URLs with query strings (usually dynamic content)
            if parsed.query:
                continue

            # Exclude non-page file extensions
            path_lower = parsed.path.lower()
            # Check the file extension of the last path segment
            last_segment = path_lower.rstrip("/").rsplit("/", 1)[-1]
            if "." in last_segment:
                ext = "." + last_segment.rsplit(".", 1)[-1]
                if ext in _NON_PAGE_EXTENSIONS:
                    continue

            # Strip fragment, normalise
            clean = parsed._replace(fragment="").geturl()

            if clean not in seen:
                seen.add(clean)
                results.append(clean)

    return results


def _analyze_page(html: str, page_url: str) -> PageTagInfo:
    """Analyse *html* source and return a populated :class:`PageTagInfo`.

    Detects:
    - GTM containers (googletagmanager.com and server-side variants)
    - gtag.js measurement IDs
    - gtag('config', 'G-...') calls
    - Double-tagging indicators
    """
    info = PageTagInfo(url=page_url)

    # --- Count script tags ---
    script_counter = _ScriptCounter()
    try:
        script_counter.feed(html)
    except Exception:
        pass
    info.script_count = script_counter.count

    # --- GTM via googletagmanager.com ---
    gtm_ids: list[str] = GTM_PATTERN.findall(html)
    # Also capture GTM IDs from noscript iframes
    gtm_ids += GTM_NOSCRIPT_PATTERN.findall(html)
    # Deduplicate, preserve order
    seen_gtm: set[str] = set()
    for gid in gtm_ids:
        uid = gid.upper()
        if uid not in seen_gtm:
            seen_gtm.add(uid)
            info.gtm_containers.append(uid)

    info.has_gtm = bool(info.gtm_containers)

    # --- Server-side GTM (first-party domain) ---
    sgtm_matches = GTM_SGTM_PATTERN.findall(html)
    if sgtm_matches:
        info.has_server_side_gtm = True
        # Also capture those container IDs
        for _full_path, container_id in sgtm_matches:
            uid = container_id.upper()
            if uid not in seen_gtm:
                seen_gtm.add(uid)
                info.gtm_containers.append(uid)
        info.has_gtm = True  # server-side GTM still means GTM is present

    # --- gtag.js ---
    gtag_script_ids: list[str] = GTAG_PATTERN.findall(html)
    # --- gtag('config', ...) calls ---
    config_ids: list[str] = GTAG_CONFIG_PATTERN.findall(html)
    info.ga4_config_calls = len(config_ids)

    # Collect all G- IDs (from gtag.js src + config calls + bare occurrences)
    all_gids_raw: list[str] = gtag_script_ids + config_ids
    # Also sweep for any measurement IDs we may have missed
    all_gids_raw += MEASUREMENT_ID_PATTERN.findall(html)

    seen_gids: set[str] = set()
    for gid in all_gids_raw:
        uid = gid.upper()
        if uid not in seen_gids:
            seen_gids.add(uid)
            info.gtag_ids.append(uid)

    info.has_gtag = bool(gtag_script_ids) or bool(config_ids)

    return info


def _page_has_ga4(info: PageTagInfo) -> bool:
    """Return True if a page has any form of GA4 tracking."""
    return info.has_gtm or info.has_gtag or bool(info.gtag_ids)


def _page_has_double_tagging(info: PageTagInfo) -> bool:
    """Return True if a page appears to have multiple GA4 implementations.

    Indicators:
    - More than one distinct G- measurement ID
    - Both GTM and a standalone gtag.js pointing to the same property
      (GTM fires its own gtag, so adding an extra gtag.js is redundant)
    """
    if len(info.gtag_ids) > 1:
        return True
    if info.has_gtm and info.has_gtag:
        return True
    return False


# ---------------------------------------------------------------------------
# Main async spider
# ---------------------------------------------------------------------------


async def spider_site(
    site_url: str,
    max_pages: int = 20,
    timeout: int = 10,
    cache=None,
) -> SpiderResult:
    """Crawl *site_url* and return :class:`SpiderResult` with GA4 coverage info.

    Algorithm
    ---------
    1. Normalise *site_url* (ensure https://, strip trailing slash).
    2. Fetch homepage; extract internal links from the same response body.
    3. Sort discovered links by path depth (shallower = more canonical).
    4. Crawl up to *max_pages* pages concurrently (``asyncio.Semaphore(5)``).
    5. Aggregate findings into a :class:`SpiderResult`.

    Parameters
    ----------
    site_url:
        Root URL of the site to crawl (e.g. ``https://example.com``).
    max_pages:
        Maximum number of pages to crawl (homepage counts as one). Default 20.
    timeout:
        Per-request timeout in seconds. Default 10.
    cache:
        Optional :class:`~ga4.cache.Cache` instance.  When provided, results
        are stored in the ``spider`` namespace and served from cache on
        subsequent calls within the TTL window (24 hours by default).
    """
    site_url = _normalize_url(site_url)
    # Strip trailing slash on the root so the homepage URL is canonical
    if site_url.endswith("/") and urlparse(site_url).path == "/":
        site_url = site_url.rstrip("/")

    # Check cache before hitting the network
    if cache is not None:
        from .cache import TTL_MEDIUM
        cache_key = f"spider_{site_url}"
        cached = cache.get("spider", cache_key, TTL_MEDIUM)
        if cached is not None:
            # Reconstruct SpiderResult from the cached dict
            page_results = [PageTagInfo(**p) for p in cached.get("page_results", [])]
            return SpiderResult(
                site_url=cached.get("site_url", site_url),
                pages_crawled=cached.get("pages_crawled", 0),
                pages_with_ga4=cached.get("pages_with_ga4", 0),
                pages_without_ga4=cached.get("pages_without_ga4", 0),
                pages_with_gtm=cached.get("pages_with_gtm", 0),
                pages_with_errors=cached.get("pages_with_errors", 0),
                gtm_containers=cached.get("gtm_containers", []),
                measurement_ids=cached.get("measurement_ids", []),
                has_server_side_gtm=cached.get("has_server_side_gtm", False),
                double_tagging_pages=cached.get("double_tagging_pages", []),
                untagged_pages=cached.get("untagged_pages", []),
                page_results=page_results,
            )

    result = SpiderResult(site_url=site_url)

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
    }

    semaphore = asyncio.Semaphore(5)

    async def _fetch_page(
        client: httpx.AsyncClient,
        url: str,
    ) -> tuple[PageTagInfo, str | None]:
        """Fetch *url*, analyse tags, and return ``(PageTagInfo, raw_html | None)``.

        The raw HTML is returned so the caller can extract links without a
        second network round-trip.
        """
        info = PageTagInfo(url=url)
        raw_html: str | None = None
        async with semaphore:
            try:
                response = await client.get(url, headers=headers, follow_redirects=True)
                info.status_code = response.status_code
                if response.status_code == 200:
                    ct = response.headers.get("content-type", "")
                    if "html" in ct or not ct:
                        raw_html = response.text
                        analysed = _analyze_page(raw_html, url)
                        info.gtm_containers = analysed.gtm_containers
                        info.gtag_ids = analysed.gtag_ids
                        info.ga4_config_calls = analysed.ga4_config_calls
                        info.has_gtm = analysed.has_gtm
                        info.has_gtag = analysed.has_gtag
                        info.has_server_side_gtm = analysed.has_server_side_gtm
                        info.script_count = analysed.script_count
                    else:
                        info.error = f"Non-HTML content-type: {ct}"
            except httpx.TimeoutException:
                info.error = "Timeout"
            except httpx.TooManyRedirects:
                info.error = "Too many redirects"
            except httpx.RequestError as exc:
                info.error = f"Request error: {type(exc).__name__}"
            except Exception as exc:  # noqa: BLE001
                info.error = f"Unexpected error: {type(exc).__name__}: {exc}"
        return info, raw_html

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        follow_redirects=True,
    ) as client:
        # ---- Step 1: fetch homepage (reuse body for link extraction) --------
        homepage_info, homepage_html = await _fetch_page(client, site_url)
        result.page_results.append(homepage_info)

        # ---- Step 2: extract links from the already-fetched homepage body ---
        discovered_links: list[str] = []
        if homepage_html is not None:
            discovered_links = _extract_links(homepage_html, site_url)

        # Sort by path depth (shallower first = more important pages)
        discovered_links.sort(key=_url_path_depth)

        # Exclude homepage itself (already crawled) and limit
        pages_to_crawl = [
            url
            for url in discovered_links
            if url.rstrip("/") != site_url.rstrip("/")
        ][: max_pages - 1]  # -1 because homepage already counted

        # ---- Step 3: crawl discovered pages concurrently -------------------
        if pages_to_crawl:
            tasks = [_fetch_page(client, url) for url in pages_to_crawl]
            gathered = await asyncio.gather(*tasks)
            result.page_results.extend(info for info, _html in gathered)

    # ---- Step 4: aggregate results -----------------------------------------
    all_gtm_ids: set[str] = set()
    all_gids: set[str] = set()

    for info in result.page_results:
        result.pages_crawled += 1

        if info.error:
            result.pages_with_errors += 1

        if info.has_gtm:
            result.pages_with_gtm += 1

        if info.has_server_side_gtm:
            result.has_server_side_gtm = True

        all_gtm_ids.update(info.gtm_containers)
        all_gids.update(info.gtag_ids)

        if _page_has_ga4(info):
            result.pages_with_ga4 += 1
            if _page_has_double_tagging(info):
                result.double_tagging_pages.append(info.url)
        else:
            result.pages_without_ga4 += 1
            if not info.error:
                # Only flag as untagged when we successfully fetched the page
                result.untagged_pages.append(info.url)

    # Stable sorted lists for deterministic output
    result.gtm_containers = sorted(all_gtm_ids)
    result.measurement_ids = sorted(all_gids)

    # Store in cache for future calls
    if cache is not None:
        from .cache import TTL_MEDIUM
        cache_key = f"spider_{site_url}"
        cache.set("spider", cache_key, {
            "site_url": result.site_url,
            "pages_crawled": result.pages_crawled,
            "pages_with_ga4": result.pages_with_ga4,
            "pages_without_ga4": result.pages_without_ga4,
            "pages_with_gtm": result.pages_with_gtm,
            "pages_with_errors": result.pages_with_errors,
            "gtm_containers": result.gtm_containers,
            "measurement_ids": result.measurement_ids,
            "has_server_side_gtm": result.has_server_side_gtm,
            "double_tagging_pages": result.double_tagging_pages,
            "untagged_pages": result.untagged_pages,
            "page_results": [
                {
                    "url": p.url,
                    "status_code": p.status_code,
                    "error": p.error,
                    "gtm_containers": p.gtm_containers,
                    "gtag_ids": p.gtag_ids,
                    "ga4_config_calls": p.ga4_config_calls,
                    "has_gtm": p.has_gtm,
                    "has_gtag": p.has_gtag,
                    "has_server_side_gtm": p.has_server_side_gtm,
                    "script_count": p.script_count,
                }
                for p in result.page_results
            ],
        })

    return result
