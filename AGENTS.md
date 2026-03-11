# ga4 - AI Assistant Context

## Purpose

Google Analytics 4 property management, health diagnostics, schema replication, and reporting CLI. Supports multi-profile authentication for managing multiple Google accounts.

## Global Flags

| Flag | Env Var | Description |
|------|---------|-------------|
| `--profile NAME` / `-P NAME` | `GA4_PROFILE` | Select auth profile (default: `default`) |
| `--version` / `-V` | | Show version |

## Commands

### Authentication

| Command | Description |
|---------|-------------|
| `ga4 auth login [--profile NAME] [--port N]` | Authenticate via OAuth2 |
| `ga4 auth status [--json]` | Check auth status for active profile |
| `ga4 auth logout [--profile NAME]` | Clear credentials |
| `ga4 auth list` | List all profiles with status |

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
| `ga4 users add <property-id> <email> --role <role> [--dry-run]` | Add user access |
| `ga4 users remove <property-id> <email> [--dry-run]` | Remove user access |
| `ga4 users copy <src> <dest> [--dry-run]` | Copy users between properties |
| `ga4 users batch-add <property-id> <file> [--dry-run]` | Add users from JSON/CSV |

**Roles:** `viewer`, `analyst`, `editor`, `admin`

**Note:** Access can be at Account or Property level. Property-level lists may be empty if access is granted at Account level.

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
| `ga4 dimensions get <property-id> <api-name>` | Get dimension details |
| `ga4 metrics list <property-id> [--json]` | List available metrics |
| `ga4 metrics get <property-id> <api-name>` | Get metric details |

### Health (Property Diagnostics)

24 checks across tracking, config, access, and tag categories. Scores 0-100 with grades A-F.

| Command | Description |
|---------|-------------|
| `ga4 health check <property-id> [--json] [--no-cache]` | Full 24-check diagnostic |
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

Export a property's configuration and replicate it to new or existing properties.

| Command | Description |
|---------|-------------|
| `ga4 schema export <property-id> -o FILE [--json]` | Export property schema to JSON |
| `ga4 schema deploy FILE --account ID --name NAME --url URL [--dry-run]` | Create new property with schema |
| `ga4 schema deploy FILE --property ID [--dry-run]` | Apply schema to existing property |

**Schema includes:** custom dimensions, custom metrics, key events, enhanced measurement, data retention, audiences. Excludes Google Ads links.

### Cache

| Command | Description |
|---------|-------------|
| `ga4 cache` | Show cache status |
| `ga4 cache clear` | Clear all cached data |

### Introspection

| Command | Description |
|---------|-------------|
| `ga4 describe [--json]` | List all resources and actions (no auth required) |

## Authentication

```bash
# Default profile
ga4 auth login
ga4 auth status --json

# Named profile (e.g. client account)
ga4 auth login --profile roam
ga4 --profile roam auth status
ga4 --profile roam properties list

# List all profiles
ga4 auth list
```

## Common Workflows

### Schema Replication (New Sites)

```bash
# Export template property schema
ga4 --profile roam schema export 309144142 -o roam-schema.json

# Preview what will be created
ga4 --profile roam schema deploy roam-schema.json \
  --account 16621930 --name "newsite.com.au - GA4" \
  --url "https://www.newsite.com.au" --dry-run

# Deploy: creates property + stream + dims + events + settings
ga4 --profile roam schema deploy roam-schema.json \
  --account 16621930 --name "newsite.com.au - GA4" \
  --url "https://www.newsite.com.au"

# Apply schema to existing property (skips duplicates)
ga4 --profile roam schema deploy roam-schema.json --property 461067940
```

### Health Checks & Scanning

```bash
# Full health check
ga4 health check 123456789
ga4 health check 123456789 --json | jq '.data.score'

# Generate markdown report with site spider
ga4 health report 123456789
ga4 health report 123456789 --spider 0   # skip spider
ga4 health report 123456789 --no-cache   # fresh data

# Scan all properties in an account
ga4 scan all --account 123456789
ga4 scan issues --account 123456789
ga4 scan report --account 123456789 --output reports

# Cross-property permission audit
ga4 scan permissions --account 123456789
ga4 scan permissions --account 123456789 --json | jq '.data.issues'
```

### User Management

```bash
ga4 users list 123456789 --json
ga4 users add 123456789 user@example.com --role analyst
ga4 users remove 123456789 user@example.com
ga4 users copy 123456789 987654321 --dry-run
ga4 users batch-add 123456789 users.json --dry-run
```

**File formats:**
```json
[{"email": "user@example.com", "role": "analyst"}]
```

### Reports

```bash
ga4 reports run 123456789 -d date,city -m activeUsers,sessions
ga4 reports run 123456789 --from 2025-01-01 --to 2025-01-31 --json
ga4 reports realtime 123456789 -d country -m activeUsers
```

### Property Discovery

```bash
ga4 properties list --json | jq '.data[] | {id, name}'
ga4 properties list --account 123456789
ga4 properties get 987654321 --json
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

## APIs Used

| API | Endpoint | Purpose |
|-----|----------|---------|
| Analytics Admin API v1beta | `analyticsadmin.googleapis.com/v1beta` | Properties, accounts, users, schema |
| Analytics Admin API v1alpha | `analyticsadmin.googleapis.com/v1alpha` | Audiences, enhanced measurement, access bindings |
| Analytics Data API v1beta | `analyticsdata.googleapis.com/v1beta` | Reports, dimensions, metrics |

## Protocol

Follows [Fabric Protocol](../00_Fabric/docs/FABRIC_PROTOCOL.md).
