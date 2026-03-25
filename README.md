# GA4-CLI

[![Version](https://img.shields.io/badge/version-0.3.0-blue)](https://github.com/0xDarkMatter/ga4-cli/releases)
[![Python](https://img.shields.io/badge/python-3.11+-green)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

A command-line tool for managing Google Analytics 4 properties at scale. Built for agencies and teams that manage multiple GA4 accounts across different clients.

Run health diagnostics across every property in an account. Export a template property's schema — custom dimensions, key events, channel groups, enhanced measurement — and deploy it to new sites in one command. Manage user access at both account and property level, with bulk operations for onboarding and migrations.

Supports multi-profile OAuth so you can switch between Google accounts without re-authenticating. Every command outputs structured JSON for scripting and automation.

## Installation

```bash
uv pip install -e .
```

## Quick Start

```bash
# Authenticate
ga4 auth login
ga4 auth login --profile client1       # Named profile for another Google account

# Explore
ga4 accounts list
ga4 properties list --json
ga4 --profile client1 properties list --account 987654321

# Health check a property
ga4 health check 123456789
ga4 health report 123456789 -o reports/

# Manage users
ga4 users list 123456789
ga4 users add 123456789 user@example.com --role analyst

# Run reports
ga4 reports run 123456789 -d date,city -m activeUsers,sessions
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

### BigQuery (GA4 Export)

GA4-specific BigQuery commands that the official `bq` CLI doesn't provide. Understands GA4 export dataset conventions (`analytics_<property_id>`), auto-detects GCP projects from BQ links, and includes pre-built query templates for common GA4 analysis.

**Why not just use `bq`?** The `bq` CLI is a general BigQuery tool — it doesn't know about GA4 properties, export links, or the nested event schema. `ga4 bq` bridges the gap: it cross-references the GA4 Admin API with BigQuery to audit exports, check freshness, and run GA4-specific queries without writing SQL.

| Command | Description |
|---------|-------------|
| `ga4 bq status <property-id>` | Show BQ export link config (project, export types, excluded events) |
| `ga4 bq link <property-id> --project <gcp> [--streaming] [--dry-run]` | Create BQ export link |
| `ga4 bq freshness <property-id>` | Check latest export table dates and data lag |
| `ga4 bq audit [--account ID]` | Scan all properties for BQ link status and gaps |
| `ga4 bq query <property-id> --template <name> [--from --to]` | Run pre-built GA4 query |
| `ga4 bq query <property-id> --sql "SELECT ..."` | Run custom SQL |
| `ga4 bq cost <property-id> --template <name>` | Estimate query cost (dry-run) |
| `ga4 bq tables <property-id> [-n LIMIT]` | List tables in GA4 export dataset |
| `ga4 bq schema <property-id> [--table NAME]` | Show table schema |
| `ga4 bq datasets <gcp-project> [--ga4-only]` | List datasets in a GCP project |
| `ga4 bq templates` | List available query templates |

**Query templates:** `ai-traffic`, `sessions`, `top-pages`, `events`, `channels`

```bash
# Check if BQ export is set up
ga4 bq status 123456789

# Audit all properties in an account
ga4 bq audit --account 987654321

# Check data freshness
ga4 bq freshness 123456789

# Run AI traffic analysis from BQ
ga4 bq query 123456789 --template ai-traffic --from 2025-01-01 --to 2025-03-01

# Estimate cost before running
ga4 bq cost 123456789 --template sessions --from 2025-01-01 --to 2025-12-31

# Browse tables and schema
ga4 bq tables 123456789
ga4 bq schema 123456789
```

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
ga4 --profile client1 schema export 123456789 -o template-schema.json

# Preview
ga4 --profile client1 schema deploy template-schema.json \
  --account 987654321 --name "example.com.au - GA4" \
  --url "https://www.example.com.au" --dry-run

# Deploy
ga4 --profile client1 schema deploy template-schema.json \
  --account 987654321 --name "example.com.au - GA4" \
  --url "https://www.example.com.au"

# Apply to existing property (skips duplicates)
ga4 --profile client1 schema deploy template-schema.json --property 111222333
```

### Multi-Account User Management

```bash
# Property-level
ga4 users add 123456789 user@example.com --role analyst
ga4 users remove 123456789 user@example.com

# Account-level (cascades to all properties)
ga4 users add --account 987654321 user@example.com --role admin
ga4 users list --account 987654321 --json

# Bulk from file
ga4 users batch-add 123456789 users.json --dry-run
ga4 users copy 123456789 987654321 --dry-run
```

### Health & Scanning

```bash
# Single property
ga4 health check 123456789
ga4 health report 123456789 --spider 0   # skip spider

# All properties in an account
ga4 scan all --account 987654321
ga4 scan issues --account 987654321
ga4 scan permissions --account 987654321 --json
```

### JSON Pipeline Examples

```bash
# List property IDs
ga4 properties list --json | jq -r '.data[].id'

# Get health score
ga4 health check 123456789 --json | jq '.data.score'

# Filter output fields
ga4 --fields id,name properties list --json

# Quiet mode for scripts
ga4 -q health summary 123456789 --json
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

### v0.3.0 (March 2026)

**BigQuery Integration**
- New `ga4 bq` command group with 10 commands
- `bq status` — show BQ export link configuration
- `bq link` — create BQ export links via Admin API
- `bq freshness` — check data lag on export tables
- `bq audit` — scan all properties for BQ link gaps
- `bq query` — run pre-built or custom SQL against GA4 BQ exports
- `bq cost` — dry-run cost estimation before querying
- `bq tables` / `bq schema` / `bq datasets` — browse BQ structure
- 5 query templates: ai-traffic, sessions, top-pages, events, channels
- Auto-detects GCP project from BQ link (no `--project` needed)
- BQ REST API client using existing OAuth tokens (no extra deps)
- 36 automated tests (up from 20)

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

Follows the Clique Protocol for consistent CLI patterns, JSON output, and exit codes.
