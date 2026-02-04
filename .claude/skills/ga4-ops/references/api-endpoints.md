# GA4 API Endpoints Reference

## APIs Used

| API | Base URL | Purpose |
|-----|----------|---------|
| Analytics Admin API | `analyticsadmin.googleapis.com/v1beta` | Accounts, properties |
| Analytics Admin API (Alpha) | `analyticsadmin.googleapis.com/v1alpha` | Access bindings |
| Analytics Data API | `analyticsdata.googleapis.com/v1beta` | Reports, metrics |

## OAuth Scopes

```
https://www.googleapis.com/auth/analytics.readonly
https://www.googleapis.com/auth/analytics.manage.users
```

## Account Endpoints

### List Accounts
```
GET /v1beta/accounts
```

**Response:**
```json
{
  "accounts": [
    {
      "name": "accounts/123456789",
      "displayName": "My Account",
      "createTime": "2020-01-15T10:30:00Z",
      "updateTime": "2024-06-01T14:22:00Z"
    }
  ],
  "nextPageToken": "..."
}
```

## Property Endpoints

### List Properties
```
GET /v1beta/properties
  ?filter=parent:accounts/{account_id}
  &pageSize=200
```

### Get Property
```
GET /v1beta/properties/{property_id}
```

**Response fields:**
- `name` - Resource name (properties/123456789)
- `displayName` - Human-readable name
- `account` - Parent account
- `createTime`, `updateTime` - Timestamps
- `timeZone` - Reporting timezone
- `currencyCode` - Currency for revenue
- `industryCategory` - Business category

## Access Binding Endpoints (Alpha API)

### List Property Access Bindings
```
GET /v1alpha/properties/{property_id}/accessBindings
  ?pageSize=200
```

### Create Property Access Binding
```
POST /v1alpha/properties/{property_id}/accessBindings

{
  "user": "email@example.com",
  "roles": ["predefinedRoles/analyst"]
}
```

### Delete Property Access Binding
```
DELETE /v1alpha/properties/{property_id}/accessBindings/{binding_id}
```

### Batch Create Access Bindings
```
POST /v1alpha/properties/{property_id}/accessBindings:batchCreate

{
  "requests": [
    {
      "accessBinding": {
        "user": "user1@example.com",
        "roles": ["predefinedRoles/viewer"]
      }
    },
    {
      "accessBinding": {
        "user": "user2@example.com",
        "roles": ["predefinedRoles/analyst"]
      }
    }
  ]
}
```

### Account-Level Access Bindings

Same pattern as property bindings:

```
GET  /v1alpha/accounts/{account_id}/accessBindings
POST /v1alpha/accounts/{account_id}/accessBindings
DELETE /v1alpha/accounts/{account_id}/accessBindings/{binding_id}
```

Account-level access cascades to all properties under that account.

## Role Mapping

| CLI Role | API Role |
|----------|----------|
| viewer | predefinedRoles/viewer |
| analyst | predefinedRoles/analyst |
| editor | predefinedRoles/editor |
| admin | predefinedRoles/admin |

## Pagination

All list endpoints support pagination:

```
?pageSize=200
&pageToken={nextPageToken}
```

The CLI handles pagination automatically, fetching all results up to the specified limit.

## Rate Limits

Google Analytics Admin API:
- 600 requests per minute per project
- 10 requests per second per user

When hitting rate limits, implement exponential backoff.

## Error Responses

```json
{
  "error": {
    "code": 403,
    "message": "The caller does not have permission",
    "status": "PERMISSION_DENIED"
  }
}
```

| HTTP Code | Meaning | CLI Exit Code |
|-----------|---------|---------------|
| 401 | Unauthorized | 2 |
| 403 | Forbidden | 5 |
| 404 | Not Found | 3 |
| 400 | Bad Request | 4 |
| 429 | Rate Limited | 6 |
