---
name: ga4-access
description: "GA4 user access management, permission audits, and cross-property security. Triggers: ga4 users, add user, remove user, permissions, access audit, role management, user migration."
version: 1.0.0
category: domain
tool: ga4
requires:
  bins: ["ga4"]
  skills: ["ga4-ops"]
related-skills: ["ga4-health"]
allowed-tools: "Read Bash Grep"
---

# GA4 Access Management

Domain skill for managing user access, auditing permissions, and maintaining security across GA4 properties.

## Roles Reference

| Role | API Constant | What They Can Do |
|------|-------------|------------------|
| `viewer` | `predefinedRoles/viewer` | View reports and dashboards |
| `analyst` | `predefinedRoles/analyst` | View reports, create explorations |
| `editor` | `predefinedRoles/editor` | Edit property settings and reports |
| `admin` | `predefinedRoles/admin` | Full control including user management |

Use the short names (`viewer`, `analyst`, `editor`, `admin`) with all CLI commands. The API uses the full constant internally.

## User Management Commands

```bash
# List users on a property
ga4 users list <property_id> --json

# Add a user
ga4 users add <property_id> user@example.com --role analyst
ga4 users add <property_id> user@example.com --role viewer --dry-run

# Remove a user
ga4 users remove <property_id> user@example.com
ga4 users remove <property_id> user@example.com --dry-run

# Copy users between properties
ga4 users copy <src_property> <dest_property> --dry-run
ga4 users copy <src_property> <dest_property>

# Batch add from file
ga4 users batch-add <property_id> users.json --dry-run
ga4 users batch-add <property_id> users.csv
```

Always use `--dry-run` before destructive or bulk operations to preview what will change.

## Account vs Property Level Access

GA4 access can be granted at two levels:

| Level | Scope | CLI |
|-------|-------|-----|
| Account | Inherits to all properties under the account | Managed via Admin API directly (not exposed in `ga4 users`) |
| Property | Single property only | `ga4 users list/add/remove <property_id>` |

**Critical gotcha:** `ga4 users list <property_id>` only returns property-level bindings. If a user has access at the account level, they will not appear in this list even though they have access. Use `ga4 health access <property_id>` or `ga4 scan permissions` to see the full picture including inherited access.

## Permission Auditing

### Single Property Audit

```bash
# Health check focused on access only
ga4 health access <property_id> --json

# What it checks:
# - Total user count
# - Admin user count (flag if > 3)
# - External domain users
# - Role distribution
```

### Cross-Property Permission Matrix

```bash
# Scan all properties for access issues
ga4 scan permissions --json

# Filter to one account
ga4 scan permissions --account <account_id> --json

# Increase concurrency for large accounts
ga4 scan permissions --account <account_id> --workers 5 --json
```

The permission matrix shows every user mapped against every property, highlighting:

| Issue Type | Description |
|------------|-------------|
| `inconsistent_roles` | User has different roles on different properties |
| `partial_access` | User has access to some but not all properties in an account |
| `external_elevated` | User from an external domain has editor or admin on a property |

Account-level inherited bindings are shown with `*` suffix in the human-readable table.

### Reading the JSON Output

```bash
# Summary counts
ga4 scan permissions --json | jq '.data.summary'

# All detected issues
ga4 scan permissions --json | jq '.data.issues[]'

# Users with elevated external access
ga4 scan permissions --json | jq '.data.issues[] | select(.type == "external_elevated")'

# Full matrix for a specific user
ga4 scan permissions --json | jq '.data.users[] | select(.user == "someone@external.com")'
```

## User Migration Workflows

### Copy Between Properties (with Filtering)

```bash
# Preview all users
ga4 users copy <src> <dest> --dry-run

# Copy only analysts
ga4 users copy <src> <dest> --role analyst --dry-run
ga4 users copy <src> <dest> --role analyst

# Exclude outgoing agency accounts
ga4 users copy <src> <dest> --exclude admin@oldagency.com,ops@oldagency.com
```

### Batch Provisioning

**JSON format** (`users.json`):
```json
[
  {"email": "alice@example.com", "role": "analyst"},
  {"email": "bob@example.com", "role": "viewer"},
  {"email": "carol@example.com", "role": "editor"}
]
```

**CSV format** (`users.csv`):
```csv
email,role
alice@example.com,analyst
bob@example.com,viewer
```

```bash
# Validate file before applying
ga4 users batch-add <property_id> users.json --dry-run

# Apply
ga4 users batch-add <property_id> users.json
```

### Export Users from One Property, Import to Another

```bash
# Export current users as JSON ready for batch-add
ga4 users list <src_property> --json \
  | jq '[.data[] | {email: .user, role: .roles[0]}]' > /tmp/users.json

# Review
cat /tmp/users.json

# Import to destination
ga4 users batch-add <dest_property> /tmp/users.json --dry-run
ga4 users batch-add <dest_property> /tmp/users.json
```

## Security Best Practices

**Principle of least privilege:** Default new users to `viewer` or `analyst`. Reserve `editor` for content managers and `admin` for property owners only. Avoid granting `admin` to more than 2–3 users per property.

**Audit external domains regularly:** Use `ga4 scan permissions --json | jq '.data.issues[] | select(.type == "external_elevated")'` to surface contractors or agencies with elevated access that may no longer be active.

**Review role distribution:** A property with many admins is a signal worth investigating.

```bash
ga4 users list <property_id> --json \
  | jq 'group_by(.roles[]) | map({role: .[0].roles[0], count: length})'
```

**Before removing a user:** Always `--dry-run` first to confirm the right binding is targeted. Role names in the API response may differ from display names in the GA4 UI (`predefinedRoles/analyst` vs "Analyst").

## jq Patterns for Access Data

```bash
# List all user emails on a property
ga4 users list <property_id> --json | jq -r '.data[].user'

# Filter to admins only
ga4 users list <property_id> --json \
  | jq '.data[] | select(.roles | contains(["admin"]))'

# Count users by role
ga4 users list <property_id> --json \
  | jq '[.data[].roles[]] | group_by(.) | map({role: .[0], count: length})'

# Export user list as CSV
ga4 users list <property_id> --json \
  | jq -r '.data[] | [.user, (.roles | join(";"))] | @csv'

# Find users with access to multiple properties (from permissions scan)
ga4 scan permissions --json \
  | jq '.data.users[] | select((.properties | length) > 1) | .user'
```

## Gotchas

**Empty user list on a property:** Not necessarily a bug. If `ga4 users list` returns empty, the property may have users inherited from account-level bindings. Use `ga4 health access` to verify.

**Role names in API vs UI:** The CLI uses short names (`viewer`, `analyst`, `editor`, `admin`). The raw API returns `predefinedRoles/analyst` etc. jq filters on the raw output need to match the full constant; the `ga4 users list` command normalises these to short names in its JSON output.

**External domain detection:** `ga4 scan permissions` determines "external" by comparing domains within a property. The most common domain is assumed to be the primary. In multi-brand accounts this heuristic can produce false positives — review `external_elevated` issues manually.

**Batch API limit:** The GA4 Admin API batch create endpoint accepts up to 1000 bindings per call. Files passed to `batch-add` beyond this size will be split internally.

**Account-level inheritance in the matrix:** The `*` marker in `scan permissions` output means the binding was inherited from account level, not set directly on the property. Removing it requires account-level access that is not yet exposed via the `ga4 users` commands.
