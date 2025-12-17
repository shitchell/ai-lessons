# AI Lessons Agent Instructions

Instructions for AI agents using ai-lessons. For technical specs, see [specs.md](specs.md). For full protocol details, see [agent-protocol.md](agent-protocol.md).

## Quick Reference

```bash
# Search for knowledge
ai-lessons recall search "your query" --context-tags "relevant,tags"

# Get full content
ai-lessons recall show-resource RESOURCE_ID

# Run a script
ai-lessons recall run-resource SCRIPT_ID -- arg1 arg2

# Add a lesson
ai-lessons contribute add --title "..." --content "..." --tags tag1,tag2

# Add a script
ai-lessons contribute add-resource --type script --path /path/to/script.sh --title "..."

# Suggest a rule (goes to approval queue)
ai-lessons contribute suggest-rule --title "..." --rationale "..." --tags tag1,tag2
```

---

## Before Starting a Task

1. **Search** for existing knowledge:
   ```bash
   ai-lessons recall search "your task description" --context-tags "project,domain"
   ```

2. **Check results** for:
   - **Rules** (follow these) - Prescriptive guidance you must follow
   - **Scripts** (try these) - Validated solutions that may solve your task
   - **Lessons** (context) - Knowledge that may help
   - **Docs** (reference) - Documentation for details

3. **Run scripts** if available:
   ```bash
   ai-lessons recall run-resource SCRIPT_ID -- args
   ```

4. **Fetch full content** only for promising results:
   ```bash
   ai-lessons recall show-resource RESOURCE_ID
   ```

---

## The Contribution Rule

**If you had to iterate, you MUST contribute.**

| Outcome | Action |
|---------|--------|
| First-try success | No contribution needed |
| **Had to iterate/debug** | **MUST add lesson + script** |
| Discovered generalizable pattern | Also suggest a rule |
| Failed completely | Add partial lesson tagged `unsolved` |

### Why This Matters

Knowledge that required iteration is knowledge worth capturing. Future agents (including yourself) will benefit from:
- The lesson explaining what you learned
- The script proving the solution works

---

## How to Contribute

### 1. Add a Lesson

```bash
ai-lessons contribute add \
  --title "Descriptive title of what you learned" \
  --content "Detailed explanation of the observation or solution" \
  --tags relevant,tags,here \
  --confidence high \
  --source tested
```

### 2. Add a Validated Script

Save your working solution as a script, then:

```bash
ai-lessons contribute add-resource \
  --type script \
  --path /path/to/your/script.sh \
  --title "Descriptive script title" \
  --version v3  # or --version unversioned
```

### 3. Link Them

```bash
ai-lessons contribute link LESSON_ID SCRIPT_ID --relation has_script
ai-lessons contribute link SCRIPT_ID LESSON_ID --relation proves
```

### 4. Consider Suggesting a Rule

If your learning is generalizable (would help others avoid the same mistake):

```bash
ai-lessons contribute suggest-rule \
  --title "Always: do X when Y" \
  --rationale "Because Z will happen otherwise" \
  --tags relevant,tags \
  --link-lesson LESSON_ID \
  --link-script SCRIPT_ID
```

Rules require human approval before surfacing in search results.

---

## Search Tips

### Context Tags

Pass relevant context to boost related results:

```bash
ai-lessons recall search "query" --context-tags "jira-api=1.5,workflows,v3"
```

- Unweighted tags (e.g., `workflows`) get default weight
- Weighted tags (e.g., `jira-api=1.5`) boost by specified amount

### Version Filtering

```bash
# Single version
ai-lessons recall search "query" --version v3

# Multiple versions
ai-lessons recall search "query" --version v2 --version v3
```

### Type Filtering

```bash
ai-lessons recall search "query" --type script
ai-lessons recall search "query" --type doc
ai-lessons recall search "query" --type lesson
```

---

## Filesystem Fallback

If semantic search fails, explore the filesystem directly:

```bash
ls ~/.ai/reference/
ls ~/.ai/reference/{project}/docs/{version}/
grep -r "keyword" ~/.ai/reference/{project}/
```

---

## MCP Tools (if available)

| Tool | Purpose |
|------|---------|
| `search` | Search all knowledge types |
| `get_resource` | Fetch full content by ID |
| `run_script` | Execute a script resource |
| `add_lesson` | Add a new lesson |
| `add_resource` | Add doc or script |
| `suggest_rule` | Suggest a rule for approval |
| `link` | Create relationship between items |

---

## Checklist

Before completing a task, verify:

- [ ] Searched ai-lessons for existing knowledge
- [ ] Followed any applicable rules
- [ ] Tried relevant scripts
- [ ] If iterated: added lesson documenting what was learned
- [ ] If iterated: added script validating the solution
- [ ] If pattern is generalizable: suggested a rule

---

## Example Flow

```
Task: Update Jira workflow transitions

1. Search: ai-lessons recall search "jira workflow transitions" --context-tags "jira-api,v3"

2. Found:
   - Rule: "Always GET before PUT on workflows"
   - Script: update-workflow.sh
   - Lesson: "PUT replaces entire resource"

3. Tried script: Failed (new edge case)

4. Iterated: Fixed by adding status validation

5. Contributed:
   - Lesson: "Workflow PUT requires all statuses, even unchanged ones"
   - Script: update-workflow-v2.sh (improved version)
   - Suggested rule: "Always include all statuses in workflow PUT"
```
