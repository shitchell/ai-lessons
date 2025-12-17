# Conceptual/Explanation Template

Use this template for documentation that explains concepts, architecture, or "why" something works the way it does.

---

## Template

```markdown
# Understanding [Concept Name]

Brief summary: what this concept is and why it matters.

## What is [Concept]?

[2-3 paragraph explanation of the concept in plain terms. Start with a concrete definition, then expand.]

### Key Characteristics

- **Characteristic 1** - Brief explanation
- **Characteristic 2** - Brief explanation
- **Characteristic 3** - Brief explanation

## How [Concept] Works

[Explain the mechanics. Use diagrams if helpful.]

```
[Simple ASCII diagram or code showing the flow/structure]
```

### [Sub-component 1]

[Explain this part of the concept.]

### [Sub-component 2]

[Explain this part.]

## Why [Concept] Matters

[Explain the practical implications. When does understanding this help?]

**Use cases:**
- Situation where this knowledge is useful
- Another situation

## Common Misconceptions

### "[Misconception]"

**Reality:** [Correct understanding]

## Related Concepts

- **[Related Concept 1]** - How it relates
- **[Related Concept 2]** - How it relates

## Further Reading

- [Link to deeper dive]
- [Link to official documentation]
```

---

## Example: Understanding Jira Workflow Schemes

```markdown
# Understanding Jira Workflow Schemes

Workflow schemes connect workflows to projects and issue types. Understanding them is essential for managing how issues move through your Jira instance.

## What is a Workflow Scheme?

A workflow scheme is a mapping layer that determines which workflow governs which issue types in a project. It sits between projects and workflows:

```
Project  →  Workflow Scheme  →  Workflow(s)
   │              │                  │
   └── uses ──────┘                  │
                  └── maps issue ────┘
                      types to
```

Every Jira project has exactly one workflow scheme. That scheme can map different issue types to different workflows, or use a single workflow for all types.

### Key Characteristics

- **One scheme per project** - A project cannot have multiple schemes
- **Many-to-many** - One scheme can serve multiple projects; one workflow can be in multiple schemes
- **Issue-type mapping** - Each issue type maps to exactly one workflow within the scheme
- **Default workflow** - Unmapped issue types use the scheme's default workflow

## How Workflow Schemes Work

When you create an issue, Jira:

1. Looks up the project's workflow scheme
2. Finds the workflow mapped to that issue type
3. Places the issue in that workflow's initial status
4. Uses that workflow's transitions going forward

### The Mapping Structure

```json
{
  "id": "10001",
  "name": "Software Development Scheme",
  "defaultWorkflow": "Basic Workflow",
  "issueTypeMappings": {
    "Bug": "Bug Workflow",
    "Story": "Agile Workflow",
    "Epic": "Agile Workflow"
  }
}
```

In this example:
- Bugs use "Bug Workflow"
- Stories and Epics share "Agile Workflow"
- Any other issue type uses "Basic Workflow"

### Optimistic Locking

Workflow schemes use **optimistic locking** to prevent conflicts:

1. When you fetch a scheme, you get a `version.versionNumber`
2. When you update, you must include that version number
3. If someone else changed the scheme, your version is stale and the update fails

This prevents race conditions but requires you to always fetch before update.

## Why Workflow Schemes Matter

Understanding schemes is critical when:

- **Migrating projects** - You need to assign an appropriate scheme
- **Changing workflows** - Updates happen at the scheme level, not project level
- **Debugging transitions** - "Why can't I transition this issue?" often traces to scheme mappings
- **Bulk changes** - One scheme change affects all projects using it

**Use cases:**
- Standardizing workflows across multiple projects
- Giving different teams different processes for the same issue types
- Rolling out workflow changes gradually (change scheme, not workflow)

## Common Misconceptions

### "I can assign a workflow directly to a project"

**Reality:** You assign a workflow *scheme* to a project. The scheme then maps workflows to issue types. There's always a scheme in between, even if it only maps one workflow.

### "Changing a workflow affects only one project"

**Reality:** If multiple projects share a workflow scheme, and that scheme uses a workflow, changing the workflow affects all those projects. To change just one project, give it its own scheme.

### "I can have multiple workflows per issue type"

**Reality:** Within a single project, each issue type maps to exactly one workflow. An issue can't be in two workflows simultaneously.

## Related Concepts

- **Workflows** - The actual state machines with statuses and transitions
- **Issue Types** - The categories of work (Bug, Story, Task, etc.)
- **Workflow Scheme Drafts** - Unpublished changes to schemes

## Further Reading

- [Jira Workflow Schemes API](/api-reference/WorkflowSchemesApi.md)
- [How to Duplicate a Workflow](/how-to/duplicate-workflow.md)
- [Atlassian: Working with Workflows](https://support.atlassian.com/jira-cloud-administration/docs/work-with-workflows/)
```

---

## Why This Structure Works

1. **"What is" opening** - Answers the fundamental question immediately
2. **Visual aids** - Diagrams help conceptual understanding
3. **Progressive depth** - Overview → Details → Implications
4. **Misconceptions section** - Addresses common confusions (great for search)
5. **Related concepts** - Helps users explore the topic space
6. **Practical grounding** - "Why it matters" connects theory to action
