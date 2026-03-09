# ga4 - AI Assistant Context

## Purpose

Google Analytics 4 reporting and user management CLI.

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
| `ga4 properties list [--account ID] [--json]` | List properties |
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

**Note:** Access can be at Account or Property level. Property-level lists may be empty if access is granted at Account level.

### Reports

| Command | Description |
|---------|-------------|
| `ga4 reports run <property-id> [OPTIONS]` | Run a custom report |
| `ga4 reports realtime <property-id> [OPTIONS]` | Run a realtime report |

**Report Options:** `-d dimensions`, `-m metrics`, `--from`, `--to`, `-n limit`, `-o order-by`, `--asc`

### Dimensions & Metrics

| Command | Description |
|---------|-------------|
| `ga4 dimensions list <property-id> [--json]` | List available dimensions |
| `ga4 dimensions get <property-id> <api-name>` | Get dimension details |
| `ga4 metrics list <property-id> [--json]` | List available metrics |
| `ga4 metrics get <property-id> <api-name>` | Get metric details |

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
| `ga4 describe [--json]` | List all resources and actions (no auth required) |

## Authentication

```bash
# Check if authenticated
ga4 auth status --json

# If not authenticated
ga4 auth login
```

## Common Workflows

### User Management (Cross-Org Migration)

```bash
# List current users on a property
ga4 users list 123456789 --json

# Add user with analyst role
ga4 users add 123456789 user@example.com --role analyst

# Remove user access
ga4 users remove 123456789 user@example.com

# Copy users between properties (for Looker Studio migrations)
ga4 users copy 123456789 987654321 --dry-run  # Preview first
ga4 users copy 123456789 987654321            # Execute
ga4 users copy 123456789 987654321 --role analyst  # Only analysts
ga4 users copy 123456789 987654321 --exclude admin@example.com

# Batch add from file
ga4 users batch-add 123456789 users.json
ga4 users batch-add 123456789 users.csv --dry-run
```

**File formats:**
```json
[{"email": "user@example.com", "role": "analyst"}]
```
```csv
email,role
user@example.com,analyst
```

### Property Discovery

```bash
# List all properties
ga4 properties list --json | jq '.data[] | {id, name}'

# Filter by account
ga4 properties list --account 123456789

# Get property details
ga4 properties get 987654321 --json
```

### Reports

```bash
# Run a basic report (last 30 days)
ga4 reports run 123456789

# Custom dimensions and metrics
ga4 reports run 123456789 -d date,city -m activeUsers,sessions

# Date range
ga4 reports run 123456789 --from 2025-01-01 --to 2025-01-31

# Sort by metric
ga4 reports run 123456789 -d city -m sessions -o sessions

# Realtime data
ga4 reports realtime 123456789 -d country -m activeUsers

# JSON output for scripting
ga4 reports run 123456789 --json | jq '.data.rows[] | select(.sessions > "100")'
```

### Health Checks & Scanning

```bash
# Full health check on a property
ga4 health check 123456789

# Quick summary
ga4 health summary 123456789

# Access audit only
ga4 health access 123456789 --json | jq '.data.checks'

# Scan all properties for issues
ga4 scan issues

# Scan with JSON for scripting
ga4 scan all --json | jq '.data.properties[] | select(.score < 60)'

# Scan specific account
ga4 scan all --account 123456789
```

### Dimensions & Metrics Discovery

```bash
# List all dimensions for a property
ga4 dimensions list 123456789

# Filter by category
ga4 dimensions list 123456789 --category User
ga4 metrics list 123456789 --category Session

# Get details for a specific dimension/metric
ga4 dimensions get 123456789 city
ga4 metrics get 123456789 activeUsers
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 2 | Auth required |
| 3 | Not found |
| 4 | Validation error |
| 5 | Forbidden |

## APIs Used

| API | Endpoint | Purpose |
|-----|----------|---------|
| Analytics Admin API | `analyticsadmin.googleapis.com/v1beta` | Properties, accounts, users |
| Analytics Data API | `analyticsdata.googleapis.com/v1beta` | Reports, dimensions, metrics |

## Protocol

Follows [Fabric Protocol](../00_Fabric/docs/FABRIC_PROTOCOL.md).
