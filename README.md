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

ga4 properties list

ga4 reports list

ga4 dimensions list

ga4 metrics list

```

## Usage

```bash
# List with JSON output
ga4 properties list --json

# Get specific item
ga4 properties get <id> --json

# Filter results
ga4 properties list --limit 10 --json
```

## Commands

| Command | Description |
|---------|-------------|

| `ga4 properties list` | List properties |
| `ga4 properties get <id>` | Get specific propertie |

| `ga4 reports list` | List reports |
| `ga4 reports get <id>` | Get specific report |

| `ga4 dimensions list` | List dimensions |
| `ga4 dimensions get <id>` | Get specific dimension |

| `ga4 metrics list` | List metrics |
| `ga4 metrics get <id>` | Get specific metric |


## Authentication

```bash
ga4 auth login   # Authenticate
ga4 auth status  # Check status
ga4 auth logout  # Clear credentials
```

## JSON Output

All commands support `--json` for machine-readable output:

```bash
ga4 properties list --json | jq '.data[0]'
```

## Protocol

This tool follows the [Fabric Protocol](../00_Fabric/docs/FABRIC_PROTOCOL.md).
