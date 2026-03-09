---
name: ga4-recipe-client-onboard
description: "Onboard a new client: scan all GA4 properties, generate reports, identify issues. Triggers: new client, onboard, client setup, account audit, first review."
version: 1.0.0
category: recipe
tool: ga4
requires:
  bins: ["ga4", "jq"]
  skills: ["ga4-ops", "ga4-health", "ga4-access"]
allowed-tools: "Read Bash Grep Write"
---

# GA4 Client Onboarding

A repeatable workflow for the first review of a new client's Google Analytics 4
setup. Produces per-property health reports, a permission matrix, an issues
summary, and actionable recommendations — all from a single account scan.

## What This Produces

- Health report (markdown) per property in `output/`
- Permission matrix showing every user × property combination
- Prioritised issues list (fail > warn > info)
- Recommendations covering data retention, enhanced measurement, role hygiene

## Prerequisites

- [ ] Client has granted your Google account viewer+ access to their GA4
- [ ] Authenticated: `ga4 auth status` (or use a dedicated client profile)

### Using a Dedicated Profile (Recommended)

Profiles keep client credentials isolated from your own account:

```bash
# Authenticate as the client
ga4 auth login --profile <client-slug>

# Verify
ga4 --profile <client-slug> auth status

# All subsequent commands use --profile <client-slug>
# or set GA4_PROFILE=<client-slug> in the shell
```

## Steps

### 1. Discover Accounts and Properties

```bash
# List all accounts the authenticated user can see
ga4 accounts list --json | jq '.data[] | {id: .name, name: .displayName}'

# List properties — filter to a specific account
ga4 properties list --account <account_id> --json \
  | jq '.data[] | {id, name, account}'
```

Note the `account_id` — you need it for all scan commands.

### 2. Generate Health Reports for All Properties

```bash
ga4 scan report --account <account_id> --output output
# With a named profile:
ga4 --profile <client-slug> scan report --account <account_id> --output output
```

Each property writes to `output/{domain}-{property_id}/report.md`. Progress
and per-property scores are printed as they complete.

### 3. Permission Audit

```bash
ga4 scan permissions --account <account_id>
# JSON for further processing:
ga4 scan permissions --account <account_id> --json | jq '.data.issues[]'
```

Flags to look for in output:

- `INCONSISTENT` — same user has different roles on different properties
- `PARTIAL` — user can access some but not all properties
- `EXTERNAL` — external domain user with editor or admin role

### 4. Issues Summary

```bash
# Properties with issues only (skips clean properties)
ga4 scan issues --account <account_id>

# JSON — count by severity
ga4 scan issues --account <account_id> --json \
  | jq '.data.properties[] | {name: .property_name, fails: .summary.fail, warns: .summary.warn}'
```

### 5. Review Output

```bash
# List generated reports
ls output/*/report.md

# Spot-check a single property
cat output/<domain>-<property_id>/report.md
```

## Using Profiles for Client Separation

```bash
# Login as client profile
ga4 auth login --profile acme-corp

# All commands use client credentials
ga4 --profile acme-corp scan report --account 123456
ga4 --profile acme-corp scan permissions --account 123456
ga4 --profile acme-corp scan issues --account 123456

# List all profiles
ga4 auth list
```

Profiles are stored per-user and never shared between clients.

## Deliverables Checklist

- [ ] Health reports for all properties in `output/`
- [ ] Permission matrix reviewed (`scan permissions`)
- [ ] Issues list reviewed and prioritised (`scan issues`)
- [ ] Data retention setting noted (check Tracking section of each report)
- [ ] Enhanced measurement status noted per property
- [ ] Recommendations documented for client handoff

## Common Recommendations

| Finding | Recommendation |
|---------|---------------|
| Data retention < 14 months | Extend to 14 months in property settings |
| Enhanced measurement off | Enable for scroll, outbound, file download events |
| External user with admin role | Downgrade to analyst or remove |
| No data in last 7 days | Check stream configuration and tag deployment |
| High (not set) rate | Review custom dimension configuration |
| Score D or F | Escalate to implementation review |

## Pipe Patterns

```bash
# Overall account health summary
ga4 scan all --account <account_id> --json | jq '.data.overall'

# Extract all failing checks across all properties
ga4 scan all --account <account_id> --json \
  | jq '[.data.properties[].checks[] | select(.status == "fail")]'

# Send issues count to Slack (with fslack)
ga4 scan issues --account <account_id> --json \
  | jq '"Client has \(.data.properties | length) properties with issues"' \
  | fslack messages send --channel client-onboarding --json
```
