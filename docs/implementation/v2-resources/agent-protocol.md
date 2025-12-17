# Agent Protocol

End-to-end workflow for agents using ai-lessons. For specifications, see [specs.md](specs.md).

## Overview

This document defines:
1. How agents search and consume knowledge
2. When and how agents contribute new knowledge
3. The contribution trigger (iteration = knowledge worth capturing)

---

## Search Flow

### Phase 1: Search

```python
results = ai_lessons.search(
    query=query,
    context_tags={"reviewer": None, "jira-api": 1.5},
    include_rules=True,
    limit=5
)

rules = results.rules          # Prescriptions to follow
scripts = results.scripts      # Executable solutions
lessons = results.lessons      # Observed knowledge
docs = results.docs            # Reference material
```

### Phase 2: Check for Existing Solution

```python
if scripts:
    for script in scripts.by_relevance():
        output = ai_lessons.run_script(script.id, args=...)

        if output.success:
            return output.result
        else:
            script_failed = True
            failed_script = script
```

### Phase 3: Apply Knowledge & Attempt Task

```python
guidance = {
    "must_follow": [r.content for r in rules],
    "keep_in_mind": [l.content for l in lessons],
    "reference": [d.id for d in docs],
}

attempts = 0
max_attempts = 5
learnings = []

while attempts < max_attempts:
    attempts += 1

    try:
        result = attempt_task(query, guidance)
        success = True
        break
    except Exception as e:
        learnings.append({
            "attempt": attempts,
            "error": str(e),
            "observation": analyze_failure(e)
        })
        guidance = refine_guidance(guidance, e)
        success = False
```

### Phase 4: Contribution

```python
if success:
    if attempts == 1 and not learnings:
        # First-try success, nothing notable learned
        pass

    elif attempts > 1 or learnings:
        # HAD TO ITERATE - this is the trigger
        # MUST contribute both lesson AND script

        # 1. Create lesson (objective observation of what was learned)
        lesson_id = ai_lessons.add_lesson(
            title=generate_title(query, learnings),
            content=synthesize_lesson(learnings),
            tags=context_tags + infer_tags(learnings),
            confidence="high",
            source="tested"
        )

        # 2. Create script that proves the lesson
        script_path = save_script(generate_validated_script(
            task=query,
            solution=result,
            learnings=learnings
        ))
        script_id = ai_lessons.add_resource(
            type="script",
            title=f"Validated: {generate_title(query, learnings)}",
            path=script_path,
            versions=detect_versions(context_tags),
            tags=context_tags
        )

        # 3. Link script to lesson
        ai_lessons.link(lesson_id, script_id, relation="has_script")
        ai_lessons.link(script_id, lesson_id, relation="proves")

        # 4. Consider suggesting a rule
        if is_generalizable(learnings):
            ai_lessons.suggest_rule(
                title=f"Always: {extract_prescription(learnings)}",
                rationale=synthesize_lesson(learnings),
                tags=context_tags,
                linked_lessons=[lesson_id],
                linked_resources=[script_id]
            )

else:
    # Failed after max attempts - still contribute partial knowledge
    ai_lessons.add_lesson(
        title=f"[UNSOLVED] {query}",
        content=synthesize_partial_learnings(learnings),
        tags=context_tags + ["unsolved", "needs-help"],
        confidence="low",
        source="observed"
    )
```

---

## Decision Points

### When to Contribute

| Condition | Action |
|-----------|--------|
| Script exists, works | Use it, done |
| Script exists, fails | Note failure, continue, consider updating script |
| First-try success | No contribution needed |
| **Had to iterate** | **MUST add lesson + script** |
| Iteration reveals pattern | Suggest rule |
| Failed completely | Add partial lesson tagged `unsolved` |

### When to Suggest a Rule

```python
def is_generalizable(learnings: list) -> bool:
    """Determine if learnings should become a rule."""
    return (
        has_repeated_pattern(learnings) or    # Same error multiple times
        is_api_behavior(learnings) or         # General API gotcha
        is_non_obvious(learnings)             # Would surprise others
    )
```

---

## Output Formats by Scenario

### Scenario 1: Only Docs

```
Search: "jira workflow transitions"

Results:
  Docs:
    [D001] (0.87) Jira Workflows API v3
      versions: v3 | "The Workflows API allows you to..."

  No lessons, rules, or scripts found.

  💡 After completing this task, consider:
     - Adding a lesson if you discover unexpected behavior
     - Adding a script if you build a reusable solution
```

### Scenario 2: Docs + Lessons

```
Search: "jira workflow transitions"

Results:
  Lessons:
    [L001] (0.91) PUT /workflows replaces entire resource
      confidence: high | source: tested
      "Omitting statuses in PUT payload deletes them..."

  Docs:
    [D001] (0.85) Jira Workflows API v3
      versions: v3 | "The Workflows API allows you to..."

  No rules or scripts found.

  💡 Consider: Should there be a rule based on lesson L001?
```

### Scenario 3: Full Coverage (Rules + Scripts + Lessons + Docs)

```
Search: "jira workflow transitions"

Rules (follow these):
  [R001] Always GET before PUT on Jira workflows
    applies to: jira-api, workflows
    rationale: "PUT replaces entire resource; GET ensures you have current state"

Scripts (try these):
  [S001] (0.89) update-workflow.sh
    versions: v2, v3 | path: ~/.ai/reference/jira-api/scripts/shared/
    "Updates workflow with proper status preservation..."

Lessons (context):
  [L001] (0.88) PUT /workflows replaces entire resource
    confidence: high | source: tested

Docs (reference):
  [D001] (0.82) Jira Workflows API v3
    versions: v3

  ✓ Full guidance available. Run script S001 or fetch details.
```

### Scenario 4: Only Scripts (No Context)

```
Search: "update jira workflow"

Results:
  Scripts:
    [S001] (0.92) update-workflow.sh
      versions: v2, v3 | path: ~/.ai/reference/jira-api/scripts/shared/
      "Updates workflow with proper status preservation..."

  No lessons, rules, or docs found.

  💡 This script exists but has no documented lessons.
     After using it, consider adding:
     - A lesson explaining what it does and why
     - A rule if there are important usage guidelines
```

---

## Contribution Prompts by Gap

| Found | Missing | Prompt |
|-------|---------|--------|
| Docs only | Everything else | "Add lesson if unexpected behavior; add script if reusable" |
| Scripts only | Lessons, rules | "Add lesson explaining what/why; add rule for guidelines" |
| Lessons only | Rules, scripts | "Should there be a rule? Is this scriptable?" |
| Docs + lessons | Rules, scripts | "Should there be a rule? Is this scriptable?" |
| Rules + lessons | Scripts | "Is this scriptable?" |
| Everything | Nothing | "✓ Full guidance available" |

---

## Sub-Agent Delegation

For complex searches or large doc exploration, spawn a sub-agent:

```python
# Primary agent
def handle_complex_query(query):
    # Delegate to sub-agent to preserve primary context
    result = spawn_subagent(
        task=f"Search ai-lessons for: {query}",
        instructions="""
        1. Search ai-lessons with the query
        2. If docs are massive, use filesystem fallback
        3. Return: relevant rules, scripts, lessons, doc summaries
        4. If you learned something new, add lesson + script
        5. Return concise summary to primary agent
        """
    )
    return result.summary
```

**Rationale:** Keeps primary agent context clean. Sub-agent handles search, contribution, and returns only relevant summary.

---

## Filesystem Fallback

If semantic search fails:

```bash
# List available reference materials
ls ~/.ai/reference/

# Explore specific project
ls ~/.ai/reference/jira-api/docs/v3/

# Grep for keywords
grep -r "workflow" ~/.ai/reference/jira-api/
```

The filesystem hierarchy exists as a last-resort search path when semantic search doesn't surface relevant results.

---

## Hooks Integration

### Startup Hook (Check Pending Rules)

```bash
# ~/.claude/hooks/on-startup.sh (or equivalent for other agents)
pending=$(ai-lessons admin pending-rules --count)
if [ "$pending" -gt 0 ]; then
    echo "⚠️  $pending rule suggestions awaiting review"
    echo "   Run: ai-lessons admin review-rules"
fi
```

### Post-Task Hook (Remind to Contribute)

```bash
# After task completion, if iteration occurred
if [ "$ITERATIONS" -gt 1 ]; then
    echo "💡 You iterated $ITERATIONS times. Remember to:"
    echo "   - Add lesson: ai-lessons contribute add ..."
    echo "   - Add script: ai-lessons contribute add-resource --type script ..."
fi
```
