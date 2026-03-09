---
name: ga4-ops
description: "Google Analytics 4 CLI for property management, health checks, and user access. Triggers: ga4, google analytics, property access, analytics users, grant access."
version: 2.0.0
category: operations
tool: ga4
requires:
  bins: ["ga4"]
allowed-tools: "Read Bash Grep"
---

# GA4 Operations

CLI tool for Google Analytics 4 property management, user access control, and property health.

## Auth Check

```bash
ga4 auth status --json                          # Check active profile
ga4 --profile analytics auth status --json      # Check named profile
ga4 auth list                                   # Show all profiles
```

## Profile Management

```bash
ga4 auth login                                  # Default profile
ga4 auth login --profile analytics             # Named profile
ga4 auth logout --profile analytics

export GA4_PROFILE=analytics                    # Set default via env var
```

## Common Operations

### Accounts and Properties

```bash
ga4 accounts list --json
ga4 properties list --json
ga4 properties list --account <account-id> --json
ga4 properties get <property-id> --json

# Filter with jq
ga4 properties list --json | jq '.data[] | {id, name}'
ga4 properties list --json | jq -r '.data[] | select(.name | contains("Production")) | .id'
```

### User Management

```bash
ga4 users list <property-id> --json
ga4 users add <property-id> user@example.com --role viewer
ga4 users remove <property-id> user@example.com
ga4 users copy <src-id> <dest-id> [--dry-run]
ga4 users copy <src-id> <dest-id> --role analyst --exclude admin@old.com
ga4 users batch-add <property-id> users.csv [--dry-run]
```

### Health Check

```bash
ga4 health check <property-id>
ga4 health check <property-id> --json | jq '.data.score'
```

See `ga4-health` skill for full diagnostic workflows.

### Multi-Property Scan

```bash
ga4 scan all
ga4 scan issues
ga4 scan report
```

See `ga4-health` skill for scan workflows and score interpretation.

### Cache Management

```bash
ga4 cache status
ga4 cache clear
ga4 health check <property-id> --no-cache      # Skip cache for fresh data
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

## Output Fields

All commands return a `{data, meta}` envelope:

```json
{
  "data": [...],
  "meta": {
    "total": 42,
    "cached": true,
    "cache_age_seconds": 120
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `data` | array/object | The primary result payload |
| `meta.total` | int | Total record count (before any limit) |
| `meta.cached` | bool | Whether result came from cache |
| `meta.cache_age_seconds` | int | Age of cached response in seconds |

## Gotchas

- **Rate limits**: GA4 Admin API is quota-limited. Use cache (default TTL: 1 hour) and avoid `--no-cache` in loops.
- **Account vs property access**: Users granted at account level do not appear in property-level listings. If `users list` returns empty, check account-level bindings.
- **Token expiry**: OAuth tokens expire. Run `ga4 auth status` before long operations; re-auth with `ga4 auth login` if needed.
- **Cache TTL**: Default 1-hour cache means newly added users/properties may not appear immediately. Use `ga4 cache clear` or `--no-cache` to force fresh data.
- **Multi-profile**: When managing multiple clients, always specify `--profile` or set `GA4_PROFILE` to avoid cross-account mutations.
- **Dry-run first**: `--dry-run` is available on `users copy` and `users batch-add`. Always use it before executing bulk changes.

## Pipe Patterns

| Chain | Command | Use Case |
|-------|---------|----------|
| → jq | `ga4 properties list --json \| jq '.data[] \| {id, name}'` | Extract/filter properties |
| → jq | `ga4 users list <id> --json \| jq -r '.data[].user'` | Export user list |
| → fslack | `ga4 scan issues --json \| fslack messages send --channel analytics-alerts` | Alert on failing properties |
| → gsc | `ga4 properties list --json \| jq -r '.data[].id'` then `gsc sites list` | Cross-reference GA4 + GSC properties |
| ← gsc | `gsc analytics --json \| ga4 ...` | Combine search + analytics data |
| → file | `ga4 users list <id> --json \| jq '[.data[] \| {email: .user, role: .roles[0]}]' > users.json` | Export for batch-add |

## Bulk User Provisioning

**CSV format** (`users.csv`):
```csv
email,role
alice@example.com,analyst
bob@example.com,viewer
```

**JSON format** (`users.json`):
```json
[
  {"email": "alice@example.com", "role": "analyst"},
  {"email": "bob@example.com", "role": "viewer"}
]
```

```bash
ga4 users batch-add <property-id> users.csv --dry-run
ga4 users batch-add <property-id> users.csv
```

## See Also

- `ga4-health` — Property health diagnostics, scoring, and site spider
- [references/api-endpoints.md](references/api-endpoints.md) — Full API endpoint reference
- [references/migration-patterns.md](references/migration-patterns.md) — Complex migration scenarios
