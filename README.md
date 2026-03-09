# ga4

> Google Analytics 4 reporting and data analysis

## Installation

```bash
cd X:\Fabric\Ga4
uv pip install -e .
```

## Quick Start

```bash
# Authenticate
ga4 auth login

# Check status
ga4 auth status

# List resources
ga4 accounts list
ga4 properties list
ga4 users list <property-id>
```

## Commands

### Authentication

| Command | Description |
|---------|-------------|
| `ga4 auth login` | Authenticate via OAuth2 |
| `ga4 auth status [--json]` | Check auth status |
| `ga4 auth logout` | Clear credentials |

### Accounts

| Command | Description |
|---------|-------------|
| `ga4 accounts list [--json]` | List GA4 accounts |

### Properties

| Command | Description |
|---------|-------------|
| `ga4 properties list [--json]` | List properties |
| `ga4 properties get <id> [--json]` | Get specific property |

### Users (Access Management)

| Command | Description |
|---------|-------------|
| `ga4 users list <property-id> [--json]` | List users with access |
| `ga4 users add <property-id> <email> --role <role>` | Add user access |
| `ga4 users remove <property-id> <email>` | Remove user access |
| `ga4 users copy <src> <dest> [--dry-run]` | Copy users between properties |
| `ga4 users batch-add <property-id> <file>` | Add users from JSON/CSV |

**Roles:** `viewer`, `analyst`, `editor`, `admin`

### Reports

| Command | Description |
|---------|-------------|
| `ga4 reports run <property-id> [OPTIONS]` | Run a custom report |
| `ga4 reports realtime <property-id> [OPTIONS]` | Run a realtime report |

**Report Options:**
- `-d, --dimensions` - Dimensions (comma-separated, default: date)
- `-m, --metrics` - Metrics (comma-separated, default: activeUsers,sessions)
- `--from` - Start date (YYYY-MM-DD or relative like "30daysAgo")
- `--to` - End date (YYYY-MM-DD or relative like "today")
- `-n, --limit` - Max rows (default: 100)
- `-o, --order-by` - Sort by dimension or metric
- `--asc` - Sort ascending (default: descending)

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
| `ga4 health check <property-id> [--json]` | Full health check (tracking, access, config) |
| `ga4 health access <property-id> [--json]` | Access audit only |
| `ga4 health tracking <property-id> [--json]` | Tracking & data quality only |
| `ga4 health summary <property-id> [--json]` | Quick one-line status |

### Scan (Multi-Property)

| Command | Description |
|---------|-------------|
| `ga4 scan all [--account ID] [--json]` | Health check all properties |
| `ga4 scan access [--account ID] [--json]` | Access audit across properties |
| `ga4 scan issues [--account ID] [--json]` | Only show problems |

### Introspection

| Command | Description |
|---------|-------------|
| `ga4 describe [--json]` | List all resources and actions |

## Health Checks

```bash
# Full health check on a property
ga4 health check 123456789

# Quick one-line summary
ga4 health summary 123456789

# Access audit only
ga4 health access 123456789

# Tracking & data quality
ga4 health tracking 123456789

# Scan all properties for issues
ga4 scan issues

# Scan all properties (full report)
ga4 scan all --json | jq '.data.overall'

# Scan specific account
ga4 scan all --account 123456789
```

**Health checks include:**
- Data recency (is data flowing?)
- Session volume and bounce rate
- (not set) prevalence in source dimension
- User count and admin count
- External domain detection
- Role distribution analysis
- Property configuration (timezone, currency, industry)
- Custom dimensions/metrics

## Usage Examples

```bash
# List properties and filter with jq
ga4 properties list --json | jq '.data[0]'

# Run a report
ga4 reports run 123456789 -d date -m activeUsers,sessions
ga4 reports run 123456789 -d date,city -m sessions --from 2025-01-01 --to 2025-01-31
ga4 reports run 123456789 --json | jq '.data.rows'

# Realtime report
ga4 reports realtime 123456789 -d country -m activeUsers

# List available dimensions and metrics
ga4 dimensions list 123456789
ga4 metrics list 123456789 --category User

# Add user to property
ga4 users add 123456789 user@example.com --role analyst

# List users on property
ga4 users list 123456789

# Remove user from property
ga4 users remove 123456789 user@example.com

# Copy users between properties (for Looker Studio migrations)
ga4 users copy 123456789 987654321 --dry-run  # Preview
ga4 users copy 123456789 987654321            # Execute
ga4 users copy 123456789 987654321 --role analyst  # Only analysts
ga4 users copy 123456789 987654321 --exclude admin@example.com

# Batch add users from file
ga4 users batch-add 123456789 users.json --dry-run
ga4 users batch-add 123456789 users.csv
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

## Protocol

This tool follows the [Fabric Protocol](../00_Fabric/docs/FABRIC_PROTOCOL.md).
