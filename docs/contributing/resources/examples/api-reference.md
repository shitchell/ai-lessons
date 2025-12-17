# API Reference Template

Use this template for documenting APIs, libraries, or any reference material with multiple discrete items (endpoints, functions, methods, etc.).

---

## Template

```markdown
# [API/Library Name] Reference

Brief description of what this API/library does and when to use it.

## [Endpoint/Function Name]

**Method:** `GET /path/to/endpoint` (or function signature)

**When to use:** One sentence describing the use case.

[2-3 sentence description of what this does and any important behavior.]

### Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `param1` | string | Yes | What this parameter controls |
| `param2` | integer | No | Optional parameter (default: 10) |

### Response

```json
{
  "field1": "Description of field1",
  "field2": 123
}
```

### Example

```bash
curl -X GET "https://api.example.com/endpoint?param1=value"
```

### Notes

- Important gotcha or edge case
- Another important consideration

---

## [Next Endpoint/Function]

...
```

---

## Example: Jira Workflows API

```markdown
# Jira Workflows API Reference

API for creating, reading, updating, and deleting Jira workflows. Use the v3 API for all new integrations.

## Get Workflow

**Method:** `GET /rest/api/3/workflow/search`

**When to use:** Retrieve workflow details by name or ID, including statuses and transitions.

Returns paginated workflow data. Use `workflowName` for exact match or `queryString` for partial search.

### Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `workflowName` | string | No | Exact workflow name to retrieve |
| `queryString` | string | No | Partial match search |
| `expand` | string | No | Include additional data: `transitions`, `statuses`, `operations` |

### Response

```json
{
  "values": [
    {
      "id": "workflow-id",
      "name": "My Workflow",
      "statuses": [...],
      "transitions": [...]
    }
  ],
  "isLast": true
}
```

### Example

```bash
jira get "/rest/api/3/workflow/search?workflowName=My%20Workflow&expand=transitions,statuses"
```

### Notes

- Results are paginated; check `isLast` field
- `expand` parameter significantly increases response size

---

## Update Workflows (Bulk)

**Method:** `POST /rest/api/3/workflows/update`

**When to use:** Modify existing workflows. Required for changing transitions, conditions, or statuses.

Updates one or more workflows atomically. The payload must include ALL statuses and transitions for each workflow—omitted items are deleted.

### Parameters

Request body:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `workflows` | array | Yes | Array of workflow update objects |
| `workflows[].version` | object | Yes | Version info for optimistic locking |
| `workflows[].statuses` | array | Yes | Complete list of statuses |
| `workflows[].transitions` | array | Yes | Complete list of transitions |

### Example

```bash
jira post -d '{
  "workflows": [{
    "version": {"versionNumber": 1, "id": "workflow-id"},
    "statuses": [...],
    "transitions": [...]
  }]
}' /rest/api/3/workflows/update
```

### Notes

- **Critical:** You must include ALL statuses and transitions. Omitted items are deleted.
- Always GET the current workflow first to preserve existing items
- Use `version.versionNumber` from the GET response for optimistic locking
```

---

## Why This Structure Works

1. **Each endpoint = one chunk** - Self-contained, searchable by endpoint name
2. **"When to use" upfront** - Helps embeddings capture intent
3. **Parameters table** - Structured, scannable
4. **Example inline** - Not in a separate section
5. **Notes for gotchas** - Critical info that might match "why doesn't X work" queries
