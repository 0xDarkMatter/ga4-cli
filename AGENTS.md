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

### Reports, Dimensions, Metrics

| Command | Description |
|---------|-------------|
| `ga4 reports list [--json]` | List reports |
| `ga4 reports get <id> [--json]` | Get specific report |
| `ga4 dimensions list [--json]` | List dimensions |
| `ga4 dimensions get <id> [--json]` | Get specific dimension |
| `ga4 metrics list [--json]` | List metrics |
| `ga4 metrics get <id> [--json]` | Get specific metric |

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
