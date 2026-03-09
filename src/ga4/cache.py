"""JSON file cache for GA4 API responses with TTL support."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional


DEFAULT_CACHE_DIR = Path(".cache/ga4")

# TTL constants (seconds)
TTL_SHORT = 3600        # 1 hour - for data that changes daily
TTL_MEDIUM = 86400      # 24 hours - for admin config data
TTL_LONG = 604800       # 7 days - for metadata that rarely changes


class Cache:
    """Simple JSON file cache with TTL."""

    def __init__(self, cache_dir: Path | str = DEFAULT_CACHE_DIR):
        self.cache_dir = Path(cache_dir)

    def _key_path(self, namespace: str, key: str) -> Path:
        """Generate file path for a cache entry."""
        # Use hash for safe filenames
        key_hash = hashlib.md5(key.encode()).hexdigest()[:12]
        safe_key = key.replace("/", "_").replace(":", "_")[:50]
        return self.cache_dir / namespace / f"{safe_key}_{key_hash}.json"

    def get(self, namespace: str, key: str, ttl: int = TTL_MEDIUM) -> Optional[Any]:
        """Get cached value if it exists and hasn't expired."""
        path = self._key_path(namespace, key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - data.get("cached_at", 0) > ttl:
                # Expired
                path.unlink(missing_ok=True)
                return None
            return data.get("value")
        except (json.JSONDecodeError, OSError):
            return None

    def set(self, namespace: str, key: str, value: Any) -> None:
        """Store a value in the cache."""
        path = self._key_path(namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "cached_at": time.time(),
            "key": key,
            "value": value,
        }
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def clear(self, namespace: str | None = None) -> int:
        """Clear cache entries. If namespace is None, clear all."""
        count = 0
        if namespace:
            ns_dir = self.cache_dir / namespace
            if ns_dir.exists():
                for f in ns_dir.glob("*.json"):
                    f.unlink()
                    count += 1
        else:
            if self.cache_dir.exists():
                for f in self.cache_dir.rglob("*.json"):
                    f.unlink()
                    count += 1
        return count

    def clear_property(self, property_id: str) -> int:
        """Clear all cache entries for a specific property."""
        count = 0
        if self.cache_dir.exists():
            for f in self.cache_dir.rglob(f"*{property_id}*.json"):
                f.unlink()
                count += 1
        return count

    def status(self) -> dict:
        """Return cache statistics."""
        if not self.cache_dir.exists():
            return {"entries": 0, "namespaces": [], "size_bytes": 0}

        namespaces: dict[str, int] = {}
        total_size = 0
        for f in self.cache_dir.rglob("*.json"):
            ns = f.parent.name
            namespaces[ns] = namespaces.get(ns, 0) + 1
            try:
                total_size += f.stat().st_size
            except OSError:
                pass

        return {
            "entries": sum(namespaces.values()),
            "namespaces": [{"name": k, "count": v} for k, v in sorted(namespaces.items())],
            "size_bytes": total_size,
            "cache_dir": str(self.cache_dir),
        }
