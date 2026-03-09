---
name: ga4-reporting
description: "GA4 reporting, traffic analysis, and engagement metrics. Triggers: ga4 report, traffic data, sessions, bounce rate, engagement, pageviews, custom dimensions, analytics data."
version: 1.0.0
category: domain
tool: ga4
requires:
  bins: ["ga4"]
  skills: ["ga4-ops"]
related-skills: ["ga4-health", "gsc-analytics"]
allowed-tools: "Read Bash Grep"
---

# GA4 Reporting

Domain skill for running GA4 reports, interpreting traffic data, and extracting engagement metrics.

## Key Commands

```bash
# Standard report
ga4 reports run <property_id> --dimensions date --metrics sessions,bounceRate --from 7daysAgo --json

# Realtime report
ga4 reports realtime <property_id> --dimensions country --metrics activeUsers --json

# Discover available dimensions and metrics
ga4 dimensions list <property_id> --json
ga4 metrics list <property_id> --json

# Get details for a specific dimension or metric
ga4 dimensions get <property_id> date --json
ga4 metrics get <property_id> sessions --json
```

## Date Ranges

| Expression | Meaning |
|------------|---------|
| `today` | Current day |
| `yesterday` | Previous day |
| `7daysAgo` | Last 7 days |
| `30daysAgo` | Last 30 days |
| `90daysAgo` | Last 90 days |
| `2026-01-01` | Specific date (YYYY-MM-DD) |

Default range is `--from 30daysAgo --to today`. The API accepts both ISO dates and relative expressions.

## Report Recipes

### 7-Day Traffic by Date

```bash
ga4 reports run <property_id> \
  --dimensions date \
  --metrics sessions,activeUsers,bounceRate \
  --from 7daysAgo --to today \
  --order-by date --asc \
  --json
```

### Traffic Sources Breakdown

```bash
ga4 reports run <property_id> \
  --dimensions sessionDefaultChannelGroup \
  --metrics sessions,newUsers,bounceRate \
  --from 30daysAgo \
  --json
```

### Top Pages by Pageviews

```bash
ga4 reports run <property_id> \
  --dimensions pagePath,pageTitle \
  --metrics screenPageViews,averageSessionDuration \
  --from 30daysAgo \
  --order-by screenPageViews \
  --limit 50 \
  --json
```

### Channel Grouping Analysis

```bash
ga4 reports run <property_id> \
  --dimensions sessionDefaultChannelGroup,sessionSourceMedium \
  --metrics sessions,newUsers,engagementRate \
  --from 30daysAgo \
  --json
```

### Geographic Distribution

```bash
ga4 reports run <property_id> \
  --dimensions country,city \
  --metrics activeUsers,sessions \
  --from 30daysAgo \
  --order-by sessions \
  --json
```

### Device and Platform Breakdown

```bash
ga4 reports run <property_id> \
  --dimensions deviceCategory,operatingSystem \
  --metrics sessions,bounceRate,averageSessionDuration \
  --from 30daysAgo \
  --json
```

### Realtime Active Users by Country

```bash
ga4 reports realtime <property_id> \
  --dimensions country,city \
  --metrics activeUsers \
  --json
```

## Output Fields

Report data is returned under `data` with these fields:

| Field | Type | Description |
|-------|------|-------------|
| `rows` | array | Data rows, each keyed by dimension/metric name |
| `dimension_headers` | array | Ordered list of dimension names |
| `metric_headers` | array | Ordered list of metric names |
| `row_count` | int | Total rows available (may exceed `rows` if `--limit` applies) |

Each row is a flat dict: `{"date": "20260101", "sessions": "1234", "bounceRate": "0.42"}`.

Note: all metric values are returned as strings, even numeric ones. Cast with `jq` as needed.

## jq Patterns

```bash
# Extract rows as table
ga4 reports run <property_id> --json | jq '.data.rows'

# Sum a metric across all rows
ga4 reports run <property_id> -d sessionDefaultChannelGroup -m sessions --json \
  | jq '[.data.rows[].sessions | tonumber] | add'

# Top 3 channels by sessions
ga4 reports run <property_id> -d sessionDefaultChannelGroup -m sessions --json \
  | jq '[.data.rows[] | {channel: .sessionDefaultChannelGroup, sessions: (.sessions | tonumber)}] | sort_by(-.sessions) | .[0:3]'

# Filter rows where bounce rate > 70%
ga4 reports run <property_id> -d pagePath -m sessions,bounceRate --json \
  | jq '.data.rows[] | select((.bounceRate | tonumber) > 0.7)'

# Export as CSV (header + rows)
ga4 reports run <property_id> -d date -m sessions,activeUsers --json | jq -r '
  (.data.dimension_headers + .data.metric_headers | @csv),
  (.data.rows[] | [.date, .sessions, .activeUsers] | @csv)
'
```

## Custom Dimensions

Custom dimensions are property-specific and appear alongside standard dimensions in `ga4 dimensions list`. They are prefixed with `customEvent:` or `customUser:` in the API name.

```bash
# List all dimensions, filter to custom only
ga4 dimensions list <property_id> --json \
  | jq '.data[] | select(.api_name | startswith("custom"))'

# Use a custom dimension in a report
ga4 reports run <property_id> \
  --dimensions customEvent:plan_type \
  --metrics sessions \
  --from 30daysAgo \
  --json
```

## Gotchas

**Date format in output:** Dates come back as `YYYYMMDD` (e.g., `20260101`), not `YYYY-MM-DD`. Convert with `jq 'gsub("(?<y>[0-9]{4})(?<m>[0-9]{2})(?<d>[0-9]{2})"; "\(.y)-\(.m)-\(.d)")'` or handle in downstream processing.

**`(not set)` values:** Dimensions like `city`, `pagePath`, and custom dimensions often include `(not set)` rows when data is missing. Filter them out with `jq '.data.rows[] | select(.city != "(not set)")'`.

**Sampling:** Large date ranges on high-traffic properties may return sampled data. Use shorter ranges or add `--limit 100000` to force unsampled results where possible.

**Data processing lag:** GA4 data is typically 24–48 hours behind. Avoid `today` for accuracy-sensitive reports; use `yesterday` or earlier.

**Realtime limitations:** Realtime reports only support a subset of dimensions and metrics. Check `ga4 dimensions list` — realtime-compatible ones are flagged in the API metadata.

**row_count vs rows length:** `row_count` is the total available rows; `rows` is capped by `--limit` (default 100). Always check `row_count` to know if results are truncated.

## Pipe Patterns

| Chain | Command | Use Case |
|-------|---------|----------|
| → jq | `ga4 reports run <id> --json \| jq '.data.rows'` | Extract and reshape |
| → fslack | `ga4 reports run <id> --json \| fslack messages send --channel analytics` | Weekly traffic alerts |
| → gsc | Compare GA4 sessions with GSC clicks on same date range | SEO correlation |
