# GA4 Migration Patterns

Complex migration scenarios for GA4 user management.

## Looker Studio Migration (Agency Transition)

**Scenario:** Client moving from Agency A to Agency B. Looker Studio dashboards need GA4 access transferred.

### Phase 1: Audit Current State

```bash
# List all current users on source property
ga4 users list 123456789 --json > current_users.json

# Review the list
jq '.data[] | {email: .user, roles}' current_users.json

# Count by role
jq '[.data[].roles[]] | group_by(.) | map({role: .[0], count: length})' current_users.json
```

### Phase 2: Prepare User List

```bash
# Filter to only viewers (Looker Studio access)
jq '[.data[] | select(.roles | contains(["viewer"])) | {email: .user, role: "viewer"}]' current_users.json > migrate_users.json

# Exclude agency A emails
jq '[.[] | select(.email | contains("@agencyA.com") | not)]' migrate_users.json > final_users.json
```

### Phase 3: Grant Access on New Property

```bash
# Dry run first
ga4 users batch-add 987654321 final_users.json --dry-run

# Execute
ga4 users batch-add 987654321 final_users.json
```

### Phase 4: Verify

```bash
# Compare user counts
ga4 users list 987654321 --json | jq '.meta.count'
```

## Multi-Property Rollout

**Scenario:** Add a new team member to multiple properties.

### Using Shell Loop

```bash
# Properties file (one ID per line)
cat > properties.txt << EOF
123456789
234567890
345678901
EOF

# Add user to all properties
while read prop_id; do
  echo "Adding to property $prop_id..."
  ga4 users add "$prop_id" newuser@company.com --role analyst
done < properties.txt
```

### Using jq + xargs

```bash
# Get all property IDs and add user to each
ga4 properties list --json | jq -r '.data[].id' | \
  xargs -I {} ga4 users add {} newuser@company.com --role analyst
```

## Role Upgrade Campaign

**Scenario:** Upgrade all viewers to analysts on a property.

```bash
# Get current viewers
ga4 users list 123456789 --json | \
  jq -r '.data[] | select(.roles | contains(["viewer"])) | .user' > viewers.txt

# Remove viewer access, add analyst access
while read email; do
  ga4 users remove 123456789 "$email"
  ga4 users add 123456789 "$email" --role analyst
done < viewers.txt
```

## Cross-Account Migration

**Scenario:** Move users from properties in Account A to properties in Account B.

### Map Source to Destination Properties

```bash
# Create mapping file
cat > property_map.csv << EOF
source_id,dest_id
123456789,987654321
234567890,876543210
EOF
```

### Execute Migration

```bash
# Process each mapping
while IFS=, read -r src dest; do
  [[ "$src" == "source_id" ]] && continue  # Skip header
  echo "Migrating users from $src to $dest..."
  ga4 users copy "$src" "$dest" --dry-run
done < property_map.csv

# After review, remove --dry-run
```

## Cleanup: Remove Departed Users

**Scenario:** Remove users from a domain that no longer needs access.

```bash
# Find users from specific domain
ga4 users list 123456789 --json | \
  jq -r '.data[] | select(.user | contains("@olddomain.com")) | .user' > remove.txt

# Remove each user
while read email; do
  echo "Removing $email..."
  ga4 users remove 123456789 "$email"
done < remove.txt
```

## Audit: Who Has Access Where?

**Scenario:** Generate compliance report of all access across all properties.

```bash
# Create audit report
echo "property_id,property_name,user,roles" > audit.csv

ga4 properties list --json | jq -r '.data[] | "\(.id),\(.name)"' | \
while IFS=, read -r prop_id prop_name; do
  ga4 users list "$prop_id" --json 2>/dev/null | \
    jq -r --arg pid "$prop_id" --arg pname "$prop_name" \
    '.data[] | [$pid, $pname, .user, (.roles | join(";"))] | @csv' >> audit.csv
done

# View summary
column -t -s, audit.csv | head -20
```

## Sync Users Between Properties

**Scenario:** Keep two properties in sync (e.g., staging and production).

```bash
SOURCE=123456789
DEST=987654321

# Get users from both
ga4 users list $SOURCE --json | jq '[.data[] | {email: .user, role: .roles[0]}]' > source_users.json
ga4 users list $DEST --json | jq -r '.data[].user' > dest_emails.txt

# Find users in source not in dest
jq -r '.[].email' source_users.json | while read email; do
  if ! grep -q "^$email$" dest_emails.txt; then
    role=$(jq -r --arg e "$email" '.[] | select(.email == $e) | .role' source_users.json)
    echo "Adding $email as $role to dest..."
    ga4 users add $DEST "$email" --role "$role"
  fi
done
```

## Rollback Pattern

Always capture state before bulk operations:

```bash
# Before migration
ga4 users list 123456789 --json > backup_$(date +%Y%m%d_%H%M%S).json

# If rollback needed, restore from backup
jq '[.data[] | {email: .user, role: .roles[0]}]' backup_*.json > restore.json
ga4 users batch-add 123456789 restore.json
```
