# Troubleshooting Guide Template

Use this template for error resolution guides and debugging documentation.

---

## Template

```markdown
# Troubleshooting [System/Feature Name]

Common issues and solutions for [system/feature]. Search for your error message or symptom below.

## Error: [Exact Error Message]

**Symptoms:** What the user sees or experiences.

**Cause:** Why this error occurs.

**Solution:**

1. First step to resolve
2. Second step if needed
3. Third step if needed

```bash
# Command to fix (if applicable)
fix-command --option value
```

**Prevention:** How to avoid this in the future.

---

## Error: [Another Error Message]

...

---

## Symptom: [Description When No Clear Error]

**What you see:** Description of the unexpected behavior.

**Possible causes:**

1. **Cause A** - How to identify and fix
2. **Cause B** - How to identify and fix

**Diagnostic steps:**

```bash
# Commands to help diagnose
diagnostic-command
```

---

## Still Stuck?

- Check [related documentation]
- Search existing issues: [link]
- Ask for help: [channel/forum]
```

---

## Example: Jira API Troubleshooting

```markdown
# Troubleshooting Jira API

Common errors when working with the Jira REST API and how to resolve them.

## Error: 400 Bad Request - "Workflow scheme is locked"

**Symptoms:** API returns 400 when updating a workflow scheme.

**Cause:** Another process or user has a lock on the workflow scheme. Jira uses optimistic locking—your request included a stale version number.

**Solution:**

1. Fetch the current workflow scheme to get the latest version:
   ```bash
   jira get /rest/api/3/workflowscheme/SCHEME_ID
   ```

2. Note the `version.versionNumber` in the response

3. Retry your update with the new version number

**Prevention:** Always fetch the latest version immediately before making updates. Don't cache workflow scheme data.

---

## Error: 400 Bad Request - "Status mapping required"

**Symptoms:** Workflow scheme update fails with message about status mappings.

**Cause:** Issues exist in statuses that don't exist in the new workflow. Jira needs to know where to move these issues.

**Solution:**

1. Identify which statuses need mapping (listed in error response)

2. Add `statusMappingsByIssueTypeOverride` to your request:
   ```json
   {
     "statusMappingsByIssueTypeOverride": {
       "10001": {
         "oldStatusId": "newStatusId",
         "anotherOldId": "anotherNewId"
       }
     }
   }
   ```

3. Status IDs map FROM old workflow TO new workflow (not reverse)

**Prevention:** When changing workflows, audit existing issues first:
```bash
jira post -d '{"jql":"project=PROJ AND status in (\"Status A\", \"Status B\")"}' /search/jql
```

---

## Error: 403 Forbidden

**Symptoms:** API returns 403 for any request.

**Cause:** Usually one of:
1. Invalid or expired API token
2. Insufficient permissions for the operation
3. IP restrictions on the Atlassian account

**Solution:**

1. **Verify authentication:**
   ```bash
   jira get /rest/api/3/myself
   ```
   If this fails, re-authenticate: `jira auth login`

2. **Check permissions:** Ensure your account has admin access for the target project

3. **Check IP allowlist:** In Atlassian admin, verify your IP is allowed

---

## Symptom: Workflow Changes Not Taking Effect

**What you see:** You updated a workflow via API, but issues still show old transitions.

**Possible causes:**

1. **Draft vs Active** - Changes went to a draft workflow
   - Check: Look for `draft: true` in workflow response
   - Fix: Publish the draft workflow

2. **Wrong workflow scheme** - Updated the wrong scheme
   - Check: `jira get /rest/api/3/project/PROJ` shows `workflowScheme`
   - Fix: Update the correct scheme

3. **Caching** - Jira UI caches workflow data
   - Check: API shows correct data but UI doesn't
   - Fix: Hard refresh browser, or wait 5 minutes

**Diagnostic steps:**

```bash
# Get the workflow scheme for a project
jira get /rest/api/3/project/PROJ | jq '.workflowScheme'

# Get workflow assignments in that scheme
jira get /rest/api/3/workflowscheme/SCHEME_ID
```

---

## Still Stuck?

- Check [Jira API Documentation](https://developer.atlassian.com/cloud/jira/platform/rest/v3/)
- Search [Atlassian Community](https://community.atlassian.com/)
- Review scripts in `~/.claude/skills/jira-api-docs/scripts/` for working examples
```

---

## Why This Structure Works

1. **Error messages as headers** - Direct match for copy-pasted errors
2. **Symptoms first** - Helps users confirm they have the right issue
3. **Cause explained** - Understanding prevents repeat errors
4. **Numbered solutions** - Clear action path
5. **Prevention tip** - Reduces future occurrences
6. **Fallback section** - When nothing else works
