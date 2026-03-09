---
name: ga4-ops
description: "Google Analytics 4 CLI operations for property management, user access control, and cross-org migrations. Use when: (1) Managing GA4 users (add, remove, copy, batch), (2) Listing accounts/properties, (3) Looker Studio migrations (granting viewer access), (4) Bulk user provisioning, (5) Any GA4 property or access management task. Triggers: ga4, google analytics, property access, looker studio, analytics users, grant access, migrate users."
---

# GA4 Operations

CLI tool for Google Analytics 4 property management and user access control.

## Quick Reference

```bash
# Auth
ga4 auth login                    # OAuth2 browser flow
ga4 auth status --json            # Check auth state
ga4 auth logout                   # Clear credentials

# Discovery
ga4 accounts list --json          # All accounts
ga4 properties list --json        # All properties
ga4 properties list --account ID  # Filter by account
ga4 properties get ID --json      # Property details

# User Management
ga4 users list PROPERTY_ID --json
ga4 users add PROPERTY_ID EMAIL --role ROLE
ga4 users remove PROPERTY_ID EMAIL
ga4 users copy SRC_PROP DEST_PROP [--dry-run]
ga4 users batch-add PROPERTY_ID FILE [--dry-run]
```

## Roles

| Role | API Name | Access Level |
|------|----------|--------------|
| `viewer` | predefinedRoles/viewer | Read-only |
| `analyst` | predefinedRoles/analyst | Read + explore |
| `editor` | predefinedRoles/editor | Read + edit |
| `admin` | predefinedRoles/admin | Full control |

## Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Success | Continue |
| 2 | Auth required | Run `ga4 auth login` |
| 3 | Not found | Check property/user ID |
| 4 | Validation error | Check inputs |
| 5 | Forbidden | Check permissions |

## Common Workflows

### Grant Looker Studio Access

Looker Studio requires `viewer` role on the GA4 property:

```bash
# Single user
ga4 users add 123456789 user@example.com --role viewer

# Batch from file
ga4 users batch-add 123456789 users.csv --dry-run
ga4 users batch-add 123456789 users.csv
```

### Cross-Org User Migration

Copy users between properties (e.g., agency transition):

```bash
# Preview first
ga4 users copy 123456789 987654321 --dry-run

# Execute
ga4 users copy 123456789 987654321

# Filter by role
ga4 users copy 123456789 987654321 --role analyst

# Exclude specific users
ga4 users copy 123456789 987654321 --exclude admin@old.com,owner@old.com
```

### Bulk User Provisioning

**JSON format** (`users.json`):
```json
[
  {"email": "alice@example.com", "role": "analyst"},
  {"email": "bob@example.com", "role": "viewer"}
]
```

**CSV format** (`users.csv`):
```csv
email,role
alice@example.com,analyst
bob@example.com,viewer
```

```bash
ga4 users batch-add 123456789 users.json --dry-run
ga4 users batch-add 123456789 users.json
```

### Property Discovery

```bash
# Find all properties
ga4 properties list --json | jq '.data[] | {id, name}'

# Find by name pattern
ga4 properties list --json | jq '.data[] | select(.name | contains("Production"))'

# Get property ID for a specific name
ga4 properties list --json | jq -r '.data[] | select(.name == "My Site") | .id'
```

## jq Patterns

### Extract Data

```bash
# Property IDs only
ga4 properties list --json | jq -r '.data[].id'

# User emails on a property
ga4 users list 123456789 --json | jq -r '.data[].user'

# Count users by role
ga4 users list 123456789 --json | jq '[.data[].roles[]] | group_by(.) | map({role: .[0], count: length})'
```

### Filter Results

```bash
# Properties in specific timezone
ga4 properties list --json | jq '.data[] | select(.time_zone == "America/New_York")'

# Users with admin role
ga4 users list 123456789 --json | jq '.data[] | select(.roles | contains(["admin"]))'

# Properties created after date
ga4 properties list --json | jq '.data[] | select(.create_time > "2024-01-01")'
```

### Transform for Other Tools

```bash
# Create CSV of users
ga4 users list 123456789 --json | jq -r '.data[] | [.user, (.roles | join(";"))] | @csv'

# Export for batch-add to another property
ga4 users list 123456789 --json | jq '[.data[] | {email: .user, role: .roles[0]}]' > users.json
```

## Error Handling

```bash
# Check auth before operations
if ! ga4 auth status --json | jq -e '.data.authenticated' > /dev/null; then
  ga4 auth login
fi

# Handle not found
ga4 properties get 999999999 --json 2>&1 || echo "Property not found"

# Validate role before adding
ROLE="analyst"
if [[ ! "$ROLE" =~ ^(viewer|analyst|editor|admin)$ ]]; then
  echo "Invalid role: $ROLE"
  exit 4
fi
```

## Account vs Property Access

Access can be granted at two levels:

| Level | Scope | API |
|-------|-------|-----|
| Account | All properties under account | `accounts/{id}/accessBindings` |
| Property | Single property only | `properties/{id}/accessBindings` |

**Note:** When listing property users, the list may be empty if access is granted at the account level. Check account-level bindings if property-level returns empty.

## Credential Storage

| Location | Priority | Use Case |
|----------|----------|----------|
| Environment vars | 1 | CI/CD, automation |
| OS Keyring | 2 | Interactive use |

Environment variables:
- `GA4_ACCESS_TOKEN` - OAuth access token
- `GA4_REFRESH_TOKEN` - OAuth refresh token
- `GA4_CREDENTIALS_PATH` - Path to OAuth client JSON

## Health Checks & Scanning

### Single Property Health

```bash
# Full diagnostic (async prefetch — all API calls concurrent)
ga4 health check 123456789
ga4 health check 123456789 --json | jq '.data.score'

# Category-specific (only fetches needed data)
ga4 health access 123456789        # User access audit
ga4 health tracking 123456789      # Data quality checks
ga4 health summary 123456789       # One-line score
```

### Multi-Property Scanning

```bash
# Scan all properties (3 concurrent workers by default)
ga4 scan all
ga4 scan all --workers 5           # 5 concurrent properties
ga4 scan all --account 123456789   # Filter to one account

# Access audit across all properties
ga4 scan access --json | jq '.data.properties[] | {property_name, score}'

# Only show problems
ga4 scan issues
ga4 scan issues --json | jq '.data.properties[].checks[] | select(.status == "fail")'
```

### Health Check Categories

| Category | Checks | What It Finds |
|----------|--------|---------------|
| tracking | data_recency, realtime, sessions, bounce, not_set | Broken tracking, data gaps |
| access | user_count, admin_count, external_domains, roles | Access sprawl, security |
| config | property_config, custom_dimensions | Missing settings |

### jq Patterns for Health Data

```bash
# Properties scoring below 70
ga4 scan all --json | jq '.data.properties[] | select(.score < 70) | {property_name, score, grade}'

# All failing checks
ga4 health check 123456789 --json | jq '.data.checks[] | select(.status == "fail")'

# Average score across all properties
ga4 scan all --json | jq '.data.overall.avg_score'
```

### Introspection

```bash
ga4 describe --json          # List all resources and actions
ga4 describe --json | jq '.data.resources | keys'
```

## See Also

- [references/api-endpoints.md](references/api-endpoints.md) - Full API endpoint reference
- [references/migration-patterns.md](references/migration-patterns.md) - Complex migration scenarios
