# GA4-CLI

> Google Analytics 4 property management, health diagnostics, schema replication, and reporting CLI

A [Clique Protocol](../00_Fabric/docs/CLIQUE_PROTOCOL.md) tool for managing GA4 properties at scale. Supports multi-profile OAuth authentication, 25-check health diagnostics, schema export/deploy for property replication, custom channel groups, and user access management across accounts and properties.

## Installation

```bash
cd X:\Fabric\GA4
uv pip install -e .
```

## Quick Start

```bash
# Authenticate
ga4 auth login
ga4 auth login --profile roam       # Named profile for another Google account

# Explore
ga4 accounts list
ga4 properties list --json
ga4 --profile roam properties list --account 16621930

# Health check a property
ga4 health check 309144142
ga4 health report 309144142 -o reports/

# Manage users
ga4 users list 309144142
ga4 users add 309144142 user@example.com --role analyst

# Run reports
ga4 reports run 309144142 -d date,city -m activeUsers,sessions
```

## Global Flags

| Flag | Short | Description |
|------|-------|-------------|
| `--profile NAME` | `-P` | Auth profile (env: `GA4_PROFILE`) |
| `--fields FIELDS` | | Comma-separated fields for JSON output |
| `--quiet` | `-q` | Suppress non-essential stderr |
| `--version` | `-V` | Show version |
| `--help` | | Show help |

## Commands

### Authentication

| Command | Description |
|---------|-------------|
| `ga4 auth login [--profile NAME] [--port N]` | Authenticate via OAuth2 |
| `ga4 auth status [--json]` | Check auth status |
| `ga4 auth logout [--profile NAME]` | Clear credentials |
| `ga4 auth list` | List all profiles with status |

### Accounts & Properties

| Command | Description |
|---------|-------------|
| `ga4 accounts list [-n LIMIT] [--json]` | List GA4 accounts |
| `ga4 properties list [--account ID] [-n LIMIT] [--json]` | List properties |
| `ga4 properties get <id> [--json]` | Get specific property |

### Users (Access Management)

All user commands support property-level (default) and account-level (`--account`/`-a`). Account-level access cascades to all properties under the account.

| Command | Description |
|---------|-------------|
| `ga4 users list <property-id> [--json]` | List property users |
| `ga4 users list --account <account-id> [--json]` | List account-level users |
| `ga4 users add <property-id> <email> --role <role> [--dry-run]` | Add user access |
| `ga4 users add --account <id> <email> --role <role>` | Add account-level access |
| `ga4 users remove <property-id> <email> [--dry-run]` | Remove user access |
| `ga4 users remove --account <id> <email>` | Remove account-level access |
| `ga4 users copy <src> <dest> [--account] [--dry-run]` | Copy users between properties/accounts |
| `ga4 users batch-add <id> <file> [--account] [--dry-run]` | Add users from JSON/CSV file |

**Roles:** `viewer`, `analyst`, `editor`, `admin`

### Reports

| Command | Description |
|---------|-------------|
| `ga4 reports run <property-id> [OPTIONS]` | Run a custom report |
| `ga4 reports realtime <property-id> [OPTIONS]` | Run a realtime report |

**Options:** `-d dimensions`, `-m metrics`, `--from`, `--to`, `-n limit`, `-o order-by`, `--asc`

### Dimensions & Metrics

| Command | Description |
|---------|-------------|
| `ga4 dimensions list <property-id> [-n LIMIT] [--json]` | List available dimensions |
| `ga4 dimensions get <property-id> <api-name> [--json]` | Get dimension details |
| `ga4 metrics list <property-id> [-n LIMIT] [--json]` | List available metrics |
| `ga4 metrics get <property-id> <api-name> [--json]` | Get metric details |

### Health (Property Diagnostics)

25 checks across tracking, config, access, and tag categories. Scores 0-100 with grades A-F.

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

Export a property's configuration and replicate it to new or existing properties. Idempotent — safe to run multiple times.

| Command | Description |
|---------|-------------|
| `ga4 schema export <property-id> -o FILE [--json]` | Export property schema to JSON |
| `ga4 schema deploy FILE --account ID --name NAME --url URL [--dry-run]` | Create new property with schema |
| `ga4 schema deploy FILE --property ID [--dry-run]` | Apply schema to existing property |

**Schema includes:** custom dimensions, custom metrics, key events, channel groups, enhanced measurement settings, data retention, audiences.

### Channels (Channel Groups)

| Command | Description |
|---------|-------------|
| `ga4 channels list <property-id> [-n LIMIT] [--json]` | List channel groups |
| `ga4 channels get <property-id> <group-id> [--json]` | Get channel group details |
| `ga4 channels create <property-id> --template <name> [--dry-run]` | Create from template |
| `ga4 channels create <property-id> --from-file <file> [--dry-run]` | Create from JSON file |
| `ga4 channels update <property-id> <group-id> [--template/--from-file]` | Update existing group |
| `ga4 channels export <property-id> <group-id> -o <file>` | Export to reusable JSON |
| `ga4 channels delete <property-id> <group-id> [--dry-run]` | Delete custom group |
| `ga4 channels templates [--json]` | List available templates |

**Templates:** `ai-traffic` — Clones the default channel group and inserts "AI Traffic" above Referral. Via API, matches all Referral traffic (API only supports `eachScopeDefaultChannelGroup`). Edit in GA4 UI to apply source-level AI domain regex. See [`docs/AI_TRAFFIC_CHANNELS.md`](docs/AI_TRAFFIC_CHANNELS.md).

### Cache & Introspection

| Command | Description |
|---------|-------------|
| `ga4 cache [status]` | Show cache status |
| `ga4 cache clear [<property-id>]` | Clear cached data |
| `ga4 describe [--json]` | List all resources and actions |

## Health Checks (25 checks)

| Category | Checks |
|----------|--------|
| **Tracking** | Data recency, realtime, session volume, (not set), bounce rate, engagement, traffic trend, event diversity |
| **Config** | Property config, data streams, key events, custom dims/metrics, enhanced measurement, audiences, ads links, data retention, channel groups |
| **Access** | User count, admin count, external domains, role distribution |
| **Tags** | Double-tagging, self-referrals, hostname fragmentation, channel grouping |

Scoring: 0-100. Grades: A (≥90), B (≥75), C (≥60), D (≥40), F (<40).

## Common Workflows

### Schema Replication (New Sites)

```bash
# Export template property
ga4 --profile roam schema export 309144142 -o roam-schema.json

# Preview
ga4 --profile roam schema deploy roam-schema.json \
  --account 16621930 --name "newsite.com.au - GA4" \
  --url "https://www.newsite.com.au" --dry-run

# Deploy
ga4 --profile roam schema deploy roam-schema.json \
  --account 16621930 --name "newsite.com.au - GA4" \
  --url "https://www.newsite.com.au"

# Apply to existing property (skips duplicates)
ga4 --profile roam schema deploy roam-schema.json --property 461067940
```

### Multi-Account User Management

```bash
# Property-level
ga4 users add 309144142 user@example.com --role analyst
ga4 users remove 309144142 user@example.com

# Account-level (cascades to all properties)
ga4 users add --account 16621930 user@example.com --role admin
ga4 users list --account 16621930 --json

# Bulk from file
ga4 users batch-add 309144142 users.json --dry-run
ga4 users copy 309144142 987654321 --dry-run
```

### Health & Scanning

```bash
# Single property
ga4 health check 309144142
ga4 health report 309144142 --spider 0   # skip spider

# All properties in an account
ga4 scan all --account 16621930
ga4 scan issues --account 16621930
ga4 scan permissions --account 16621930 --json
```

### JSON Pipeline Examples

```bash
# List property IDs
ga4 properties list --json | jq -r '.data[].id'

# Get health score
ga4 health check 309144142 --json | jq '.data.score'

# Filter output fields
ga4 --fields id,name properties list --json

# Quiet mode for scripts
ga4 -q health summary 309144142 --json
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
| 7 | Conflict |

## APIs Used

| API | Endpoint | Purpose |
|-----|----------|---------|
| Analytics Admin v1beta | `analyticsadmin.googleapis.com/v1beta` | Properties, accounts, schema |
| Analytics Admin v1alpha | `analyticsadmin.googleapis.com/v1alpha` | Audiences, channels, access bindings, enhanced measurement |
| Analytics Data v1beta | `analyticsdata.googleapis.com/v1beta` | Reports, dimensions, metrics |

## Recent Changes

### v0.2.0 (March 2026)

**Channel Groups**
- Full CRUD CLI for custom channel groups (list, get, create, update, export, delete)
- AI Traffic template — creates channel group with AI Traffic above Referral
- Documented GA4 Admin API limitation: only `eachScopeDefaultChannelGroup` supported as filter field
- Channel groups integrated into schema export/deploy with idempotent dedup
- Channel groups health check (#25)

**Account-Level User Management**
- All user commands now support `--account`/`-a` for account-level access bindings
- Account-level access cascades to all properties under the account
- Added `delete_account_access_binding` and `batch_create_account_access_bindings`

**Clique Protocol Compliance**
- Added `--fields` global flag for JSON field selection
- Added `--quiet`/`-q` global flag to suppress non-essential stderr
- Added `--limit`/`-n` to users list and channels list
- Added `validate_id()` for agent safety (rejects `?#%&..` in IDs)
- Added `## Agent Rules` section to AGENTS.md
- Added `origin` and updated `resources` in `[tool.clique]` metadata
- Expanded test suite from 4 to 20 tests

**Schema**
- Added channel groups to schema export/deploy
- Added `skipped` tracking for idempotent deploy reporting
- Added `analytics.edit` OAuth scope for write operations

### v0.1.0

- Initial release with auth, properties, accounts, reports, dimensions, metrics
- Health diagnostics (25 checks, scoring, grading)
- Multi-property scanning
- Schema export/deploy for property replication
- Multi-profile OAuth authentication
- Site spider for tag coverage
- Response caching

## Protocol

This tool follows the [Clique Protocol](../00_Fabric/docs/CLIQUE_PROTOCOL.md).
