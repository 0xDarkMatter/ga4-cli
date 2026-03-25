# AI Traffic Channel Groups

## Problem

AI platforms (ChatGPT, Claude, Gemini, Copilot, Perplexity, etc.) are driving an increasing share of website referral traffic. By default, GA4 lumps this traffic into the **Referral** channel alongside all other referring domains, making it invisible in standard channel reports.

## Solution

Create a custom channel group that adds an **AI Traffic** channel to capture visits from known AI platforms. The channel must be ordered **above Referral** because GA4 evaluates channel rules top-to-bottom — if Referral is higher, AI traffic gets caught there first.

## API Limitation (March 2026)

The GA4 Admin API (`v1alpha`) only accepts `eachScopeDefaultChannelGroup` as a filter field in custom channel groups. Other fields documented elsewhere (`sessionSource`, `sessionMedium`, etc.) are **rejected** with `unsupported-channel-grouping-field`.

This means:
- **Via API**: The AI Traffic channel matches ALL Referral traffic (not just AI sources)
- **Via GA4 UI**: Full source-level filtering works — use the regex below to target only AI domains
- **Recommended workflow**: Create the channel group via API, then edit it in the GA4 UI to apply the source regex

## Implementation

### Quick Start (CLI)

```bash
# Preview what will be created (dry run)
ga4 channels create 309144142 --template ai-traffic --dry-run

# Create (matches all Referral traffic via API)
ga4 channels create 309144142 --template ai-traffic

# Then edit in GA4 UI to apply source-level regex for AI-only filtering
```

### What the Template Does

1. Fetches the property's system-defined default channel group (all 18 standard channels)
2. Re-expresses each channel using `eachScopeDefaultChannelGroup` (API-compatible)
3. Inserts an **AI Traffic** channel immediately above **Referral**
4. Creates a new custom channel group named "Default + AI Traffic"

### The Regex (for GA4 UI)

After creating the channel group via API, edit the AI Traffic channel in the GA4 UI and set the condition to `sessionSource` matches regex:

```
chatgpt\.com|chat\.openai\.com|claude\.ai|perplexity\.ai|pplx\.ai
|gemini\.google\.com|copilot\.microsoft\.com|edgepilot|edgeservices
|deepseek\.com|meta\.ai|grok\.com|you\.com|phind\.com|poe\.com
|chat\.mistral\.ai
```

| Domain | Platform |
|--------|----------|
| `chatgpt.com` | OpenAI ChatGPT |
| `chat.openai.com` | OpenAI ChatGPT (legacy) |
| `claude.ai` | Anthropic Claude |
| `perplexity.ai` | Perplexity |
| `pplx.ai` | Perplexity (short links) |
| `gemini.google.com` | Google Gemini |
| `copilot.microsoft.com` | Microsoft Copilot |
| `edgepilot` | Edge built-in Copilot |
| `edgeservices` | Edge services referrer |
| `deepseek.com` | DeepSeek |
| `meta.ai` | Meta AI |
| `grok.com` | xAI Grok |
| `you.com` | You.com AI search |
| `phind.com` | Phind (developer AI) |
| `poe.com` | Quora Poe |
| `chat.mistral.ai` | Mistral AI |

### Channel Ordering

```
 1. Direct
 2. Cross-network
 3. Paid Shopping
 4. Paid Search
 5. Paid Social
 6. Paid Video
 7. Display
 8. AI Traffic          ← inserted here, ABOVE Referral
 9. Organic Shopping
10. Organic Search
11. Organic Social
12. Organic Video
13. Email
14. Affiliates
15. Referral            ← AI domains would fall here without the custom channel
16. Audio
17. SMS
18. Mobile Push Notifications
19. (Other)
```

## Layer 1 vs Layer 2

This implementation covers **Layer 1: GA4 Custom AI Channel Group**.

| Layer | What It Captures | Cost |
|-------|-----------------|------|
| **Layer 1** (this) | AI referral traffic — humans who click through from AI platforms | Free |
| **Layer 2** (future) | AI bot/crawler visits that don't execute JavaScript | Requires server-side log analysis |

GA4 relies on JavaScript execution, so it can only see visitors who render the page in a browser. AI crawlers that fetch pages without rendering JS (GPTBot, ClaudeBot, Google-Extended) are invisible to GA4 and require server log analysis.

## Schema Integration

Channel groups are included in schema export/deploy:

```bash
# Export property schema (includes custom channel groups)
ga4 schema export 309144142 -o roam-schema.json

# Deploy to new property (creates channel groups)
ga4 schema deploy roam-schema.json --account 16621930 \
  --name "newsite.com.au - GA4" --url "https://www.newsite.com.au"

# Deploy to existing property (skips if group name already exists)
ga4 schema deploy roam-schema.json --property 461067940
```

## Updating the Regex

After editing the channel group in the GA4 UI to use source-level filtering:

```bash
# Export current channel group
ga4 channels export 309144142 <group-id> -o ai-traffic.json

# Edit ai-traffic.json to add new domains to the regex

# Update the channel group
ga4 channels update 309144142 <group-id> --from-file ai-traffic.json
```

## Health Check

The `ga4 health check` command includes a `channel_groups` config check that warns if no custom channel groups are configured, with a suggestion to add AI agent tracking.

## Limitations

- Standard GA4 properties support **max 2 custom channel groups**
- GA360 properties support up to 50
- **API limitation**: The GA4 Admin API only supports `eachScopeDefaultChannelGroup` as a filter field — `sessionSource`, `sessionMedium`, etc. are rejected. Use the GA4 UI for source-level filtering.
- The `edgepilot` and `edgeservices` entries don't include a TLD because Edge uses these as partial referrer strings
