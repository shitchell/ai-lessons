# CLI Unification Implementation Specifications

**Plan**: declarative-baking-crystal.md
**Created**: 2025-12-18
**Status**: ✅ Implemented (2025-12-18)

---

## Overview

This document provides detailed, step-by-step implementation instructions for unifying the ai-lessons CLI using type-prefixed IDs, namespaced options, and unified commands. Each chunk is discrete and testable.

**CRITICAL**: Follow the plan exactly. No deviations. No suggestions. Just implement what is specified.

---

## Chunk 1: Schema v12 Migration (Refuse and Instruct)

### Goal
Update schema version to 12 and add a migration that refuses to migrate from v11 or earlier, instructing the user to recreate the database.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/schema.py`
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/db.py`

### Changes

#### schema.py
Change line 5:
```python
# Before:
SCHEMA_VERSION = 11

# After:
SCHEMA_VERSION = 12
```

Fix edges table CHECK constraints (lines 57-60):
```python
# Before:
from_type TEXT NOT NULL CHECK (from_type IN ('lesson', 'resource', 'chunk')),
...
to_type TEXT NOT NULL CHECK (to_type IN ('lesson', 'resource', 'chunk')),

# After:
from_type TEXT NOT NULL CHECK (from_type IN ('lesson', 'resource', 'chunk', 'rule')),
...
to_type TEXT NOT NULL CHECK (to_type IN ('lesson', 'resource', 'chunk', 'rule')),
```

#### db.py
Add v12 migration in `_run_migrations()` function (after the v11 migration block, around line 555):

```python
if current_version < 12:
    # v12: Type-prefixed IDs - requires clean slate
    raise RuntimeError(
        "I'm sorry Dave, I can't do that.\n\n"
        "Schema v12 introduces type-prefixed IDs which require a fresh database.\n"
        "To upgrade:\n"
        "  1. Delete your database: rm ~/.ai/lessons/knowledge.db\n"
        "  2. Re-initialize: ai-lessons admin init\n"
        "  3. Re-import your resources\n\n"
        "This is a one-time migration during rapid development."
    )

# Update schema version (this block already exists, no change needed)
conn.execute(
    "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
    (str(SCHEMA_VERSION),),
)
```

### Testing
```bash
# If you have an existing v11 database
ai-lessons admin stats  # Should raise the migration error

# Clean slate
rm ~/.ai/lessons/knowledge.db
ai-lessons admin init   # Should succeed
```

---

## Chunk 2: Core ID Generation Functions

### Goal
Add `generate_entity_id()` and `parse_entity_id()` functions to core.py, and update `_generate_id()` to use the new function for backward compatibility.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/core.py`

### Changes

Add after the imports (around line 31):
```python
def generate_entity_id(entity_type: str) -> str:
    """Generate a new prefixed ID for an entity type.

    Args:
        entity_type: One of 'lesson', 'resource', 'rule'.

    Returns:
        Prefixed ID (e.g., 'LSN01KCPYNGF1ZNRSQE5KANFAHH4N').

    Raises:
        ValueError: If entity_type is invalid.
    """
    prefix_map = {
        "lesson": "LSN",
        "resource": "RES",
        "rule": "RUL",
    }

    if entity_type not in prefix_map:
        raise ValueError(f"Invalid entity_type: {entity_type}. Must be one of: {list(prefix_map.keys())}")

    prefix = prefix_map[entity_type]
    return f"{prefix}{ULID()}"


def parse_entity_id(id_str: str) -> tuple[str, str]:
    """Parse a prefixed entity ID.

    Returns:
        Tuple of (entity_type, base_id) where entity_type is one of:
        'lesson', 'resource', 'chunk', 'rule'.

    Examples:
        parse_entity_id("LSN01KCP...") → ("lesson", "01KCP...")
        parse_entity_id("RES01KCP....0") → ("chunk", "RES01KCP....0")
        parse_entity_id("RES01KCP...") → ("resource", "RES01KCP...")
        parse_entity_id("RUL01KCP...") → ("rule", "RUL01KCP...")

    Raises:
        ValueError: If ID format is invalid.
    """
    # Check for chunk ID first (has .N suffix)
    if "." in id_str:
        # Chunk IDs keep the full ID including prefix
        # Format: RES<ulid>.<index>
        return ("chunk", id_str)

    # Extract prefix (first 3 chars)
    if len(id_str) < 3:
        raise ValueError(f"Invalid ID format: {id_str} (too short)")

    prefix = id_str[:3]
    base_id = id_str[3:]

    prefix_map = {
        "LSN": "lesson",
        "RES": "resource",
        "RUL": "rule",
    }

    if prefix not in prefix_map:
        raise ValueError(f"Invalid ID prefix: {prefix}. Must be one of: {list(prefix_map.keys())}")

    return (prefix_map[prefix], base_id)
```

### Testing
```python
# Test in Python REPL or write unit tests
from ai_lessons.core import generate_entity_id, parse_entity_id

# Generation
lesson_id = generate_entity_id("lesson")
assert lesson_id.startswith("LSN")
assert len(lesson_id) == 29  # 3 char prefix + 26 char ULID

resource_id = generate_entity_id("resource")
assert resource_id.startswith("RES")

rule_id = generate_entity_id("rule")
assert rule_id.startswith("RUL")

# Parsing
assert parse_entity_id("LSN01KCPYNGF1ZNRSQE5KANFAHH4N") == ("lesson", "01KCPYNGF1ZNRSQE5KANFAHH4N")
assert parse_entity_id("RES01KCPYNGF1ZNRSQE5KANFAHH4N") == ("resource", "01KCPYNGF1ZNRSQE5KANFAHH4N")
assert parse_entity_id("RUL01KCPYNGF1ZNRSQE5KANFAHH4N") == ("rule", "01KCPYNGF1ZNRSQE5KANFAHH4N")
assert parse_entity_id("RES01KCPYNGF1ZNRSQE5KANFAHH4N.0") == ("chunk", "RES01KCPYNGF1ZNRSQE5KANFAHH4N.0")
```

---

## Chunk 3: Update Chunk ID Generation

### Goal
Update `chunk_ids.py` to generate chunk IDs with RES prefix and update parsing logic.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/chunk_ids.py`

### Changes

Update the `generate_chunk_id()` function (around line 27):
```python
# No changes needed - the function already generates IDs in the format
# <resource_id>.<chunk_index>, and resource_id will now have RES prefix
```

Update the `parse_chunk_id()` function comment (line 43):
```python
# Before:
    chunk_id: Chunk ID to parse (e.g., "01KCPN9V.1").

# After:
    chunk_id: Chunk ID to parse (e.g., "RES01KCPN9V...0").
```

Update the `is_resource_id()` function (around line 85):
```python
# Before:
def is_resource_id(id_str: str) -> bool:
    """Check if a string is a resource ID (no .N suffix).

    Args:
        id_str: ID string to check.

    Returns:
        True if looks like a resource ID, False otherwise.
    """
    return "." not in id_str

# After:
def is_resource_id(id_str: str) -> bool:
    """Check if a string is a resource ID (has RES prefix, no .N suffix).

    Args:
        id_str: ID string to check.

    Returns:
        True if looks like a resource ID, False otherwise.
    """
    return id_str.startswith("RES") and "." not in id_str
```

### Testing
```python
from ai_lessons.chunk_ids import generate_chunk_id, parse_chunk_id, is_chunk_id, is_resource_id

# Test with prefixed resource ID
resource_id = "RES01KCPYNGF1ZNRSQE5KANFAHH4N"
chunk_id = generate_chunk_id(resource_id, 0)
assert chunk_id == "RES01KCPYNGF1ZNRSQE5KANFAHH4N.0"

parsed = parse_chunk_id(chunk_id)
assert parsed.resource_id == resource_id
assert parsed.chunk_index == 0

assert is_chunk_id(chunk_id)
assert is_resource_id(resource_id)
assert not is_resource_id(chunk_id)
```

---

## Chunk 4: Update add_lesson() to Use Prefixed IDs

### Goal
Update the `add_lesson()` function in core.py to use `generate_entity_id("lesson")`.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/core.py`

### Changes

Update line 464 in `add_lesson()`:
```python
# Before:
lesson_id = _generate_id()

# After:
lesson_id = generate_entity_id("lesson")
```

Update line 549 in `add_lessons_batch()`:
```python
# Before:
lesson_id = _generate_id()

# After:
lesson_id = generate_entity_id("lesson")
```

### Testing
```bash
# Create a lesson
ai-lessons contribute add-lesson -t "Test lesson" -c "Test content"

# Verify the ID has LSN prefix (should print something like LSN01KCP...)
ai-lessons admin stats
```

---

## Chunk 5: Update add_resource() to Use Prefixed IDs

### Goal
Find all resource creation code and update to use `generate_entity_id("resource")`.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/core.py`

### Changes

Search for `_generate_id()` calls in resource-related functions (around line 1100+). Update the `add_resource()` function:

```python
# Before (around line 1147):
resource_id = _generate_id()

# After:
resource_id = generate_entity_id("resource")
```

### Testing
```bash
# Create a test document
echo "# Test doc" > /tmp/test.md
ai-lessons contribute add-resource -t doc /tmp/test.md --version v1

# Verify ID has RES prefix
ai-lessons recall list-resources
```

---

## Chunk 6: Update suggest_rule() to Use Prefixed IDs

### Goal
Update rule creation to use `generate_entity_id("rule")`.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/core.py`

### Changes

Find the `suggest_rule()` function (around line 1600+) and update:

```python
# Before:
rule_id = _generate_id()

# After:
rule_id = generate_entity_id("rule")
```

Also update the `approve_rule()` function if it creates rule IDs.

### Testing
```bash
# Suggest a rule
ai-lessons contribute suggest-rule -t "Test rule" -c "Test content" -r "Test rationale"

# Verify ID has RUL prefix
ai-lessons admin pending-rules
```

---

## Chunk 7: Add list_lessons() Function

### Goal
Add a new `list_lessons()` function to core.py for filtering and listing lessons.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/core.py`

### Changes

Add after the `recall()` function (around line 817):

```python
def list_lessons(
    pattern: Optional[str] = None,
    tags: Optional[list[str]] = None,
    confidence: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 100,
    config: Optional[Config] = None,
) -> list[Lesson]:
    """List lessons with optional filtering.

    Args:
        pattern: Filter by title (case-insensitive substring).
        tags: Filter by tags (ANY match).
        confidence: Filter by exact confidence level.
        source: Filter by exact source type.
        limit: Maximum results.
        config: Configuration to use.

    Returns:
        List of lessons matching the filters.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    # Resolve tag aliases
    if tags:
        tags = _resolve_tag_aliases(tags, config)

    with get_db(config) as conn:
        # Build query
        query = "SELECT * FROM lessons WHERE 1=1"
        params: list = []

        if pattern:
            query += " AND title LIKE ?"
            params.append(f"%{pattern}%")

        if confidence:
            query += " AND confidence = ?"
            params.append(confidence)

        if source:
            query += " AND source = ?"
            params.append(source)

        if tags:
            placeholders = ",".join("?" * len(tags))
            query += f"""
                AND id IN (
                    SELECT lesson_id FROM lesson_tags
                    WHERE tag IN ({placeholders})
                )
            """
            params.extend(tags)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

        # Build Lesson objects
        lessons = []
        for row in rows:
            tags, contexts, anti_contexts = _fetch_lesson_properties(conn, row["id"])
            lessons.append(Lesson(
                id=row["id"],
                title=row["title"],
                content=row["content"],
                confidence=row["confidence"],
                source=row["source"],
                source_notes=row["source_notes"],
                tags=tags,
                contexts=contexts,
                anti_contexts=anti_contexts,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            ))

        return lessons
```

### Testing
```python
from ai_lessons.core import list_lessons

# List all lessons
lessons = list_lessons()
print(f"Found {len(lessons)} lessons")

# Filter by pattern
lessons = list_lessons(pattern="OAuth")
print(f"Found {len(lessons)} lessons matching 'OAuth'")

# Filter by tags
lessons = list_lessons(tags=["jira", "api"])
print(f"Found {len(lessons)} lessons with jira or api tag")
```

---

## Chunk 8: Add list_rules() Function

### Goal
Add a new `list_rules()` function to core.py for filtering and listing rules.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/core.py`

### Changes

Add after the `list_lessons()` function:

```python
def list_rules(
    pattern: Optional[str] = None,
    tags: Optional[list[str]] = None,
    pending: bool = False,
    approved: bool = True,
    limit: int = 100,
    config: Optional[Config] = None,
) -> list[Rule]:
    """List rules with optional filtering.

    Args:
        pattern: Filter by title (case-insensitive substring).
        tags: Filter by tags (ANY match).
        pending: Include pending (unapproved) rules.
        approved: Include approved rules.
        limit: Maximum results.
        config: Configuration to use.

    Returns:
        List of rules matching the filters.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    # Resolve tag aliases
    if tags:
        tags = _resolve_tag_aliases(tags, config)

    with get_db(config) as conn:
        # Build query
        query = "SELECT * FROM rules WHERE 1=1"
        params: list = []

        if pattern:
            query += " AND title LIKE ?"
            params.append(f"%{pattern}%")

        # Approval status filter
        approval_conditions = []
        if approved:
            approval_conditions.append("approved = 1")
        if pending:
            approval_conditions.append("approved = 0")

        if approval_conditions:
            query += f" AND ({' OR '.join(approval_conditions)})"
        elif not approved and not pending:
            # Neither approved nor pending requested - return empty
            return []

        if tags:
            placeholders = ",".join("?" * len(tags))
            query += f"""
                AND id IN (
                    SELECT rule_id FROM rule_tags
                    WHERE tag IN ({placeholders})
                )
            """
            params.extend(tags)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

        # Build Rule objects
        rules = []
        for row in rows:
            # Get tags
            tag_cursor = conn.execute(
                "SELECT tag FROM rule_tags WHERE rule_id = ?",
                (row["id"],)
            )
            rule_tags = [r["tag"] for r in tag_cursor.fetchall()]

            # Get linked lessons
            lesson_cursor = conn.execute(
                "SELECT to_id FROM edges WHERE from_id = ? AND from_type = 'rule' AND to_type = 'lesson'",
                (row["id"],)
            )
            linked_lessons = [r["to_id"] for r in lesson_cursor.fetchall()]

            # Get linked resources
            resource_cursor = conn.execute(
                "SELECT to_id FROM edges WHERE from_id = ? AND from_type = 'rule' AND to_type = 'resource'",
                (row["id"],)
            )
            linked_resources = [r["to_id"] for r in resource_cursor.fetchall()]

            rules.append(Rule(
                id=row["id"],
                title=row["title"],
                content=row["content"],
                rationale=row["rationale"],
                approved=bool(row["approved"]),
                approved_at=row["approved_at"],
                approved_by=row["approved_by"],
                suggested_by=row["suggested_by"],
                tags=rule_tags,
                linked_lessons=linked_lessons,
                linked_resources=linked_resources,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            ))

        return rules
```

### Testing
```python
from ai_lessons.core import list_rules

# List approved rules
rules = list_rules(approved=True)
print(f"Found {len(rules)} approved rules")

# List pending rules
rules = list_rules(pending=True, approved=False)
print(f"Found {len(rules)} pending rules")

# Filter by pattern
rules = list_rules(pattern="strict")
print(f"Found {len(rules)} rules matching 'strict'")
```

---

## Chunk 9: Add update_resource() Function

### Goal
Add a new `update_resource()` function to core.py for updating resource metadata.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/core.py`

### Changes

Add after the resource-related functions (around where `refresh_resource()` is defined):

```python
def update_resource(
    resource_id: str,
    tags: Optional[list[str]] = None,
    versions: Optional[list[str]] = None,
    config: Optional[Config] = None,
) -> bool:
    """Update resource metadata (not content - use refresh for that).

    Args:
        resource_id: The resource ID to update.
        tags: New tags (replaces existing).
        versions: New versions (replaces existing).
        config: Configuration to use.

    Returns:
        True if resource was updated, False if not found.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    # Check if resource exists
    resource = get_resource(resource_id, config)
    if resource is None:
        return False

    # Resolve tag aliases
    if tags is not None:
        tags = _resolve_tag_aliases(tags, config)

    with get_db(config) as conn:
        # Update tags if provided
        if tags is not None:
            _delete_tags(conn, resource_id, 'resource')
            _save_tags(conn, resource_id, 'resource', tags)

        # Update versions if provided
        if versions is not None:
            conn.execute("DELETE FROM resource_versions WHERE resource_id = ?", (resource_id,))
            if versions:
                conn.executemany(
                    "INSERT INTO resource_versions (resource_id, version) VALUES (?, ?)",
                    [(resource_id, v) for v in versions],
                )

        # Update timestamp
        conn.execute(
            "UPDATE resources SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (resource_id,)
        )

        conn.commit()

    return True
```

### Testing
```python
from ai_lessons.core import update_resource, get_resource

# Create a resource first (or use existing)
# ...

# Update tags
success = update_resource(resource_id, tags=["new", "tags"])
assert success

resource = get_resource(resource_id)
assert set(resource.tags) == {"new", "tags"}

# Update versions
success = update_resource(resource_id, versions=["v2", "v3"])
assert success

resource = get_resource(resource_id)
assert set(resource.versions) == {"v2", "v3"}
```

---

## Chunk 10: Update Display Functions for 15-Char Truncation

### Goal
Update all ID truncation in display.py from `[:12]` to `[:15]` to accommodate 3-char prefix.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/cli/display.py`

### Changes

Find and replace all instances of `[:12]` with `[:15]` in display.py. Specific lines:

Line 14:
```python
# Before:
lines.append(f"[{lesson.id}] {lesson.title}")

# After:
lines.append(f"[{lesson.id[:15]}...] {lesson.title}")
```

Line 58:
```python
# Before:
lines.append(f"[chunk] [{result.id}] (score: {result.score:.3f}) {display_title}")

# After:
lines.append(f"[chunk] [{result.id[:15]}...] (score: {result.score:.3f}) {display_title}")
```

Line 64:
```python
# Before:
meta.append(f"parent: {result.resource_id[:12]}...")

# After:
meta.append(f"parent: {result.resource_id[:15]}...")
```

Line 86:
```python
# Before:
lines.append(f"{type_indicator} [{result.id}] (score: {result.score:.3f}) {result.title}")

# After:
lines.append(f"{type_indicator} [{result.id[:15]}...] (score: {result.score:.3f}) {result.title}")
```

Line 97:
```python
# Before:
lines.append(f"[rule] [{result.id}] (score: {result.score:.3f}) {result.title}")

# After:
lines.append(f"[rule] [{result.id[:15]}...] (score: {result.score:.3f}) {result.title}")
```

Line 103:
```python
# Before:
lines.append(f"[{result.id}] (score: {result.score:.3f}) {result.title}")

# After:
lines.append(f"[{result.id[:15]}...] (score: {result.score:.3f}) {result.title}")
```

Line 130:
```python
# Before:
lines.append(f"{type_indicator} [{resource.id}] {resource.title}")

# After:
lines.append(f"{type_indicator} [{resource.id[:15]}...] {resource.title}")
```

Line 157:
```python
# Before:
lines.append(f"[{status}] [{rule.id}] {rule.title}")

# After:
lines.append(f"[{status}] [{rule.id[:15]}...] {rule.title}")
```

Line 191:
```python
# Before:
lines.append(f"[chunk] [{chunk.id}] {title}")

# After:
lines.append(f"[chunk] [{chunk.id[:15]}...] {title}")
```

Line 196:
```python
# Before:
meta.append(f"parent: {chunk.resource_id[:12]}...")

# After:
meta.append(f"parent: {chunk.resource_id[:15]}...")
```

Line 320 (in contribute.py, not display.py - see next chunk):
```python
# Note: Also update in contribute.py
```

### Testing
```bash
# Create and view various entities to verify ID truncation
ai-lessons contribute add-lesson -t "Test" -c "Content"
ai-lessons recall search "test"
# IDs should show 15 chars + ... (e.g., [LSN01KCPYNGF1ZN...])
```

---

## Chunk 11: Update ID Display in recall.py

### Goal
Update ID truncation in recall.py CLI commands.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/cli/recall.py`

### Changes

Line 188:
```python
# Before:
target = f"[{link.resolved_resource_id[:12]}...] {resource.title}"

# After:
target = f"[{link.resolved_resource_id[:15]}...] {resource.title}"
```

Line 189:
```python
# Before:
target = f"[{link.resolved_resource_id[:12]}...] (deleted)"

# After:
target = f"[{link.resolved_resource_id[:15]}...] (deleted)"
```

Line 364:
```python
# Before:
click.echo(f"  -> [{link.resolved_resource_id[:12]}...] {target.title}")

# After:
click.echo(f"  -> [{link.resolved_resource_id[:15]}...] {target.title}")
```

Line 366:
```python
# Before:
click.echo(f"  -> [{link.resolved_resource_id[:12]}...] (deleted)")

# After:
click.echo(f"  -> [{link.resolved_resource_id[:15]}...] (deleted)")
```

Line 379:
```python
# Before:
click.echo(f"  <- [{link.from_resource_id[:12]}...] {source.title}")

# After:
click.echo(f"  <- [{link.from_resource_id[:15]}...] {source.title}")
```

Line 381:
```python
# Before:
click.echo(f"  <- [{link.from_resource_id[:12]}...] (deleted)")

# After:
click.echo(f"  <- [{link.from_resource_id[:15]}...] (deleted)")
```

Line 469:
```python
# Before:
click.echo(f"  {chunk.chunk_index}. [{chunk.id[:12]}...] ({line_info}{token_info}){summary_marker}")

# After:
click.echo(f"  {chunk.chunk_index}. [{chunk.id[:15]}...] ({line_info}{token_info}){summary_marker}")
```

### Testing
```bash
ai-lessons recall show <resource-id>
ai-lessons recall list-chunks <resource-id>
# Verify IDs show 15 chars
```

---

## Chunk 12: Update ID Display in contribute.py

### Goal
Update ID truncation in contribute.py CLI commands.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/cli/contribute.py`

### Changes

Line 320:
```python
# Before:
click.echo(f"Added: {resource_id[:12]}... {title}")

# After:
click.echo(f"Added: {resource_id[:15]}... {title}")
```

Line 342 (in summary generation):
```python
# Before:
click.echo(f"  Warning: Failed for {resource_id[:12]}...: {e}", err=True)

# After:
click.echo(f"  Warning: Failed for {resource_id[:15]}...: {e}", err=True)
```

### Testing
```bash
ai-lessons contribute add-resource -t doc /tmp/test.md
# Verify ID shows 15 chars
```

---

## Chunk 13: Update ID Display in admin.py

### Goal
Update ID truncation in admin.py CLI commands.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/cli/admin.py`

### Changes

Line 466:
```python
# Before:
click.echo(f"  [{resource.id[:12]}...] {resource.title}")

# After:
click.echo(f"  [{resource.id[:15]}...] {resource.title}")
```

### Testing
```bash
ai-lessons admin clear-resources --dry-run --all
# Verify IDs show 15 chars
```

---

## Chunk 14: Unified `recall search` Command

### Goal
Update the `recall search` command to accept namespaced options for lessons, resources, and rules.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/cli/recall.py`

### Changes

Replace the existing `search` command (lines 39-119) with:

```python
@recall.command("search")
@click.argument("query")
# Universal options
@click.option("--type", multiple=True, help="Filter to type(s): lesson, resource, chunk, rule")
@click.option("--tags", help="Filter by comma-separated tags")
@click.option("--limit", "-n", default=10, help="Maximum results per type")
@click.option("--verbose", "-v", is_flag=True, help="Show content preview")
# Lesson options
@click.option("--lesson-context", help="Filter by lesson context")
@click.option("--lesson-confidence-min", type=click.Choice(["very-low", "low", "medium", "high", "very-high"]), help="Minimum confidence level")
@click.option("--lesson-source", help="Filter by lesson source type")
@click.option("--lesson-strategy", type=click.Choice(["hybrid", "semantic", "keyword"]), default="hybrid", help="Search strategy")
# Resource options
@click.option("--resource-type", type=click.Choice(["doc", "script"]), help="Filter by doc/script")
@click.option("--resource-version", "resource_versions", multiple=True, help="Filter by version(s)")
@click.option("--resource-grouped", "-g", is_flag=True, help="Group chunks by parent resource")
# Rule options
@click.option("--rule-pending", is_flag=True, help="Include pending rules")
@click.option("--rule-approved", is_flag=True, default=True, help="Include approved rules (default: true)")
def search(
    query: str,
    type: tuple,
    tags: Optional[str],
    limit: int,
    verbose: bool,
    # Lesson options
    lesson_context: Optional[str],
    lesson_confidence_min: Optional[str],
    lesson_source: Optional[str],
    lesson_strategy: str,
    # Resource options
    resource_type: Optional[str],
    resource_versions: tuple,
    resource_grouped: bool,
    # Rule options
    rule_pending: bool,
    rule_approved: bool,
):
    """Search across lessons, resources, and rules with namespaced options.

    Universal options (--type, --tags, --limit) apply to all types.
    Type-specific options (--lesson-*, --resource-*, --rule-*) only apply to their type.

    Examples:
      # Search all types
      ai-lessons recall search "OAuth2"

      # Search only lessons with high confidence
      ai-lessons recall search "OAuth2" --type lesson --lesson-confidence-min high

      # Search resources and filter by version
      ai-lessons recall search "OAuth2" --type resource --resource-version v3

      # Search all but filter lessons by confidence (resources unaffected)
      ai-lessons recall search "OAuth2" --lesson-confidence-min high
    """
    tag_list = parse_tags(tags)
    has_results = False

    # Determine which types to search
    types_to_search = set(type) if type else {"lesson", "resource", "rule"}

    # Search lessons
    if "lesson" in types_to_search:
        context_list = [lesson_context] if lesson_context else None
        lessons = core.recall(
            query=query,
            tags=tag_list,
            contexts=context_list,
            confidence_min=lesson_confidence_min,
            source=lesson_source,
            limit=limit,
            strategy=lesson_strategy,
        )
        if lessons:
            has_results = True
            click.echo(f"=== Lessons ({len(lessons)}) ===")
            click.echo()
            for result in lessons:
                click.echo(format_search_result(result, verbose))
                click.echo()

    # Search resources (chunks)
    if "resource" in types_to_search or "chunk" in types_to_search:
        if resource_grouped:
            top_matches, grouped_results = search_resources_grouped(
                query=query,
                tag_filter=tag_list,
                resource_type=resource_type,
                versions=list(resource_versions) if resource_versions else None,
                limit=limit,
            )
            if grouped_results:
                has_results = True
                click.echo(f"=== Resources ({len(grouped_results)} resources, {len(top_matches)} top chunks) ===")
                click.echo()
                click.echo(format_grouped_search_results(top_matches, grouped_results))
                click.echo()
        else:
            resources = search_resources(
                query=query,
                tag_filter=tag_list,
                resource_type=resource_type,
                versions=list(resource_versions) if resource_versions else None,
                limit=limit,
            )
            if resources:
                has_results = True
                click.echo(f"=== Resources ({len(resources)}) ===")
                click.echo()
                for result in resources:
                    click.echo(format_search_result(result, verbose))
                    click.echo()

    # Search rules
    if "rule" in types_to_search:
        # Build approval filter
        include_pending = rule_pending
        include_approved = rule_approved

        # Fetch rules based on approval status
        if include_pending and include_approved:
            # Get all rules
            all_rules = core.list_rules(tags=tag_list, pending=True, approved=True, limit=limit)
        elif include_pending:
            all_rules = core.list_rules(tags=tag_list, pending=True, approved=False, limit=limit)
        elif include_approved:
            all_rules = core.list_rules(tags=tag_list, pending=False, approved=True, limit=limit)
        else:
            all_rules = []

        # Simple keyword filtering for rules (they don't have embeddings)
        from ..search import _keyword_score
        scored_rules = []
        for rule in all_rules:
            score = _keyword_score(query, rule.title, rule.content)
            if score > 0:
                scored_rules.append((rule, score))

        scored_rules.sort(key=lambda x: x[1], reverse=True)
        top_rules = scored_rules[:limit]

        if top_rules:
            has_results = True
            click.echo(f"=== Rules ({len(top_rules)}) ===")
            click.echo()
            from ..search import RuleResult
            for rule, score in top_rules:
                result = RuleResult(
                    id=rule.id,
                    title=rule.title,
                    content=rule.content,
                    score=score,
                    result_type="rule",
                    tags=rule.tags,
                    rationale=rule.rationale,
                    approved=rule.approved,
                )
                click.echo(format_search_result(result, verbose))
                click.echo()

    if not has_results:
        click.echo("No results found.")
```

### Testing
```bash
# Test various combinations
ai-lessons recall search "OAuth2"
ai-lessons recall search "OAuth2" --type lesson
ai-lessons recall search "OAuth2" --type lesson --lesson-confidence-min high
ai-lessons recall search "OAuth2" --type resource --resource-version v3
ai-lessons recall search "OAuth2" --type rule --rule-pending
```

---

## Chunk 15: Unified `recall show` Command

### Goal
Update the `recall show` command to auto-detect type from ID prefix.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/cli/recall.py`

### Changes

Replace the existing `show` command (lines 160-207) with:

```python
@recall.command()
@click.argument("id")
@click.option("--verbose", "-v", is_flag=True, default=True, help="Show full content")
@click.option("--type", type=click.Choice(["lesson", "resource", "chunk", "rule"]), help="Explicit type hint (auto-detected from prefix)")
def show(id: str, verbose: bool, type: Optional[str]):
    """Show any entity by ID (auto-detects type from prefix).

    Type-prefixed IDs:
      LSN... - Lesson
      RES... - Resource
      RES....N - Chunk (has .N suffix)
      RUL... - Rule

    Examples:
      ai-lessons recall show LSN01KCP...
      ai-lessons recall show RES01KCP...
      ai-lessons recall show RES01KCP....0
      ai-lessons recall show RUL01KCP...
    """
    from ..core import parse_entity_id

    # Auto-detect type if not provided
    if type is None:
        try:
            detected_type, _ = parse_entity_id(id)
            type = detected_type
        except ValueError as e:
            click.echo(f"Error: Could not parse ID: {e}", err=True)
            click.echo("Hint: Use --type to specify entity type explicitly", err=True)
            sys.exit(1)

    # Dispatch based on type
    if type == "chunk":
        chunk = core.get_chunk(id)
        if chunk is None:
            click.echo(f"Chunk not found: {id}", err=True)
            sys.exit(1)
        click.echo(format_chunk(chunk, verbose=verbose))

        # Show linked resources
        links = core.get_chunk_links(id)
        if links:
            click.echo()
            click.echo("---")
            click.echo("Linked resources:")
            for link in links:
                if link.resolved_resource_id:
                    resource = core.get_resource(link.resolved_resource_id)
                    if resource:
                        target = f"[{link.resolved_resource_id[:15]}...] {resource.title}"
                    else:
                        target = f"[{link.resolved_resource_id[:15]}...] (deleted)"
                else:
                    target = "(not imported)"
                fragment = f"#{link.to_fragment}" if link.to_fragment else ""
                click.echo(f"  [{link.link_text}](...{fragment}) -> {target}")

    elif type == "resource":
        resource = core.get_resource(id)
        if resource is None:
            click.echo(f"Resource not found: {id}", err=True)
            sys.exit(1)
        click.echo(format_resource(resource, verbose=verbose))

    elif type == "lesson":
        lesson = core.get_lesson(id)
        if lesson is None:
            click.echo(f"Lesson not found: {id}", err=True)
            sys.exit(1)
        click.echo(format_lesson(lesson, verbose=verbose))

    elif type == "rule":
        rule = core.get_rule(id)
        if rule is None:
            click.echo(f"Rule not found: {id}", err=True)
            sys.exit(1)
        click.echo(format_rule(rule, verbose=True))

    else:
        click.echo(f"Unknown type: {type}", err=True)
        sys.exit(1)
```

### Testing
```bash
# Create entities and test show
ai-lessons contribute add-lesson -t "Test" -c "Content"
# Get the ID from output (e.g., LSN01KCP...)
ai-lessons recall show LSN01KCP...

# Test with resources
ai-lessons recall show RES01KCP...

# Test with chunks
ai-lessons recall show RES01KCP....0
```

---

## Chunk 16: Unified `recall list` Command

### Goal
Add a new unified `recall list` command that requires `--type` and supports namespaced filters.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/cli/recall.py`

### Changes

Add after the `show` command:

```python
@recall.command("list")
@click.option("--type", required=True, type=click.Choice(["lesson", "resource", "chunk", "rule"]), help="Entity type to list")
@click.option("--pattern", "-p", help="Filter by title (case-insensitive substring)")
@click.option("--tags", help="Filter by comma-separated tags")
@click.option("--limit", "-n", default=100, help="Maximum results")
# Lesson options
@click.option("--lesson-confidence", help="Filter by exact confidence level")
@click.option("--lesson-source", help="Filter by exact source type")
# Resource options
@click.option("--resource-type", type=click.Choice(["doc", "script"]), help="Filter by resource type")
@click.option("--resource-version", help="Filter by version")
# Chunk options
@click.option("--chunk-parent", help="Parent resource ID (required for chunks)")
# Rule options
@click.option("--rule-pending", is_flag=True, help="Include pending rules")
@click.option("--rule-approved", is_flag=True, default=True, help="Include approved rules")
def list_cmd(
    type: str,
    pattern: Optional[str],
    tags: Optional[str],
    limit: int,
    # Lesson options
    lesson_confidence: Optional[str],
    lesson_source: Optional[str],
    # Resource options
    resource_type: Optional[str],
    resource_version: Optional[str],
    # Chunk options
    chunk_parent: Optional[str],
    # Rule options
    rule_pending: bool,
    rule_approved: bool,
):
    """List entities by type with filtering.

    The --type option is required. Type-specific options apply only to their type.

    Examples:
      # List all lessons
      ai-lessons recall list --type lesson

      # List lessons with high confidence
      ai-lessons recall list --type lesson --lesson-confidence high

      # List scripts (resource type=script)
      ai-lessons recall list --type resource --resource-type script

      # List chunks for a resource
      ai-lessons recall list --type chunk --chunk-parent RES01KCP...

      # List pending rules
      ai-lessons recall list --type rule --rule-pending --rule-approved=false
    """
    tag_list = parse_tags(tags)

    if type == "lesson":
        lessons = core.list_lessons(
            pattern=pattern,
            tags=tag_list,
            confidence=lesson_confidence,
            source=lesson_source,
            limit=limit,
        )

        if not lessons:
            click.echo("No lessons found.")
            return

        click.echo(f"Found {len(lessons)} lesson(s):\n")
        for lesson in lessons:
            click.echo(format_lesson(lesson))
            click.echo()

    elif type == "resource":
        resources = core.list_resources(
            pattern=pattern,
            resource_type=resource_type,
            version=resource_version,
            tags=tag_list,
            limit=limit,
        )

        if not resources:
            click.echo("No resources found.")
            return

        # Get chunk counts
        config = get_config()
        with get_db(config) as conn:
            chunk_counts = {}
            for resource in resources:
                cursor = conn.execute(
                    "SELECT COUNT(*) as count FROM resource_chunks WHERE resource_id = ?",
                    (resource.id,),
                )
                chunk_counts[resource.id] = cursor.fetchone()["count"]

        click.echo(f"Found {len(resources)} resource(s):\n")
        for resource in resources:
            type_indicator = f"[{resource.type}]" if resource.type else "[resource]"
            chunk_count = chunk_counts.get(resource.id, 0)
            chunk_info = f", {chunk_count} chunk(s)" if chunk_count > 0 else ""

            versions_str = ", ".join(resource.versions) if resource.versions else "unversioned"
            click.echo(f"{type_indicator} [{resource.id[:15]}...] {resource.title}")
            click.echo(f"  versions: {versions_str}{chunk_info}")
            if resource.tags:
                click.echo(f"  tags: {', '.join(resource.tags)}")
            click.echo()

    elif type == "chunk":
        if not chunk_parent:
            click.echo("Error: --chunk-parent is required for listing chunks", err=True)
            sys.exit(1)

        resource = core.get_resource(chunk_parent)
        if resource is None:
            click.echo(f"Resource not found: {chunk_parent}", err=True)
            sys.exit(1)

        chunks = core.list_chunks(chunk_parent)

        if not chunks:
            click.echo(f"No chunks found for resource '{resource.title}'.")
            return

        click.echo(f"Chunks in \"{resource.title}\" ({len(chunks)} total):\n")
        for chunk in chunks:
            # Determine title to display
            if chunk.title:
                title = chunk.title
            elif chunk.breadcrumb:
                title = chunk.breadcrumb
            else:
                title = "(no title)"

            # Line info
            line_info = ""
            if chunk.start_line is not None and chunk.end_line is not None:
                line_info = f"lines {chunk.start_line + 1}-{chunk.end_line + 1}, "

            token_info = f"{chunk.token_count} tokens" if chunk.token_count else "? tokens"
            summary_marker = " [S]" if chunk.summary else ""

            click.echo(f"  {chunk.chunk_index}. [{chunk.id[:15]}...] ({line_info}{token_info}){summary_marker}")
            click.echo(f"     {title}")

        click.echo()
        click.echo("Legend: [S] = has summary")

    elif type == "rule":
        rules = core.list_rules(
            pattern=pattern,
            tags=tag_list,
            pending=rule_pending,
            approved=rule_approved,
            limit=limit,
        )

        if not rules:
            click.echo("No rules found.")
            return

        click.echo(f"Found {len(rules)} rule(s):\n")
        for rule in rules:
            click.echo(format_rule(rule))
            click.echo()
```

### Testing
```bash
# Test listing each type
ai-lessons recall list --type lesson
ai-lessons recall list --type resource
ai-lessons recall list --type chunk --chunk-parent RES01KCP...
ai-lessons recall list --type rule

# Test with filters
ai-lessons recall list --type lesson --lesson-confidence high
ai-lessons recall list --type resource --resource-type script
ai-lessons recall list --type rule --rule-pending
```

---

## Chunk 17: Unified `recall related` Command

### Goal
Add a unified `recall related` command that works with any entity ID.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/cli/recall.py`

### Changes

Replace `related-lesson` and `related-resource` commands with a single `related` command:

```python
@recall.command("related")
@click.argument("entity_id")
@click.option("--depth", "-d", default=1, help="Traversal depth")
@click.option("--relation", "-r", multiple=True, help="Filter by relation type")
def related(entity_id: str, depth: int, relation: tuple):
    """Show entities related to the given entity via graph edges.

    Works with any entity ID (auto-detects type from prefix).

    Examples:
      ai-lessons recall related LSN01KCP...
      ai-lessons recall related RES01KCP... --depth 2
      ai-lessons recall related LSN01KCP... --relation derived_from
    """
    from ..core import parse_entity_id

    # Detect entity type
    try:
        entity_type, _ = parse_entity_id(entity_id)
    except ValueError as e:
        click.echo(f"Error: Could not parse ID: {e}", err=True)
        sys.exit(1)

    # Query edges table for related entities
    config = get_config()
    with get_db(config) as conn:
        # Build query
        query = """
            SELECT to_id, to_type, relation
            FROM edges
            WHERE from_id = ? AND from_type = ?
        """
        params: list = [entity_id, entity_type]

        if relation:
            placeholders = ",".join("?" * len(relation))
            query += f" AND relation IN ({placeholders})"
            params.extend(relation)

        cursor = conn.execute(query, params)
        edges = cursor.fetchall()

    if not edges:
        click.echo(f"No related entities found for {entity_id[:15]}...")
        return

    # Group by type
    by_type = {}
    for edge in edges:
        to_type = edge["to_type"]
        if to_type not in by_type:
            by_type[to_type] = []
        by_type[to_type].append(edge)

    # Display by type
    for entity_type in sorted(by_type.keys()):
        edges_of_type = by_type[entity_type]
        click.echo(f"\n=== {entity_type.title()}s ({len(edges_of_type)}) ===\n")

        for edge in edges_of_type:
            to_id = edge["to_id"]
            rel = edge["relation"]

            # Fetch entity details
            if entity_type == "lesson":
                entity = core.get_lesson(to_id)
                if entity:
                    click.echo(f"[{rel}] {format_lesson(entity)}")
                else:
                    click.echo(f"[{rel}] [{to_id[:15]}...] (deleted)")

            elif entity_type == "resource":
                entity = core.get_resource(to_id)
                if entity:
                    click.echo(f"[{rel}] {format_resource(entity)}")
                else:
                    click.echo(f"[{rel}] [{to_id[:15]}...] (deleted)")

            elif entity_type == "chunk":
                entity = core.get_chunk(to_id)
                if entity:
                    click.echo(f"[{rel}] {format_chunk(entity)}")
                else:
                    click.echo(f"[{rel}] [{to_id[:15]}...] (deleted)")

            elif entity_type == "rule":
                entity = core.get_rule(to_id)
                if entity:
                    click.echo(f"[{rel}] {format_rule(entity)}")
                else:
                    click.echo(f"[{rel}] [{to_id[:15]}...] (deleted)")

            click.echo()
```

### Testing
```bash
# Create some links first
ai-lessons contribute link LSN... LSN... --relation derived_from
ai-lessons contribute link LSN... RES... --relation documents

# Test related
ai-lessons recall related LSN...
ai-lessons recall related LSN... --relation derived_from
```

---

## Chunk 18: Unified `contribute update` Command

### Goal
Add a unified `contribute update` command that works with any entity ID and has namespaced options.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/cli/contribute.py`

### Changes

Add after the existing update commands:

```python
@contribute.command("update")
@click.argument("entity_id")
@click.option("--title", "-t", help="New title")
@click.option("--tags", help="New comma-separated tags (replaces existing)")
# Lesson options
@click.option("--lesson-content", "-c", help="New content")
@click.option("--lesson-confidence", type=click.Choice(["very-low", "low", "medium", "high", "very-high"]), help="New confidence level")
@click.option("--lesson-source", type=click.Choice(["inferred", "tested", "documented", "observed", "hearsay"]), help="New source type")
@click.option("--lesson-source-notes", help="New source notes")
# Resource options (metadata only)
@click.option("--resource-version", "resource_versions", multiple=True, help="New version(s) (replaces existing)")
# Rule options
@click.option("--rule-content", help="New rule content")
@click.option("--rule-rationale", help="New rationale")
def update(
    entity_id: str,
    title: Optional[str],
    tags: Optional[str],
    # Lesson options
    lesson_content: Optional[str],
    lesson_confidence: Optional[str],
    lesson_source: Optional[str],
    lesson_source_notes: Optional[str],
    # Resource options
    resource_versions: tuple,
    # Rule options
    rule_content: Optional[str],
    rule_rationale: Optional[str],
):
    """Update any entity by ID (auto-detects type from prefix).

    Universal options (--title, --tags) work for all types.
    Type-specific options (--lesson-*, --resource-*, --rule-*) only apply to their type.

    Smart errors:
      - Updating a chunk ID → Error with message to use refresh on parent
      - Updating resource content → Error with message to use refresh

    Examples:
      # Update lesson
      ai-lessons contribute update LSN01KCP... --title "New title" --lesson-confidence high

      # Update resource metadata
      ai-lessons contribute update RES01KCP... --tags new,tags --resource-version v4

      # Update rule
      ai-lessons contribute update RUL01KCP... --title "Updated" --rule-rationale "New rationale"
    """
    from ..core import parse_entity_id

    # Auto-detect type
    try:
        entity_type, _ = parse_entity_id(entity_id)
    except ValueError as e:
        click.echo(f"Error: Could not parse ID: {e}", err=True)
        sys.exit(1)

    # Smart error for chunks
    if entity_type == "chunk":
        click.echo("Error: Chunks are updated via their parent resource.", err=True)
        click.echo(f"Use `ai-lessons contribute refresh {entity_id.rsplit('.', 1)[0]}` to reload from filesystem.", err=True)
        sys.exit(1)

    # Dispatch based on type
    if entity_type == "lesson":
        # Warn if resource options provided
        if resource_versions:
            click.echo("Warning: --resource-version ignored for lessons", err=True)
        if rule_content or rule_rationale:
            click.echo("Warning: --rule-* options ignored for lessons", err=True)

        success = core.update_lesson(
            lesson_id=entity_id,
            title=title,
            content=lesson_content,
            tags=parse_tags(tags),
            confidence=lesson_confidence,
            source=lesson_source,
            source_notes=lesson_source_notes,
        )

        if success:
            click.echo(f"Updated lesson: {entity_id[:15]}...")
        else:
            click.echo(f"Lesson not found: {entity_id[:15]}...", err=True)
            sys.exit(1)

    elif entity_type == "resource":
        # Warn if lesson/rule options provided
        if lesson_content or lesson_confidence or lesson_source or lesson_source_notes:
            click.echo("Warning: --lesson-* options ignored for resources", err=True)
        if rule_content or rule_rationale:
            click.echo("Warning: --rule-* options ignored for resources", err=True)

        # Smart error for content update
        if lesson_content:
            click.echo("Error: Resource content cannot be updated directly.", err=True)
            click.echo(f"Use `ai-lessons contribute refresh {entity_id[:15]}...` to reload from filesystem.", err=True)
            sys.exit(1)

        # Update title if provided (requires modifying update_resource to accept title)
        if title:
            click.echo("Warning: Updating resource title not yet supported (only tags/versions)", err=True)

        success = core.update_resource(
            resource_id=entity_id,
            tags=parse_tags(tags),
            versions=list(resource_versions) if resource_versions else None,
        )

        if success:
            click.echo(f"Updated resource: {entity_id[:15]}...")
        else:
            click.echo(f"Resource not found: {entity_id[:15]}...", err=True)
            sys.exit(1)

    elif entity_type == "rule":
        # Warn if lesson/resource options provided
        if lesson_content or lesson_confidence or lesson_source or lesson_source_notes:
            click.echo("Warning: --lesson-* options ignored for rules", err=True)
        if resource_versions:
            click.echo("Warning: --resource-version ignored for rules", err=True)

        # Update rule
        success = core.update_rule(
            rule_id=entity_id,
            title=title,
            content=rule_content,
            rationale=rule_rationale,
            tags=parse_tags(tags),
        )

        if success:
            click.echo(f"Updated rule: {entity_id[:15]}...")
        else:
            click.echo(f"Rule not found: {entity_id[:15]}...", err=True)
            sys.exit(1)

    else:
        click.echo(f"Unknown entity type: {entity_type}", err=True)
        sys.exit(1)
```

Note: This requires a `core.update_rule()` function which doesn't exist yet. Add it to core.py:

```python
def update_rule(
    rule_id: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    rationale: Optional[str] = None,
    tags: Optional[list[str]] = None,
    config: Optional[Config] = None,
) -> bool:
    """Update an existing rule.

    Args:
        rule_id: The rule ID to update.
        title: New title (optional).
        content: New content (optional).
        rationale: New rationale (optional).
        tags: New tags (replaces existing).
        config: Configuration to use.

    Returns:
        True if rule was updated, False if not found.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    # Check if rule exists
    existing = get_rule(rule_id, config)
    if existing is None:
        return False

    # Resolve tag aliases
    if tags is not None:
        tags = _resolve_tag_aliases(tags, config)

    with get_db(config) as conn:
        # Build update query
        updates = []
        params = []

        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if content is not None:
            updates.append("content = ?")
            params.append(content)
        if rationale is not None:
            updates.append("rationale = ?")
            params.append(rationale)

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            query = f"UPDATE rules SET {', '.join(updates)} WHERE id = ?"
            params.append(rule_id)
            conn.execute(query, params)

        # Update tags if provided
        if tags is not None:
            _delete_tags(conn, rule_id, 'rule')
            _save_tags(conn, rule_id, 'rule', tags)

        conn.commit()

    return True
```

### Testing
```bash
# Test updating different types
ai-lessons contribute update LSN... --title "New title"
ai-lessons contribute update RES... --tags new,tags
ai-lessons contribute update RUL... --rule-rationale "New rationale"

# Test smart errors
ai-lessons contribute update RES....0  # Should error about chunks
```

---

## Chunk 19: Unified `contribute delete` Command

### Goal
Add a unified `contribute delete` command that works with any entity ID.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/cli/contribute.py`

### Changes

Add after the update command:

```python
@contribute.command("delete")
@click.argument("entity_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def delete(entity_id: str, yes: bool):
    """Delete any entity by ID (auto-detects type from prefix).

    Smart errors:
      - Deleting a chunk ID → Error with message to delete parent resource

    Examples:
      ai-lessons contribute delete LSN01KCP...
      ai-lessons contribute delete RES01KCP... --yes
      ai-lessons contribute delete RUL01KCP...
    """
    from ..core import parse_entity_id

    # Auto-detect type
    try:
        entity_type, _ = parse_entity_id(entity_id)
    except ValueError as e:
        click.echo(f"Error: Could not parse ID: {e}", err=True)
        sys.exit(1)

    # Smart error for chunks
    if entity_type == "chunk":
        parent_id = entity_id.rsplit('.', 1)[0]
        click.echo("Error: Chunks are deleted with their parent resource.", err=True)
        click.echo(f"Use `ai-lessons contribute delete {parent_id}` to delete the entire resource.", err=True)
        sys.exit(1)

    # Confirm deletion
    if not yes:
        entity_type_display = entity_type.title()
        if not click.confirm(f"Are you sure you want to delete this {entity_type_display}?"):
            click.echo("Aborted.")
            return

    # Dispatch based on type
    if entity_type == "lesson":
        success = core.delete_lesson(entity_id)
        if success:
            click.echo(f"Deleted lesson: {entity_id[:15]}...")
        else:
            click.echo(f"Lesson not found: {entity_id[:15]}...", err=True)
            sys.exit(1)

    elif entity_type == "resource":
        success = core.delete_resource(entity_id)
        if success:
            click.echo(f"Deleted resource: {entity_id[:15]}...")
        else:
            click.echo(f"Resource not found: {entity_id[:15]}...", err=True)
            sys.exit(1)

    elif entity_type == "rule":
        # Use reject_rule which is the same as delete
        success = core.reject_rule(entity_id)
        if success:
            click.echo(f"Deleted rule: {entity_id[:15]}...")
        else:
            click.echo(f"Rule not found: {entity_id[:15]}...", err=True)
            sys.exit(1)

    else:
        click.echo(f"Unknown entity type: {entity_type}", err=True)
        sys.exit(1)
```

### Testing
```bash
# Test deleting different types (with confirmation)
ai-lessons contribute delete LSN...
ai-lessons contribute delete RES... --yes
ai-lessons contribute delete RUL...

# Test smart error
ai-lessons contribute delete RES....0  # Should error
```

---

## Chunk 20: Unified `contribute link` and `unlink` Commands

### Goal
Add unified `contribute link` and `unlink` commands that work with any entity IDs.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/cli/contribute.py`

### Changes

Add after the delete command:

```python
@contribute.command("link")
@click.argument("from_id")
@click.argument("to_id")
@click.option("--relation", "-r", required=True, help="Relationship type (e.g., derived_from, documents, based_on)")
def link(from_id: str, to_id: str, relation: str):
    """Link any entity to any other entity (auto-detects types from prefixes).

    The edges table supports any-to-any linking:
      - Lesson to lesson
      - Lesson to resource
      - Lesson to chunk
      - Rule to lesson
      - Resource to resource
      - Chunk to chunk
      - etc.

    Examples:
      ai-lessons contribute link LSN111... LSN222... --relation derived_from
      ai-lessons contribute link LSN111... RES222... --relation documents
      ai-lessons contribute link RUL111... LSN222... --relation based_on
      ai-lessons contribute link RES111....0 LSN222... --relation explains
    """
    from ..core import parse_entity_id

    # Auto-detect types
    try:
        from_type, _ = parse_entity_id(from_id)
        to_type, _ = parse_entity_id(to_id)
    except ValueError as e:
        click.echo(f"Error: Could not parse ID: {e}", err=True)
        sys.exit(1)

    # Create edge
    config = get_config()
    with get_db(config) as conn:
        try:
            conn.execute(
                """INSERT INTO edges (from_id, from_type, to_id, to_type, relation)
                   VALUES (?, ?, ?, ?, ?)""",
                (from_id, from_type, to_id, to_type, relation),
            )
            conn.commit()
            click.echo(f"Linked {from_id[:15]}... --[{relation}]--> {to_id[:15]}...")
        except sqlite3.IntegrityError:
            click.echo("Link already exists.", err=True)
            sys.exit(1)


@contribute.command("unlink")
@click.argument("from_id")
@click.argument("to_id")
@click.option("--relation", "-r", help="Specific relation to remove (all if not specified)")
def unlink(from_id: str, to_id: str, relation: Optional[str]):
    """Remove link(s) between two entities (auto-detects types from prefixes).

    Examples:
      ai-lessons contribute unlink LSN111... LSN222...
      ai-lessons contribute unlink LSN111... RES222... --relation documents
    """
    from ..core import parse_entity_id

    # Auto-detect types
    try:
        from_type, _ = parse_entity_id(from_id)
        to_type, _ = parse_entity_id(to_id)
    except ValueError as e:
        click.echo(f"Error: Could not parse ID: {e}", err=True)
        sys.exit(1)

    # Remove edge(s)
    config = get_config()
    with get_db(config) as conn:
        if relation:
            cursor = conn.execute(
                """DELETE FROM edges
                   WHERE from_id = ? AND from_type = ?
                   AND to_id = ? AND to_type = ? AND relation = ?""",
                (from_id, from_type, to_id, to_type, relation),
            )
        else:
            cursor = conn.execute(
                """DELETE FROM edges
                   WHERE from_id = ? AND from_type = ?
                   AND to_id = ? AND to_type = ?""",
                (from_id, from_type, to_id, to_type),
            )
        conn.commit()
        count = cursor.rowcount
        click.echo(f"Removed {count} link(s)")
```

### Testing
```bash
# Create some links
ai-lessons contribute link LSN... LSN... --relation derived_from
ai-lessons contribute link LSN... RES... --relation documents

# Verify with related
ai-lessons recall related LSN...

# Remove links
ai-lessons contribute unlink LSN... LSN... --relation derived_from
ai-lessons contribute unlink LSN... RES...
```

---

## Chunk 21: `contribute refresh` Command

### Goal
Update the existing `refresh-resource` command to work as `refresh` with any resource ID.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/cli/contribute.py`

### Changes

Replace the existing `refresh-resource` command (around line 353) with:

```python
@contribute.command("refresh")
@click.argument("resource_id")
def refresh(resource_id: str):
    """Re-read resource content from filesystem (resources only).

    Smart errors:
      - Non-resource ID → Error explaining refresh only works for resources

    Examples:
      ai-lessons contribute refresh RES01KCP...
    """
    from ..core import parse_entity_id

    # Auto-detect type
    try:
        entity_type, _ = parse_entity_id(resource_id)
    except ValueError as e:
        click.echo(f"Error: Could not parse ID: {e}", err=True)
        sys.exit(1)

    # Smart error for non-resources
    if entity_type != "resource":
        click.echo(f"Error: Refresh only applies to resources (type: {entity_type}).", err=True)
        click.echo("Resources are docs and scripts that can be reloaded from filesystem.", err=True)
        sys.exit(1)

    success = core.refresh_resource(resource_id)

    if success:
        click.echo(f"Refreshed resource: {resource_id[:15]}...")
    else:
        click.echo(f"Resource not found or has no path: {resource_id[:15]}...", err=True)
        sys.exit(1)
```

### Testing
```bash
# Test refresh on a resource
ai-lessons contribute refresh RES...

# Test smart error on non-resource
ai-lessons contribute refresh LSN...  # Should error
```

---

## Chunk 22: Remove `admin reject-rule` Command

### Goal
Remove the `admin reject-rule` command since `contribute delete` now handles it.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/cli/admin.py`

### Changes

Delete the `reject-rule` command (around line 179-190):

```python
# DELETE THIS ENTIRE COMMAND:
@admin.command("reject-rule")
@click.argument("rule_id")
@click.confirmation_option(prompt="Are you sure you want to reject (delete) this rule?")
def reject_rule(rule_id: str):
    """Reject (delete) a suggested rule."""
    success = core.reject_rule(rule_id)

    if success:
        click.echo(f"Rejected rule: {rule_id}")
    else:
        click.echo(f"Rule not found: {rule_id}", err=True)
        sys.exit(1)
```

### Testing
```bash
# This command should no longer exist
ai-lessons admin reject-rule  # Should error: no such command

# Use delete instead
ai-lessons contribute delete RUL...
```

---

## Chunk 23: Update Existing Separate Commands (Optional Deprecation)

### Goal
Optionally add deprecation warnings to the old separate commands (search-lesson, search-resources, etc.) to guide users to the new unified commands.

### Files to Modify
- `/home/guy/git/github.com/shitchell/ai-lessons/src/ai_lessons/cli/recall.py`

### Changes

Add deprecation warnings to the old commands. Example:

```python
@recall.command("search-lesson")
# ... existing options ...
def search_lesson(...):
    """Search for lessons.

    DEPRECATED: Use `ai-lessons recall search --type lesson` instead.
    """
    click.echo("Warning: This command is deprecated. Use `recall search --type lesson` instead.", err=True)
    click.echo()

    # ... existing implementation ...
```

Repeat for:
- `search-resources` → "Use `recall search --type resource`"
- `show-resource` → "Use `recall show <id>`"
- `show-chunk` → "Use `recall show <id>`"
- `related-lesson` → "Use `recall related <id>`"
- `related-resource` → "Use `recall related <id>`"
- `list-resources` → "Use `recall list --type resource`"
- `list-chunks` → "Use `recall list --type chunk`"
- `show-rule` → "Use `recall show <id>`"

And in contribute.py:
- `update-lesson` → "Use `contribute update <id>`"
- `delete-lesson` → "Use `contribute delete <id>`"
- `link-lesson` → "Use `contribute link <from> <to>`"
- `unlink-lesson` → "Use `contribute unlink <from> <to>`"
- `link-resource` → "Use `contribute link <from> <to>`"
- `unlink-resource` → "Use `contribute unlink <from> <to>`"
- `delete-resource` → "Use `contribute delete <id>`"

### Testing
```bash
# Old commands should still work but show warnings
ai-lessons recall search-lesson "test"  # Shows warning, then works
ai-lessons recall show-resource RES...  # Shows warning, then works
```

---

## Chunk 24: Integration Testing

### Goal
Comprehensive testing of the new unified CLI.

### Testing Script

Create a test script `/tmp/test-unified-cli.sh`:

```bash
#!/bin/bash
set -e

echo "=== Testing Unified CLI ==="

# Clean slate
rm -f ~/.ai/lessons/knowledge.db
ai-lessons admin init

echo -e "\n=== Test 1: Create entities with prefixed IDs ==="
lesson_id=$(ai-lessons contribute add-lesson -t "Test OAuth2 lesson" -c "OAuth2 requires Bearer token" --tags oauth,api | grep -o 'LSN[A-Z0-9]*')
echo "Created lesson: $lesson_id"

echo "# Test resource" > /tmp/test-resource.md
resource_id=$(ai-lessons contribute add-resource -t doc /tmp/test-resource.md --version v3 --tags api 2>&1 | grep -o 'RES[A-Z0-9.]*' | head -1)
echo "Created resource: $resource_id"

rule_id=$(ai-lessons contribute suggest-rule -t "Use strict typing" -c "Enable strict mode" -r "Catches bugs" --tags typescript | grep -o 'RUL[A-Z0-9]*')
echo "Created rule: $rule_id"

echo -e "\n=== Test 2: Verify ID prefixes ==="
[[ $lesson_id == LSN* ]] && echo "✓ Lesson ID has LSN prefix"
[[ $resource_id == RES* ]] && echo "✓ Resource ID has RES prefix"
[[ $rule_id == RUL* ]] && echo "✓ Rule ID has RUL prefix"

echo -e "\n=== Test 3: Unified search ==="
ai-lessons recall search "OAuth2"
ai-lessons recall search "OAuth2" --type lesson
ai-lessons recall search "OAuth2" --type resource
ai-lessons recall search "OAuth2" --lesson-confidence-min medium

echo -e "\n=== Test 4: Unified show ==="
ai-lessons recall show $lesson_id
ai-lessons recall show $resource_id
ai-lessons recall show $rule_id

echo -e "\n=== Test 5: Unified list ==="
ai-lessons recall list --type lesson
ai-lessons recall list --type resource
ai-lessons recall list --type rule

echo -e "\n=== Test 6: Unified update ==="
ai-lessons contribute update $lesson_id --title "Updated lesson"
ai-lessons contribute update $resource_id --tags new,tags
ai-lessons contribute update $rule_id --rule-rationale "Better rationale"

echo -e "\n=== Test 7: Link and unlink ==="
ai-lessons contribute link $lesson_id $resource_id --relation documents
ai-lessons recall related $lesson_id
ai-lessons contribute unlink $lesson_id $resource_id

echo -e "\n=== Test 8: Refresh ==="
echo "# Updated content" > /tmp/test-resource.md
ai-lessons contribute refresh $resource_id

echo -e "\n=== Test 9: Delete ==="
ai-lessons contribute delete $lesson_id --yes
ai-lessons contribute delete $resource_id --yes
ai-lessons contribute delete $rule_id --yes

echo -e "\n=== Test 10: Smart errors ==="
# Try to update a chunk (should error)
chunk_id="${resource_id}.0"
ai-lessons contribute update $chunk_id --title "Test" 2>&1 | grep -q "Chunks are updated via their parent" && echo "✓ Smart error for chunk update"

echo -e "\n=== All tests passed! ==="
```

Run the test script:
```bash
chmod +x /tmp/test-unified-cli.sh
/tmp/test-unified-cli.sh
```

---

## Chunk 25: Documentation Updates

### Goal
Update README or CLI help text to reflect the new unified commands.

### Files to Modify
- Project README (if exists)
- CLI command docstrings (already done in chunks above)

### Changes

Ensure all command docstrings clearly explain:
1. Type-prefixed IDs (LSN, RES, RUL)
2. Namespaced options (--lesson-*, --resource-*, --rule-*)
3. Auto-detection from ID prefixes
4. Smart error messages
5. Examples showing the unified approach

### Testing
```bash
# Verify help text
ai-lessons recall search --help
ai-lessons recall show --help
ai-lessons recall list --help
ai-lessons contribute update --help
ai-lessons contribute delete --help
ai-lessons contribute link --help
```

---

## Summary

This implementation is broken into 25 discrete chunks:

1. Schema v12 migration (refuse and instruct)
2. Core ID generation functions
3. Update chunk ID generation
4. Update add_lesson() to use prefixed IDs
5. Update add_resource() to use prefixed IDs
6. Update suggest_rule() to use prefixed IDs
7. Add list_lessons() function
8. Add list_rules() function
9. Add update_resource() function
10. Update display functions for 15-char truncation
11. Update ID display in recall.py
12. Update ID display in contribute.py
13. Update ID display in admin.py
14. Unified recall search command
15. Unified recall show command
16. Unified recall list command
17. Unified recall related command
18. Unified contribute update command
19. Unified contribute delete command
20. Unified contribute link/unlink commands
21. contribute refresh command
22. Remove admin reject-rule command
23. Add deprecation warnings to old commands
24. Integration testing
25. Documentation updates

Each chunk is testable independently. Follow the plan exactly as written.

---

**STOP**: Before continuing work after a compactification, DO NOT mark re-reading this document as complete. Repeat, DO NOT mark the "READ .../SPECS.md BEFORE DOING ANYTHING ELSE" item as complete. That todo item is intended to help ensure that this document is re-read across compactifications until this cleanup process is complete. DO NOT mark that todo item as complete until this implementation is complete.

When the system prompts you to create a summary for the next session, include a **STRONG instruction** to RE-READ THIS DOCUMENT (`docs/implementation/v6-cli-unification/SPECS.md`) before doing anything else.

---

**WORK UNTIL COMPLETE**: Do NOT prompt the user for feedback, questions, or input until ALL chunks have been completed and ALL todo items are marked done. Work autonomously through each chunk in order, running verification tests after each chunk, and only engage the user once the final verification is complete.
