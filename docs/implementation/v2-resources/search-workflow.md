# v2 Search Workflow

Search patterns for the unified lessons + resources system. For design rationale, see [planning.md](planning.md).

## Two-Tier Retrieval

### Tier 1: Lightweight Results

Search returns minimal metadata for quick triage:

```
[ID] (score: 0.892) Jira Workflows API
  type: doc | versions: v3
  "The Workflows API allows you to create, update, and delete..."

[ID] (score: 0.847) Update Jira Workflow Script
  type: script | versions: v2, v3
  path: ~/.ai/reference/jira-api/scripts/shared/update-workflow.sh
  "#!/bin/bash\n# Updates a Jira workflow with proper..."
```

### Tier 2: Full Content

Explicit fetch for items worth reading:

```bash
ai-lessons recall show-resource RESOURCE_ID
```

**Rationale:** Minimizes context pollution for AI agents. Irrelevant content wastes context window capacity and can diminish output coherency.

## Search Flow

### Recommended Pattern

```
1. search(query, limit=5)
   ↓
2. Examine: titles, scores, types, versions, snippets
   ↓
3. get_resource(id) for 1-2 promising results
   ↓
4. If insufficient:
   - Refine query terms
   - Adjust version filter
   - Try different search strategy
   ↓
5. get_related(id) for connected knowledge
```

### CLI Examples

```bash
# Initial broad search
ai-lessons recall search "workflow transitions" --limit 5

# Refine with version
ai-lessons recall search "workflow" --version v3

# Refine with type
ai-lessons recall search "workflow" --type script

# Get full content
ai-lessons recall show-resource RESOURCE_ID

# Explore relationships
ai-lessons recall related RESOURCE_ID
```

## Version Filtering

### Single Version

```bash
ai-lessons recall search "workflow" --version v3
```

Matches resources that include v3 (exact, superset, subset, or partial).

### Multiple Versions

```bash
ai-lessons recall search "workflow" --version v2 --version v3
```

Matches resources containing v2 AND v3, with scoring based on match quality.

### Version Match Scoring

| Relationship | Score Modifier |
|--------------|----------------|
| Exact match | × 1.00 |
| Superset | × 0.95 |
| Subset | × 0.85 |
| Partial overlap | × 0.75 |
| Unversioned | × 0.70 |
| Disjoint | No match |

## Combined Search

### Unified Search (Default)

Searches both lessons and resources:

```bash
ai-lessons recall search "jira workflow gotcha"
```

Results interleaved by score:

```
[lesson] (0.91) Always GET before PUT on Jira workflows
[doc]    (0.87) Jira Workflows API v3
[script] (0.82) update-workflow.sh
[lesson] (0.79) Workflow status ordering matters
```

### Filtered Search

```bash
# Lessons only
ai-lessons recall search "jira" --type lesson

# Docs only
ai-lessons recall search "jira" --type doc

# Scripts only
ai-lessons recall search "jira" --type script
```

## Graph-First Retrieval

After finding an initial match, explore its neighborhood:

```bash
# Find initial match
ai-lessons recall search "jira workflow" --limit 3

# Explore from best match
ai-lessons recall related LESSON_ID --depth 1
```

Reveals connected knowledge:

```
├── has_script: update-workflow.sh
├── derived_from: "REST API idempotency patterns"
└── related_to: "Jira status transition rules"
```

## MCP Tool Patterns

### Pattern 1: Search → Triage → Fetch

```python
# Step 1: Search
results = recall(query="jira workflow transitions", limit=5)

# Step 2: Triage (examine titles, scores, snippets)
# Select most relevant based on score, version, type

# Step 3: Fetch full content
full = get_resource(resource_id=results[0].id)

# Step 4: Explore related
related = get_related(id=results[0].id, depth=1)
```

### Pattern 2: Version-Scoped Search

```python
results = search_resources(
    query="workflow status",
    versions=["v3"],
    type="doc",
    limit=5
)
```

### Pattern 3: Script Discovery and Execution

```python
# Find scripts
results = search_resources(
    query="update workflow with conditions",
    type="script",
    versions=["v3"]
)

# Run the script
output = run_script(
    resource_id=results[0].id,
    args=["--project", "PROJ", "--workflow", "123"]
)
```

## Fallback: Filesystem Search

If semantic search fails, fall back to filesystem:

```bash
ls ~/.ai/reference/
ls ~/.ai/reference/jira-api/docs/v3/
grep -r "workflow" ~/.ai/reference/jira-api/
```

**Rationale:** Filesystem hierarchy serves as last-resort search when semantic search fails to surface relevant results.

## Search Strategies

| Strategy | Use Case |
|----------|----------|
| `hybrid` (default) | General queries |
| `semantic` | Conceptual/fuzzy ("that thing about...") |
| `keyword` | Exact terms, error messages |

```bash
# Semantic for vague recollection
ai-lessons recall search "that API gotcha with missing data" --strategy semantic

# Keyword for exact error
ai-lessons recall search "CUDA no kernel image" --strategy keyword
```
