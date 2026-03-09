# ga4 - Development Plan

## Current State (v0.1.0)

### Completed

- [x] Basic CLI structure (Typer + Fabric Protocol)
- [x] OAuth2 authentication flow (login, status, logout)
- [x] Credential storage (OS keyring + env var override)
- [x] Token refresh handling
- [x] Analytics Admin API client (`admin_client.py`)
- [x] Accounts: list
- [x] Properties: list, get (with account filtering)
- [x] Users: list, add, remove, copy, batch-add
- [x] Account-level access binding support
- [x] Error handling with semantic exit codes
- [x] JSON output with `{data, meta}` shape
- [x] Rich table output for human-readable mode
- [x] ga4-ops skill for CLI usage patterns

### Recently Completed

- [x] Analytics Data API client (`client.py` rewritten)
- [x] Dimensions: list, get (property-scoped, real API)
- [x] Metrics: list, get (property-scoped, real API)
- [x] Reports: run (custom reports with dimensions/metrics/date range)
- [x] Reports: realtime (live visitor data)
- [x] Health check engine (`checks.py`) with 11 checks across tracking/access/config
- [x] `ga4 health` commands: check, access, tracking, summary
- [x] `ga4 scan` commands: all, access, issues (multi-property)
- [x] `ga4 describe` introspection command (Fabric Protocol)
- [x] `--dry-run` on `users add` and `users remove`
- [x] Rate limit handling (exit code 6) in both API clients

## Next Steps

1. [ ] Write comprehensive tests
2. [ ] Add `users list-account` command for account-level bindings
3. [ ] Register with Fabric (`fabric sync`)
4. [ ] Add `--quiet` and `--verbose` flags (Fabric Protocol)
5. [ ] Add `--fields` flag for field filtering (Fabric Protocol)

## API Details

| API | Base URL | Purpose |
|-----|----------|---------|
| Analytics Admin | `analyticsadmin.googleapis.com/v1beta` | Accounts, properties, users |
| Analytics Admin (alpha) | `analyticsadmin.googleapis.com/v1alpha` | Access bindings |
| Analytics Data | `analyticsdata.googleapis.com/v1beta` | Reports, dimensions, metrics |

## Architecture

```
src/ga4/
├── __init__.py        # Version
├── cli.py             # Typer CLI commands
├── config.py          # OAuth2 + credential storage
├── client.py          # Data API (placeholder)
└── admin_client.py    # Admin API (implemented)
```

## Notes

- User access can be at Account or Property level
- Property-level lists may be empty if access is granted at Account level
- Copy command useful for Looker Studio migrations between orgs
