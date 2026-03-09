---
name: ga4-recipe-site-audit
description: "Full GA4 site audit with health check, tag spider, and markdown report. Triggers: site audit, audit property, check site, ga4 audit, full diagnostic."
version: 1.0.0
category: recipe
tool: ga4
requires:
  bins: ["ga4", "jq"]
  skills: ["ga4-ops", "ga4-health"]
allowed-tools: "Read Bash Grep"
---

# GA4 Site Audit

A complete property diagnostic: 24 health checks across tracking, config, and
access categories, plus a site spider across up to 20 pages verifying GTM/gtag
presence. Output is a markdown report at `output/{domain}-{property_id}/report.md`.

## What This Produces

A markdown report containing: overall health score and grade, pass/warn/fail
counts per category, per-check detail with messages, site tag coverage per URL,
raw traffic and user-access tables.

## Prerequisites

- [ ] Authenticated: `ga4 auth status`
- [ ] Property ID known — see discovery commands below

### Discover Property ID

```bash
# List all accessible properties
ga4 properties list --json | jq '.data[] | {id, name}'

# Filter to a specific account
ga4 properties list --account <account_id> --json | jq '.data[] | {id, name}'
```

## Steps

### 1. Generate the Report

```bash
ga4 health report <property_id>
```

Output lands at `output/{domain}-{property_id}/report.md`. The command prints
the path on completion and shows the health table in the terminal.

### 2. Open and Review the Report

```bash
# Path printed by the command — example:
cat output/example.com-123456789/report.md
```

### 3. Drill Into Failing Checks (Optional)

```bash
# Show only non-passing checks
ga4 health check <property_id> --json \
  | jq '.data.checks[] | select(.status != "pass")'

# Access checks only
ga4 health access <property_id> --json | jq '.data.checks[]'

# Tracking checks only
ga4 health tracking <property_id> --json | jq '.data.checks[]'
```

### 4. Quick Summary (Before Full Report)

```bash
ga4 health summary <property_id>
# Output: 123456789  My Property  87/100 (B)  21 pass, 2 warn, 1 fail
```

### 5. Multi-Property Scan

```bash
# Scan all properties in an account
ga4 scan report --account <account_id>

# Check issues across all properties
ga4 scan issues --account <account_id>

# Tabular overview without writing files
ga4 scan all --account <account_id>
```

## Variations

| Goal | Flag |
|------|------|
| Skip site spider | `--spider 0` |
| Force fresh data | `--no-cache` |
| Custom output directory | `--output reports` |
| JSON for automation | `--json` |
| Faster multi-property scan | `--workers 5` |

```bash
# Minimal: checks only, no spider
ga4 health report <property_id> --spider 0

# Authoritative: bypass all caches
ga4 health report <property_id> --no-cache

# Automation: JSON output
ga4 health report <property_id> --json | jq '.data.score'
```

## Reading the Report

| Section | What to Look For |
|---------|-----------------|
| Score | Grade A/B = healthy; C = needs attention; D/F = urgent |
| Tracking | Data recency, session volume, (not set) rates |
| Config | Data retention, enhanced measurement, timezone |
| Access | Admin count, external domains, role distribution |
| Site Tag Coverage | Pages where GTM/gtag was not detected |
| Raw Data | Traffic, sources, engagement for the last 30 days |

## Pipe Patterns

```bash
# Extract score for monitoring
ga4 health check <property_id> --json | jq '.data.score'

# Feed failing checks to a Slack alert (with fslack)
ga4 health check <property_id> --json \
  | jq '[.data.checks[] | select(.status == "fail")]' \
  | fslack messages send --channel analytics-alerts --json

# Summarise all properties for an account
ga4 scan all --account <account_id> --json | jq '.data.overall'
```
