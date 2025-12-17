# How-To Guide Template

Use this template for task-oriented guides that help users accomplish a specific goal.

---

## Template

```markdown
# How to [Accomplish Task]

Brief description of what this guide helps you do and when you'd need it.

## Prerequisites

- Requirement 1 (e.g., "API access configured")
- Requirement 2 (e.g., "Admin permissions on the project")

## Steps

### 1. [First Action]

[Brief explanation of what this step does and why.]

```bash
# Command or code for this step
example-command --flag value
```

**Expected result:** What you should see if this worked.

### 2. [Second Action]

[Explanation.]

```bash
another-command
```

### 3. [Third Action]

[Explanation.]

## Verification

How to confirm the task completed successfully:

```bash
# Command to verify
check-status --resource my-resource
```

You should see: [expected output]

## Common Issues

### Issue: [Error message or symptom]

**Cause:** Why this happens.

**Solution:** How to fix it.

## Related

- [Link to related how-to]
- [Link to relevant reference docs]
```

---

## Example: Duplicating a Jira Workflow

```markdown
# How to Duplicate a Jira Workflow

Copy an existing workflow to a new project/issue-type combination, preserving all statuses, transitions, and conditions.

## Prerequisites

- Jira API access configured (`jira auth login`)
- Admin permissions on target project
- Source workflow must be active (not in draft state)

## Steps

### 1. Identify the Source Workflow

Find the workflow currently assigned to your source project and issue type:

```bash
~/.claude/skills/jira-api-docs/scripts/fetch-workflow-table.sh SOURCE_PROJECT Bug
```

Note the workflow ID from the output.

### 2. Run the Duplication Script

```bash
~/.claude/skills/jira-api-docs/scripts/duplicate-workflow.sh \
  --source-project SOURCE_PROJECT \
  --source-issue-type Bug \
  --target-project TARGET_PROJECT \
  --target-issue-type Bug \
  --dry-run  # Preview first
```

Review the dry-run output, then run without `--dry-run` to execute.

### 3. Verify the Assignment

Confirm the workflow is assigned to the target:

```bash
~/.claude/skills/jira-api-docs/scripts/fetch-workflow-table.sh TARGET_PROJECT Bug
```

You should see your new workflow listed.

## Verification

Create a test issue in the target project and verify:
1. The issue is created in the expected initial status
2. Available transitions match the source workflow
3. Transition conditions work as expected

## Common Issues

### Issue: "Status mapping required"

**Cause:** The target project has existing issues in statuses that don't exist in the source workflow.

**Solution:** Provide status mappings in the script call:
```bash
--status-mapping "Old Status:New Status" --status-mapping "Another:Different"
```

### Issue: "Workflow scheme locked"

**Cause:** Another user is editing the workflow scheme.

**Solution:** Wait and retry. Workflow schemes use optimistic locking—fetch the latest version immediately before making changes.

## Related

- [Workflows Quick Reference](../quick-reference/workflows.md)
- [Workflow Schemes API Reference](../api-reference/WorkflowSchemesApi.md)
```

---

## Why This Structure Works

1. **Task in title** - "How to X" matches user queries directly
2. **Prerequisites first** - Sets expectations, avoids wasted effort
3. **Numbered steps** - Clear progression, easy to follow
4. **Commands with context** - Each step explains why, not just what
5. **Verification section** - Users can confirm success
6. **Common issues** - Preempts support questions, matches error searches
