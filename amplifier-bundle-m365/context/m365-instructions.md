# M365 Tool Usage Instructions

## Authentication Flow

When M365 access is needed:

1. Check authentication status first with `m365_auth` operation `status`
2. If not authenticated, call `m365_auth` operation `login`
3. The user will receive a device code and URL to complete authentication in their browser
4. Once authenticated, tokens are cached and will auto-refresh

## Common Graph API Patterns

### Get Current User Profile
```json
{
  "endpoint": "/me",
  "method": "GET"
}
```

### List Emails (with filtering)
```json
{
  "endpoint": "/me/messages",
  "method": "GET",
  "params": {
    "$select": "subject,from,receivedDateTime,isRead",
    "$filter": "isRead eq false",
    "$top": "10",
    "$orderby": "receivedDateTime desc"
  }
}
```

### Read Specific Email
```json
{
  "endpoint": "/me/messages/{message-id}",
  "method": "GET",
  "params": {
    "$select": "subject,body,from,toRecipients"
  }
}
```

### Send Email
```json
{
  "endpoint": "/me/sendMail",
  "method": "POST",
  "body": {
    "message": {
      "subject": "Test Email",
      "body": {
        "contentType": "Text",
        "content": "Hello from Amplifier!"
      },
      "toRecipients": [
        {
          "emailAddress": {
            "address": "recipient@example.com"
          }
        }
      ]
    }
  }
}
```

### List Calendar Events
```json
{
  "endpoint": "/me/calendar/events",
  "method": "GET",
  "params": {
    "$select": "subject,start,end,location",
    "$filter": "start/dateTime ge '2025-01-16T00:00:00'",
    "$orderby": "start/dateTime",
    "$top": "10"
  }
}
```

### Create Calendar Event
```json
{
  "endpoint": "/me/calendar/events",
  "method": "POST",
  "body": {
    "subject": "Meeting with Team",
    "start": {
      "dateTime": "2025-01-17T14:00:00",
      "timeZone": "UTC"
    },
    "end": {
      "dateTime": "2025-01-17T15:00:00",
      "timeZone": "UTC"
    },
    "attendees": [
      {
        "emailAddress": {
          "address": "attendee@example.com"
        },
        "type": "required"
      }
    ]
  }
}
```

### List OneDrive Files
```json
{
  "endpoint": "/me/drive/root/children",
  "method": "GET",
  "params": {
    "$select": "name,size,lastModifiedDateTime,folder,file"
  }
}
```

### List Directory Users (Admin)
```json
{
  "endpoint": "/users",
  "method": "GET",
  "params": {
    "$select": "displayName,mail,userPrincipalName",
    "$top": "25"
  },
  "paginate": true
}
```

## OData Query Parameters

The Graph API supports OData query parameters:

| Parameter | Description | Example |
|-----------|-------------|---------|
| `$select` | Choose specific properties | `subject,from,receivedDateTime` |
| `$filter` | Filter results | `isRead eq false` |
| `$orderby` | Sort results | `receivedDateTime desc` |
| `$top` | Limit results | `10` |
| `$skip` | Skip results (pagination) | `20` |
| `$count` | Include count | `true` |
| `$expand` | Include related entities | `attachments` |
| `$search` | Full-text search | `"urgent"` |

## Error Handling

Common Graph API errors:

| Error Code | Meaning | Action |
|------------|---------|--------|
| `401 Unauthorized` | Token expired or invalid | Re-authenticate with `m365_auth login` |
| `403 Forbidden` | Insufficient permissions | Check required scopes |
| `404 Not Found` | Resource doesn't exist | Verify endpoint and IDs |
| `429 Too Many Requests` | Rate limited | Wait and retry |

## Best Practices

1. **Use $select** - Only request the fields you need to reduce response size
2. **Use $filter** - Filter on the server side rather than fetching all and filtering locally
3. **Use $top** - Limit results when you only need a few items
4. **Paginate for large sets** - Use `paginate: true` when you need all items from a collection
5. **Check authentication** - Verify auth status before making requests to provide better UX
