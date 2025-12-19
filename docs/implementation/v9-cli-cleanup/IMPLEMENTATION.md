# Implementation Plan: v9.1 Info Command Group

## Current Implementation Locations

### recall.py (CLI commands to migrate)
- `recall tags` - Lines 406-420 (calls `core.list_tags`)
- `recall confidence` - Lines 436-442 (calls `core.list_confidence_levels`)
- `recall sources` - Lines 423-433 (calls `core.list_sources`)

### admin.py (CLI command to migrate)
- `admin stats` - Lines 45-115 (inline SQL queries, not using core functions)

### core.py (core functions)
- `list_tags()` - Lines 1530-1560 (only queries lesson_tags, no resource/rule support)
- `list_sources()` - Lines 1563-1588
- `list_confidence_levels()` - Lines 1591-1612

### Schema (schema.py)
- `confidence_levels` table - Lines 16-19 (name, ordinal)
- `source_types` table - Lines 21-25 (name, description, typical_confidence)
- `tag_relations` table - Lines 67-72 (from_tag, to_tag, relation)
- `edges` table - Lines 55-64 (from_id, from_type, to_id, to_type, relation)
- Tag tables: `lesson_tags` (40-44), `resource_tags` (109-113), `rule_tags` (149-153)

## Key Observations

1. **list_tags() is incomplete** - Only queries `lesson_tags`, not `resource_tags` or `rule_tags`
2. **No relations listing** - No function to list distinct edge relation types
3. **admin stats uses inline SQL** - Should be refactored to core functions
4. **tag_relations table exists but is not queried** - For alias support

---

## Files to Create

### 1. `src/ai_lessons/cli/info.py` (NEW)

```python
"""Info CLI commands for schema discovery and database statistics."""

from __future__ import annotations

from typing import Optional

import click

from .. import core
from ..config import get_config


@click.group()
def info():
    """Schema discovery and database statistics."""
    pass


@info.command("tags")
@click.option("--counts", is_flag=True, help="Show usage counts per entity type")
@click.option("--type", "entity_type", type=click.Choice(["lesson", "resource", "rule"]),
              help="Filter by entity type")
@click.option("--pattern", "-p", help="Filter tags by substring (case-insensitive)")
@click.option("--unused", is_flag=True, help="Show only tags in tag_relations with zero usage")
@click.option("--sort", type=click.Choice(["name", "count"]), default="name",
              help="Sort order (default: name)")
def tags(counts: bool, entity_type: Optional[str], pattern: Optional[str],
         unused: bool, sort: str):
    """List all tags with usage information.

    Shows active tags across all entity types, plus any defined tag aliases.
    """
    pass  # Implementation details below


@info.command("confidence")
@click.option("--counts", is_flag=True, help="Show how many lessons at each level")
def confidence(counts: bool):
    """List confidence levels."""
    pass


@info.command("lesson-sources")
@click.option("--counts", is_flag=True, help="Show how many lessons use each source")
@click.option("--verbose", "-v", is_flag=True, help="Show descriptions and typical confidence")
def lesson_sources(counts: bool, verbose: bool):
    """List source types for lessons."""
    pass


@info.command("relations")
@click.option("--counts", is_flag=True, help="Show edge counts per relation type")
@click.option("--type", "entity_type", type=click.Choice(["lesson", "resource", "rule"]),
              help="Filter by from/to entity type")
def relations(counts: bool, entity_type: Optional[str]):
    """List edge relation types used in the graph."""
    pass


@info.command("stats")
@click.option("--json", "json_output", is_flag=True, help="Machine-readable JSON output")
@click.option("--verbose", "-v", is_flag=True, help="Detailed breakdown")
def stats(json_output: bool, verbose: bool):
    """Show database statistics."""
    pass
```

---

## Files to Modify

### 2. `src/ai_lessons/cli/__init__.py`

**Add import (after line 9):**
```python
from .info import info
```

**Add command (after line 30):**
```python
main.add_command(info)
```

**Update docstring (lines 15-23):**
```python
    """AI Lessons - Knowledge management with semantic search.

    Commands are organized into four groups:

    \b
      admin       Database and system management
      contribute  Add and modify lessons, resources, and rules
      info        Schema discovery and statistics
      recall      Search and view lessons
    """
```

### 3. `src/ai_lessons/core.py`

#### New Dataclasses (after line 247, after `Tag` class)

```python
@dataclass
class TagInfo:
    """Tag with detailed usage counts."""
    name: str
    lesson_count: int = 0
    resource_count: int = 0
    rule_count: int = 0

    @property
    def total_count(self) -> int:
        return self.lesson_count + self.resource_count + self.rule_count


@dataclass
class RelationType:
    """An edge relation type with usage count."""
    name: str
    count: int = 0
```

#### Update ConfidenceLevel dataclass (line 237-240)

```python
@dataclass
class ConfidenceLevel:
    """A confidence level with its ordinal."""
    name: str
    ordinal: int
    count: int = 0  # Optional usage count
```

#### Update SourceType dataclass (line 228-233)

```python
@dataclass
class SourceType:
    """A source type with its metadata."""
    name: str
    description: Optional[str] = None
    typical_confidence: Optional[str] = None
    count: int = 0  # Optional usage count
```

#### New Functions (after line 1560, after `list_tags`)

```python
def list_tags_detailed(
    entity_type: Optional[str] = None,
    pattern: Optional[str] = None,
    config: Optional[Config] = None,
) -> list[TagInfo]:
    """List all tags with per-entity-type counts."""
    # Implementation uses SQL query across all tag tables
    pass


def list_tag_aliases(config: Optional[Config] = None) -> list[tuple[str, str]]:
    """List tag aliases from tag_relations table."""
    # SELECT from_tag, to_tag FROM tag_relations WHERE relation = 'alias'
    pass


def list_relations(
    entity_type: Optional[str] = None,
    config: Optional[Config] = None,
) -> list[RelationType]:
    """List distinct edge relation types with counts."""
    pass


def get_database_stats(config: Optional[Config] = None) -> dict:
    """Get comprehensive database statistics."""
    # Move logic from admin.py stats command
    pass
```

#### Enhance list_confidence_levels (around line 1591)

Add `with_counts: bool = False` parameter.

#### Enhance list_sources (around line 1563)

Add `with_counts: bool = False` parameter.

### 4. `src/ai_lessons/cli/recall.py`

**Add deprecation warnings to old commands (lines 406-442):**

```python
@recall.command("tags")
def list_tags(...):
    """... DEPRECATED: Use 'ai-lessons info tags' instead."""
    warn_deprecation("recall tags", "info tags")
    # ... rest unchanged

@recall.command("sources")
def list_sources():
    """... DEPRECATED: Use 'ai-lessons info lesson-sources' instead."""
    warn_deprecation("recall sources", "info lesson-sources")
    # ... rest unchanged

@recall.command("confidence")
def list_confidence():
    """... DEPRECATED: Use 'ai-lessons info confidence' instead."""
    warn_deprecation("recall confidence", "info confidence")
    # ... rest unchanged
```

### 5. `src/ai_lessons/cli/admin.py`

**Add deprecation warning to stats (line 45-115):**

```python
@admin.command()
def stats():
    """... DEPRECATED: Use 'ai-lessons info stats' instead."""
    warn_deprecation("admin stats", "info stats")
    # ... rest unchanged or refactor to use core.get_database_stats()
```

---

## SQL Queries

### Tags with counts
```sql
SELECT
    tag,
    SUM(CASE WHEN source = 'lesson' THEN 1 ELSE 0 END) as lesson_count,
    SUM(CASE WHEN source = 'resource' THEN 1 ELSE 0 END) as resource_count,
    SUM(CASE WHEN source = 'rule' THEN 1 ELSE 0 END) as rule_count
FROM (
    SELECT tag, 'lesson' as source FROM lesson_tags
    UNION ALL
    SELECT tag, 'resource' as source FROM resource_tags
    UNION ALL
    SELECT tag, 'rule' as source FROM rule_tags
) combined
GROUP BY tag
ORDER BY tag;
```

### Tag aliases
```sql
SELECT from_tag, to_tag
FROM tag_relations
WHERE relation = 'alias'
ORDER BY from_tag;
```

### Unused tags in tag_relations
```sql
SELECT tr.from_tag as tag
FROM tag_relations tr
WHERE tr.relation = 'alias'
AND NOT EXISTS (
    SELECT 1 FROM lesson_tags lt WHERE lt.tag = tr.from_tag
    UNION
    SELECT 1 FROM resource_tags rt WHERE rt.tag = tr.from_tag
    UNION
    SELECT 1 FROM rule_tags rut WHERE rut.tag = tr.from_tag
);
```

### Edge relations with counts
```sql
SELECT relation, COUNT(*) as count
FROM edges
GROUP BY relation
ORDER BY count DESC, relation;
```

### Confidence levels with counts
```sql
SELECT cl.name, cl.ordinal, COUNT(l.id) as count
FROM confidence_levels cl
LEFT JOIN lessons l ON l.confidence = cl.name
GROUP BY cl.name, cl.ordinal
ORDER BY cl.ordinal;
```

### Source types with counts
```sql
SELECT st.name, st.description, st.typical_confidence, COUNT(l.id) as count
FROM source_types st
LEFT JOIN lessons l ON l.source = st.name
GROUP BY st.name, st.description, st.typical_confidence
ORDER BY st.name;
```

---

## Implementation Order

1. **core.py changes first** - Add dataclasses and new functions
2. **Create info.py** - New CLI module with all commands (with `--json` on all)
3. **Update __init__.py** - Register info command group
4. **Delete from recall.py** - Remove `tags`, `sources`, `confidence` commands
5. **Delete from admin.py** - Remove `stats` command
6. **Tests** - Add tests for new info commands

---

## Decisions Made

1. **No deprecation warnings** - Just remove old commands (pre-1.0, no users)
2. **Remove `admin stats`** - Don't alias, just delete
3. **Add `--json`** - All info commands get `--json` output option
