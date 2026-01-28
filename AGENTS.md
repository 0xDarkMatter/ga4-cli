# ga4 - AI Assistant Context

## Purpose

Google Analytics 4 reporting and data analysis

## Commands

| Command | Description |
|---------|-------------|
| `ga4 auth login` | Authenticate |
| `ga4 auth status [--json]` | Check auth status |
| `ga4 auth logout` | Clear credentials |

| `ga4 properties list [--json]` | List properties |
| `ga4 properties get <id> [--json]` | Get specific propertie |

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

```bash
# List and filter
ga4 properties list --limit 10 --json

# Get by ID
ga4 properties get <id> --json

# Chain with jq
ga4 properties list --json | jq '.data[].id'
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 2 | Auth required |
| 3 | Not found |
| 4 | Validation error |

## Protocol

Follows [Fabric Protocol](../00_Fabric/docs/FABRIC_PROTOCOL.md).
