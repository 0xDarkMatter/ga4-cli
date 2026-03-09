---
name: ga4-health
description: "GA4 property health diagnostics, scoring, and site spider. Triggers: health check, site audit, tag coverage, ga4 score, diagnostics, spider."
version: 1.0.0
category: domain
tool: ga4
requires:
  bins: ["ga4"]
  skills: ["ga4-ops"]
related-skills: ["ga4-access", "ga4-reporting"]
allowed-tools: "Read Bash Grep"
---

# GA4 Health Diagnostics

Property health scoring, tag coverage audits, and multi-property scanning.

## Key Commands

```bash
ga4 health check <property-id>                 # Full diagnostic report
ga4 health check <property-id> --json          # JSON output for piping
ga4 health access <property-id>                # User access audit only
ga4 health tracking <property-id>              # Data quality checks only
ga4 health summary <property-id>               # One-line score + grade

ga4 health report <property-id>                # Formatted report to stdout
ga4 health report <property-id> --out report.md  # Save to file
```

## Score Interpretation

| Grade | Score | Meaning |
|-------|-------|---------|
| A | 90–100 | Healthy — minor or no issues |
| B | 75–89 | Good — a few non-critical issues |
| C | 60–74 | Fair — some problems worth addressing |
| D | 40–59 | Poor — significant issues affecting data quality |
| F | 0–39 | Critical — tracking likely broken or severely compromised |

```bash
# Get just the score and grade
ga4 health check <property-id> --json | jq '.data | {score, grade}'
```

## All 24 Health Checks

### Tracking (data quality)

| Check | Detects |
|-------|---------|
| `data_recency` | Last event more than 48 hours ago — tracking may be broken |
| `realtime` | No realtime events in last 30 minutes |
| `sessions` | Session count zero or anomalously low |
| `bounce_rate` | Bounce rate >95% (likely misconfigured) or 0% (likely double-tracking) |
| `not_set` | High percentage of `(not set)` dimension values |
| `hostname` | Unexpected hostnames sending data (test/staging traffic in prod) |
| `event_volume` | Event count drops >50% week-over-week |
| `conversion_tags` | Key conversion events missing or zero for 7+ days |

### Access (security and governance)

| Check | Detects |
|-------|---------|
| `user_count` | Unusually high total user count (>50) |
| `admin_count` | More than 3 users with Admin role |
| `external_domains` | Access granted to domains outside your org |
| `roles` | Users with overly broad roles for their function |
| `stale_users` | Users who haven't accessed the property in 90+ days |
| `service_accounts` | Service account emails with Admin role |

### Config (property configuration)

| Check | Detects |
|-------|---------|
| `property_config` | Missing industry category, time zone, or currency |
| `data_retention` | Retention set to default 2 months (data loss risk) |
| `enhanced_measurement` | Enhanced measurement disabled (missing scroll, file, outbound events) |
| `custom_dimensions` | No custom dimensions registered |
| `cross_domain` | Cross-domain tracking not configured for multi-domain sites |
| `google_signals` | Google Signals disabled (affects demographic reporting) |

### Tag (implementation)

| Check | Detects |
|-------|---------|
| `gtm_present` | No GTM container detected on the site |
| `gtag_direct` | gtag.js loaded directly alongside GTM (potential double-counting) |
| `sgtm` | Server-side GTM not detected (client-side only) |
| `tag_coverage` | Pages without GA4 tag (based on spider sample) |

## Understanding the Report

```
Property: My Site (123456789)
Score: 78/100  Grade: B
Checks: 20 pass / 3 warn / 1 fail

FAIL  data_retention     Retention is 2 months (default). Set to 14 months.
WARN  admin_count        5 Admin users (threshold: 3)
WARN  enhanced_measurement  Page_view only. Scroll and outbound not active.
WARN  sgtm               Server-side GTM not detected.
```

- **FAIL**: Actively hurting data quality or security. Fix promptly.
- **WARN**: Non-critical but worth addressing. May affect reporting accuracy.
- **PASS**: Check completed successfully, no issues found.

## Site Spider

The spider samples pages from your property to verify tag presence and detect implementation issues.

```bash
# Spider runs automatically as part of health check
ga4 health check <property-id>

# Skip spider (faster, no network requests)
ga4 health check <property-id> --spider 0

# Force fresh spider results (bypass cache)
ga4 health check <property-id> --no-cache
```

What the spider checks on each page:
- GTM container present and matching expected container ID
- gtag.js loaded directly (potential double-counting with GTM)
- Server-side GTM (sGTM) endpoint detected
- Multiple GA4 measurement IDs firing (double-tagging)
- Tag coverage: pages without any GA4 measurement

Spider samples up to 20 pages from the sitemap or crawl. Coverage percentage = pages with valid GA4 tag / total pages sampled.

## Multi-Property Scanning

```bash
# Scan all accessible properties (3 concurrent workers)
ga4 scan all
ga4 scan all --workers 5
ga4 scan all --account <account-id>           # Limit to one account

# Show only failing/warning properties
ga4 scan issues
ga4 scan issues --json

# Formatted summary report
ga4 scan report

# Permission matrix across all properties
ga4 scan permissions
ga4 scan permissions --json | jq '.data.properties[] | select(.admin_count > 3)'
```

`ga4 scan all` runs health checks concurrently. Default: 3 workers. Increase for large account portfolios; stay below 10 to avoid quota exhaustion.

## jq Patterns for Health Data

```bash
# Properties scoring below 75 (grade C or worse)
ga4 scan all --json | jq '.data.properties[] | select(.score < 75) | {name: .property_name, score, grade}'

# All failing checks across a property
ga4 health check <property-id> --json | jq '.data.checks[] | select(.status == "fail")'

# All warnings
ga4 health check <property-id> --json | jq '.data.checks[] | select(.status == "warn") | .name'

# Average score across portfolio
ga4 scan all --json | jq '.data.overall.avg_score'

# Properties with external domain access
ga4 scan all --json | jq '.data.properties[] | select(.checks[] | select(.name == "external_domains" and .status != "pass")) | .property_name'

# Score summary table
ga4 scan all --json | jq -r '.data.properties[] | [.property_name, .score, .grade] | @tsv'
```

## Common Issues and Fixes

| Issue | Check | Fix |
|-------|-------|-----|
| Retention at 2 months | `data_retention` | Admin > Data Settings > Data Retention → set to 14 months |
| Enhanced measurement off | `enhanced_measurement` | Admin > Data Streams > your stream → toggle enhanced measurement on |
| All-Admin roles | `admin_count` / `roles` | Downgrade non-owners to Analyst or Editor |
| Double-tagging detected | `gtag_direct` | Remove direct gtag.js; fire GA4 through GTM only |
| `(not set)` values high | `not_set` | Audit event parameters; check referral exclusions |
| No realtime events | `realtime` | Verify tag fires in GTM Preview; check measurement ID |
| Stale users | `stale_users` | Run `ga4 health access <id>` and remove inactive accounts |
| Tag coverage gaps | `tag_coverage` | Review spider output; check pages excluded from GTM trigger |

## Pipe Patterns

| Chain | Command | Use Case |
|-------|---------|----------|
| → fslack | `ga4 scan issues --json \| fslack messages send --channel analytics` | Alert team on failing properties |
| → jq | `ga4 health check <id> --json \| jq '.data.checks[] \| select(.status == "fail")'` | Extract failures for ticket creation |
| → file | `ga4 health report <id> --out /tmp/report.md` | Save report for sharing |
| → scan | `ga4 scan all --json \| jq -r '.data.properties[] \| select(.grade == "F") \| .id'` | Get IDs of critical properties |
