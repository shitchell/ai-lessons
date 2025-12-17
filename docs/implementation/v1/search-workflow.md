# Search Workflow Guide

This document describes optimal patterns for finding relevant lessons efficiently.

## Search Strategy Selection

The system supports three search strategies, each suited to different scenarios:

| Strategy | Best For | Trade-offs |
|----------|----------|------------|
| `hybrid` (default) | General queries | Best overall accuracy, slightly slower |
| `semantic` | Conceptual/fuzzy queries | Good for "what was that thing about..." |
| `keyword` | Exact terms, error messages | Fast, precise for known terms |

### When to Use Each

**Hybrid (default)** - Use for most queries:
```bash
ai-lessons recall search "jira workflow update"
```
Combines semantic understanding with keyword matching. Catches both conceptually similar content and exact term matches.

**Semantic** - Use when you remember the concept but not the words:
```bash
ai-lessons recall search "that API gotcha with missing data" --strategy semantic
```
Pure vector similarity. Good for vague recollections.

**Keyword** - Use for error messages, specific terms, or technical identifiers:
```bash
ai-lessons recall search "CUDA no kernel image" --strategy keyword
```
Fast exact matching. Best when you know the exact terminology.

## Progressive Search Pattern

For maximum efficiency, follow this progressive approach:

### Step 1: Quick Broad Search
Start with a simple query and default settings:
```bash
ai-lessons recall search "your topic" --limit 5
```

### Step 2: Refine with Filters
If results are noisy, add filters:
```bash
# Filter by tag
ai-lessons recall search "your topic" --tags api,gotcha

# Filter by context
ai-lessons recall search "your topic" --context jira

# Filter by minimum confidence
ai-lessons recall search "your topic" --confidence-min high

# Combine filters
ai-lessons recall search "jira update" --tags api --confidence-min medium
```

### Step 3: Explore Relationships
Found something relevant? Check related lessons:
```bash
# Direct relationships
ai-lessons recall related LESSON_ID

# Deeper traversal
ai-lessons recall related LESSON_ID --depth 2

# Specific relationship types
ai-lessons recall related LESSON_ID --relation derived_from
```

### Step 4: View Full Details
Get the complete lesson:
```bash
ai-lessons recall show LESSON_ID
```

## Filter Selection Guide

### Tags
Use tags to narrow by domain:
- Technical domains: `jira`, `python`, `sql`, `api`
- Problem types: `gotcha`, `workaround`, `pattern`, `antipattern`
- Source context: `debugging`, `documentation`, `testing`

Check available tags:
```bash
ai-lessons recall tags --counts
```

### Contexts
Use contexts for situational applicability:
- Environment: `production`, `development`, `testing`
- Tool versions: `jira-cloud`, `python3.10`, `react18`
- Team/project: `devops`, `frontend`, `backend`

### Confidence Minimum
Filter out low-confidence lessons when you need reliable information:
- `very-high`: Battle-tested, multiple confirmations
- `high`: Well-tested, reliable
- `medium`: Worked once, reasonable confidence
- `low`: Some evidence, shaky
- `very-low`: Untested assumption

For production decisions, use `--confidence-min high`.
For exploration, omit the filter.

### Source Types
Filter by how the knowledge was obtained:
- `tested`: Ran code, verified behavior
- `documented`: Official docs/specs
- `observed`: Saw in logs/output
- `inferred`: Reasoned from evidence
- `hearsay`: Someone said so

For critical decisions, prefer `--source tested` or `--source documented`.

## MCP Tool Workflow (for AI Agents)

When using the MCP interface, follow this pattern:

```
1. recall(query, limit=5)
   ↓
2. If relevant results found:
   - get_lesson(id) for full details
   - get_related(id) for connected knowledge
   ↓
3. If no results or poor matches:
   - Retry with different query terms
   - Try different strategy (semantic vs keyword)
   - Broaden or narrow tag filters
```

### Example MCP Flow
```json
// Step 1: Initial search
{"tool": "recall", "arguments": {"query": "jira workflow transitions", "limit": 5}}

// Step 2: Get details for relevant result
{"tool": "get_lesson", "arguments": {"lesson_id": "01HXYZ..."}}

// Step 3: Explore related lessons
{"tool": "get_related", "arguments": {"lesson_id": "01HXYZ...", "depth": 1}}
```

## Search Quality Signals

### Good Match Indicators
- **High score (>0.01)**: Strong relevance signal
- **Multiple tag overlap**: Query tags match lesson tags
- **Context match**: Lesson applies to your current context
- **High confidence**: `high` or `very-high` confidence
- **Tested source**: Verified through actual testing

### Weak Match Indicators
- **Low score (<0.005)**: Marginal relevance
- **Anti-context match**: Lesson explicitly doesn't apply to your context
- **Low confidence**: `very-low` or `low` confidence
- **Hearsay source**: Unverified information

## Performance Considerations

### Query Efficiency
- **Filters are fast**: Tag, context, and confidence filters use indexes
- **Semantic search has fixed cost**: Embedding generation dominates time
- **Keyword search scales with corpus**: Larger knowledge bases = slower keyword search

### Optimization Tips
1. **Start filtered**: If you know the domain, add `--tags` immediately
2. **Limit early**: Use `--limit 5` for initial exploration
3. **Use keyword for exact terms**: Skip embedding generation when you have exact error messages
4. **Cache exploration**: When deep-diving a topic, note lesson IDs to revisit

## Common Query Patterns

### Problem-Solving
```bash
# "I've seen this error before"
ai-lessons recall search "exact error message" --strategy keyword

# "How did we solve that thing with X?"
ai-lessons recall search "X problem solution" --tags workaround

# "What are the gotchas for Y?"
ai-lessons recall search "Y" --tags gotcha
```

### Learning
```bash
# "What do we know about X?"
ai-lessons recall search "X" --limit 20

# "What's the most reliable info on X?"
ai-lessons recall search "X" --confidence-min high --source documented

# "What have we learned recently?"
ai-lessons recall search "X" | head -5  # ULID sorting = recent first
```

### Verification
```bash
# "Is this still true?"
ai-lessons recall search "specific claim" --confidence-min medium

# "What contradicts this?"
ai-lessons recall related LESSON_ID --relation contradicts
```
