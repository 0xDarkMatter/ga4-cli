# ga4

> Google Analytics 4 property management, health diagnostics, and schema replication

## Installation

```bash
cd X:\Clique\GA4
uv pip install -e .
```

## Quick Start

```bash
# Authenticate (default profile)
ga4 auth login

# Authenticate with named profile
ga4 auth login --profile roam

# Check status
ga4 auth status
ga4 auth list              # Show all profiles

# List resources
ga4 accounts list
ga4 properties list
ga4 --profile roam properties list --account 16621930
```

## Commands

### Authentication

| Command | Description |
|---------|-------------|
| `ga4 auth login [--profile NAME]` | Authenticate via OAuth2 |
| `ga4 auth status [--json]` | Check auth status |
| `ga4 auth logout [--profile NAME]` | Clear credentials |
| `ga4 auth list` | List all profiles |

Global flag `--profile NAME` (or env `GA4_PROFILE`) selects the auth profile for any command.

### Accounts & Properties

| Command | Description |
|---------|-------------|
| `ga4 accounts list [--json]` | List GA4 accounts |
| `ga4 properties list [--account ID] [--json]` | List properties |
| `ga4 properties get <id> [--json]` | Get specific property |

### Users (Access Management)

| Command | Description |
|---------|-------------|
| `ga4 users list <property-id> [--json]` | List users with access |
| `ga4 users list --account <account-id> [--json]` | List account-level users |
| `ga4 users add <property-id> <email> --role <role> [--dry-run]` | Add user access |
| `ga4 users add --account <account-id> <email> --role <role>` | Add account-level access |
| `ga4 users remove <property-id> <email> [--dry-run]` | Remove user access |
| `ga4 users remove --account <account-id> <email>` | Remove account-level access |
| `ga4 users copy <src> <dest> [--account] [--dry-run]` | Copy users between properties/accounts |
| `ga4 users batch-add <id> <file> [--account] [--dry-run]` | Add users from JSON/CSV |

**Roles:** `viewer`, `analyst`, `editor`, `admin`

**Scoping:** All user commands support property-level (default) and account-level (`--account`/`-a`). Account-level access cascades to all properties under the account.

### Reports

| Command | Description |
|---------|-------------|
| `ga4 reports run <property-id> [OPTIONS]` | Run a custom report |
| `ga4 reports realtime <property-id> [OPTIONS]` | Run a realtime report |

**Options:** `-d dimensions`, `-m metrics`, `--from`, `--to`, `-n limit`, `-o order-by`, `--asc`

### Dimensions & Metrics

| Command | Description |
|---------|-------------|
| `ga4 dimensions list <property-id> [--json]` | List available dimensions |
| `ga4 dimensions get <property-id> <api-name> [--json]` | Get dimension details |
| `ga4 metrics list <property-id> [--json]` | List available metrics |
| `ga4 metrics get <property-id> <api-name> [--json]` | Get metric details |

### Health (Property Diagnostics)

| Command | Description |
|---------|-------------|
| `ga4 health check <property-id> [--json] [--no-cache]` | Full 25-check diagnostic |
| `ga4 health access <property-id> [--json]` | Access audit only |
| `ga4 health tracking <property-id> [--json]` | Tracking & data quality only |
| `ga4 health summary <property-id> [--json]` | Quick one-line score |
| `ga4 health report <property-id> [-o DIR] [--spider N] [--no-cache]` | Full markdown report with site spider |

### Scan (Multi-Property)

| Command | Description |
|---------|-------------|
| `ga4 scan all [--account ID] [--json]` | Health check all properties |
| `ga4 scan issues [--account ID] [--json]` | Only show problems |
| `ga4 scan report [--account ID] [-o DIR]` | Generate reports for all properties |
| `ga4 scan permissions [--account ID] [--json]` | Cross-property permission matrix |

### Schema (Export & Deploy)

| Command | Description |
|---------|-------------|
| `ga4 schema export <property-id> -o FILE` | Export property schema to JSON |
| `ga4 schema deploy FILE --account ID --name NAME --url URL` | Create new property with schema |
| `ga4 schema deploy FILE --property ID` | Apply schema to existing property |

Both commands support `--dry-run` and `--json`.

**Exported schema includes:** custom dimensions, custom metrics, key events, channel groups, enhanced measurement settings, data retention, audiences.

### Channels (Channel Groups)

| Command | Description |
|---------|-------------|
| `ga4 channels list <property-id> [--json]` | List channel groups |
| `ga4 channels get <property-id> <group-id> [--json]` | Get channel group details |
| `ga4 channels create <property-id> --template <name> [--dry-run]` | Create from template |
| `ga4 channels create <property-id> --from-file <file> [--dry-run]` | Create from JSON file |
| `ga4 channels update <property-id> <group-id> [--template/--from-file]` | Update existing group |
| `ga4 channels export <property-id> <group-id> -o <file>` | Export group to JSON file |
| `ga4 channels delete <property-id> <group-id> [--dry-run]` | Delete custom group |
| `ga4 channels templates [--json]` | List available templates |

**Templates:** `ai-traffic` — Clones the default channel group and inserts "AI Traffic" above Referral. Via API, matches all Referral traffic (API limitation: only `eachScopeDefaultChannelGroup` is supported). Edit in GA4 UI to apply source-level AI domain regex. See `docs/AI_TRAFFIC_CHANNELS.md`.

Standard properties support max 2 custom channel groups.

### Cache

| Command | Description |
|---------|-------------|
| `ga4 cache` | Show cache status |
| `ga4 cache clear` | Clear all cached data |

### Introspection

| Command | Description |
|---------|-------------|
| `ga4 describe [--json]` | List all resources and actions |

## Health Checks (25 checks)

| Category | Checks |
|----------|--------|
| **Tracking** | Data recency, realtime, session volume, (not set), bounce rate, engagement, traffic trend, event diversity |
| **Config** | Property config, data streams, key events, custom dims/metrics, enhanced measurement, audiences, ads links, data retention, channel groups |
| **Access** | User count, admin count, external domains, role distribution |
| **Tags** | Double-tagging, self-referrals, hostname fragmentation, channel grouping |

Scoring: 0-100, Grades: A (≥90), B (≥75), C (≥60), D (≥40), F (<40)

## Schema Replication

Export a template property's schema once, deploy to new sites repeatedly:

```bash
# Export template
ga4 --profile roam schema export 309144142 -o roam-schema.json

# Preview deploy
ga4 --profile roam schema deploy roam-schema.json \
  --account 16621930 --name "newsite.com.au - GA4" \
  --url "https://www.newsite.com.au" --dry-run

# Deploy for real
ga4 --profile roam schema deploy roam-schema.json \
  --account 16621930 --name "newsite.com.au - GA4" \
  --url "https://www.newsite.com.au"

# Apply to existing property (skips duplicates)
ga4 --profile roam schema deploy roam-schema.json --property 461067940
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Auth required |
| 3 | Not found |
| 4 | Validation error |
| 5 | Forbidden |
| 6 | Rate limited |

## Protocol

This tool follows the [Clique Protocol](../00_Fabric/docs/CLIQUE_PROTOCOL.md).
