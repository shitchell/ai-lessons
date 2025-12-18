# v4-cleanup: Comprehensive Refactoring Plan

**Created**: 2025-12-17
**Status**: Planning Complete
**Estimated Chunks**: 9 implementation chunks

---

## Table of Contents

1. [Overview](#overview)
2. [Implementation Chunks](#implementation-chunks)
3. [Chunk 1: DRY Helpers - Tags & Properties](#chunk-1-dry-helpers---tags--properties)
4. [Chunk 2: DRY Helpers - Filters & Embeddings](#chunk-2-dry-helpers---filters--embeddings)
5. [Chunk 3: SearchResult Inheritance Refactor](#chunk-3-searchresult-inheritance-refactor)
6. [Chunk 4: Unified Edges Schema (v9)](#chunk-4-unified-edges-schema-v9)
7. [Chunk 5: CLI Directory Split](#chunk-5-cli-directory-split)
8. [Chunk 6: Exception Handling & Basic Type Hints](#chunk-6-exception-handling--basic-type-hints)
9. [Chunk 7: Missing Features (Rules, Batch Ops)](#chunk-7-missing-features-rules-batch-ops)
10. [Chunk 8: Strict Type Hinting & mypy](#chunk-8-strict-type-hinting--mypy)
11. [Chunk 9: Constants, Tests & Documentation](#chunk-9-constants-tests--documentation)
12. [Important Notes for Future Sessions](#important-notes-for-future-sessions)

---

## Overview

This refactoring addresses issues identified in the code review (`docs/implementation/v4-cleanup/CODE_REVIEW.md`). The work is divided into 9 chunks, each designed to be completable within a ~120k context window.

### Key Decisions (User Confirmed)

1. **SearchResult**: Use inheritance (`LessonResult(SearchResult)`) - Liskov substitution
2. **Link tables**: Unify into `edges` table, rename `resource_links` to `resource_anchors`
3. **Contexts**: Keep case-sensitive (do NOT normalize like tags)
4. **CLI**: Split into `cli/` directory with multiple modules
5. **Scope**: Complete all highest-priority items

### Files Overview

```
src/ai_lessons/
├── __init__.py          # Package init, version
├── chunking.py          # Document chunking logic
├── cli.py               # CLI commands (1811 lines) → will become cli/
├── config.py            # Configuration management
├── core.py              # Core API (2664 lines)
├── db.py                # Database operations
├── embeddings.py        # Embedding backends
├── links.py             # Link extraction from markdown
├── schema.py            # SQL schema definitions
├── search.py            # Search operations (1100+ lines)
└── mcp_server.py        # MCP server (if exists)
```

---

## Implementation Chunks

| Chunk | Description | Est. Lines Changed | Dependencies |
|-------|-------------|-------------------|--------------|
| 1 | DRY Helpers - Tags & Properties | ~150 | None |
| 2 | DRY Helpers - Filters & Embeddings | ~200 | None |
| 3 | SearchResult Inheritance | ~300 | None |
| 4 | Unified Edges Schema (v9) | ~400 | Chunks 1-2 |
| 5 | CLI Directory Split | ~1800 (reorganize) | None |
| 6 | Exception Handling & Basic Type Hints | ~100 | None |
| 7 | Missing Features | ~200 | Chunks 1-4 |
| 8 | Strict Type Hinting & mypy | ~400 | Chunks 1-7 |
| 9 | Constants, Tests & Docs | ~300 | All above |

---

## Chunk 1: DRY Helpers - Tags & Properties

**Goal**: Extract duplicated tag handling and lesson property fetching into reusable helpers.

### 1.1 - Create `_save_tags()` Helper

**Location**: `src/ai_lessons/core.py`

**Current Duplication** (3 places):

```python
# Lessons - core.py lines 248-252
if tags:
    conn.executemany(
        "INSERT INTO lesson_tags (lesson_id, tag) VALUES (?, ?)",
        [(lesson_id, tag) for tag in tags],
    )

# Resources - core.py lines 1354-1358
if tags:
    conn.executemany(
        "INSERT INTO resource_tags (resource_id, tag) VALUES (?, ?)",
        [(resource_id, tag) for tag in tags],
    )

# Rules - core.py lines 1972-1976
if tags:
    conn.executemany(
        "INSERT INTO rule_tags (rule_id, tag) VALUES (?, ?)",
        [(rule_id, tag) for tag in tags],
    )
```

**New Helper** (add after line ~190 in core.py, near other helpers):

```python
def _save_tags(
    conn: sqlite3.Connection,
    entity_id: str,
    entity_type: str,
    tags: Optional[list[str]],
) -> None:
    """Save tags for an entity.

    Args:
        conn: Database connection (within transaction).
        entity_id: ID of the entity.
        entity_type: One of 'lesson', 'resource', 'rule'.
        tags: List of tags to save.
    """
    if not tags:
        return

    table_map = {
        'lesson': ('lesson_tags', 'lesson_id'),
        'resource': ('resource_tags', 'resource_id'),
        'rule': ('rule_tags', 'rule_id'),
    }

    if entity_type not in table_map:
        raise ValueError(f"Unknown entity type: {entity_type}")

    table, id_col = table_map[entity_type]
    conn.executemany(
        f"INSERT INTO {table} ({id_col}, tag) VALUES (?, ?)",
        [(entity_id, tag) for tag in tags],
    )


def _delete_tags(
    conn: sqlite3.Connection,
    entity_id: str,
    entity_type: str,
) -> None:
    """Delete all tags for an entity.

    Args:
        conn: Database connection (within transaction).
        entity_id: ID of the entity.
        entity_type: One of 'lesson', 'resource', 'rule'.
    """
    table_map = {
        'lesson': ('lesson_tags', 'lesson_id'),
        'resource': ('resource_tags', 'resource_id'),
        'rule': ('rule_tags', 'rule_id'),
    }

    if entity_type not in table_map:
        raise ValueError(f"Unknown entity type: {entity_type}")

    table, id_col = table_map[entity_type]
    conn.execute(f"DELETE FROM {table} WHERE {id_col} = ?", (entity_id,))


def _get_tags(
    conn: sqlite3.Connection,
    entity_id: str,
    entity_type: str,
) -> list[str]:
    """Get tags for an entity.

    Args:
        conn: Database connection.
        entity_id: ID of the entity.
        entity_type: One of 'lesson', 'resource', 'rule'.

    Returns:
        List of tags.
    """
    table_map = {
        'lesson': ('lesson_tags', 'lesson_id'),
        'resource': ('resource_tags', 'resource_id'),
        'rule': ('rule_tags', 'rule_id'),
    }

    if entity_type not in table_map:
        raise ValueError(f"Unknown entity type: {entity_type}")

    table, id_col = table_map[entity_type]
    cursor = conn.execute(
        f"SELECT tag FROM {table} WHERE {id_col} = ?",
        (entity_id,),
    )
    return [row["tag"] for row in cursor.fetchall()]
```

**Update Call Sites**:

| Location | Current | New |
|----------|---------|-----|
| `add_lesson()` line 248-252 | inline executemany | `_save_tags(conn, lesson_id, 'lesson', tags)` |
| `update_lesson()` line 410-416 | delete + inline executemany | `_delete_tags(conn, lesson_id, 'lesson')` then `_save_tags(...)` |
| `add_resource()` line 1354-1358 | inline executemany | `_save_tags(conn, resource_id, 'resource', tags)` |
| `_reimport_resource()` line 1460-1466 | delete + inline | `_delete_tags(...)` then `_save_tags(...)` |
| `suggest_rule()` line 1972-1976 | inline executemany | `_save_tags(conn, rule_id, 'rule', tags)` |

### 1.2 - Create `_fetch_lesson_properties()` Helper

**Location**: `src/ai_lessons/core.py`

**Current Duplication** (2 places):

```python
# get_lesson() - core.py lines 304-322
cursor = conn.execute(
    "SELECT tag FROM lesson_tags WHERE lesson_id = ?",
    (lesson_id,),
)
tags = [r["tag"] for r in cursor.fetchall()]

cursor = conn.execute(
    "SELECT context, applies FROM lesson_contexts WHERE lesson_id = ?",
    (lesson_id,),
)
contexts = []
anti_contexts = []
for r in cursor.fetchall():
    if r["applies"]:
        contexts.append(r["context"])
    else:
        anti_contexts.append(r["context"])

# search.py _row_to_result() lines 453-470 - SAME PATTERN
```

**New Helper** (add near other helpers in core.py):

```python
def _fetch_lesson_properties(
    conn: sqlite3.Connection,
    lesson_id: str,
) -> tuple[list[str], list[str], list[str]]:
    """Fetch tags, contexts, and anti_contexts for a lesson.

    Args:
        conn: Database connection.
        lesson_id: The lesson ID.

    Returns:
        Tuple of (tags, contexts, anti_contexts).
    """
    # Get tags
    cursor = conn.execute(
        "SELECT tag FROM lesson_tags WHERE lesson_id = ?",
        (lesson_id,),
    )
    tags = [r["tag"] for r in cursor.fetchall()]

    # Get contexts
    cursor = conn.execute(
        "SELECT context, applies FROM lesson_contexts WHERE lesson_id = ?",
        (lesson_id,),
    )
    contexts = []
    anti_contexts = []
    for r in cursor.fetchall():
        if r["applies"]:
            contexts.append(r["context"])
        else:
            anti_contexts.append(r["context"])

    return tags, contexts, anti_contexts
```

**Update Call Sites**:

| Location | File | Change |
|----------|------|--------|
| `get_lesson()` lines 304-322 | core.py | Replace with `tags, contexts, anti_contexts = _fetch_lesson_properties(conn, lesson_id)` |
| `_row_to_result()` lines 453-470 | search.py | Import helper, replace inline code |

**Note**: The search.py usage requires importing from core. Add to imports at top of search.py:
```python
from .core import _fetch_lesson_properties
```

### 1.3 - Create `_fetch_resource_metadata()` Helper

**Location**: `src/ai_lessons/search.py`

**Current Duplication** (2 places in search.py):

```python
# _process_resource_row() lines 690-700
cursor = conn.execute(
    "SELECT version FROM resource_versions WHERE resource_id = ?",
    (resource_id,)
)
versions = {r["version"] for r in cursor.fetchall()}

cursor = conn.execute(
    "SELECT tag FROM resource_tags WHERE resource_id = ?",
    (resource_id,)
)
tags = [r["tag"] for r in cursor.fetchall()]

# _process_chunk_row() lines 745-755 - SAME PATTERN
```

**New Helper** (add in search.py near line 670):

```python
def _fetch_resource_metadata(
    conn: sqlite3.Connection,
    resource_id: str,
) -> tuple[set[str], list[str]]:
    """Fetch versions and tags for a resource.

    Args:
        conn: Database connection.
        resource_id: The resource ID.

    Returns:
        Tuple of (versions_set, tags_list).
    """
    cursor = conn.execute(
        "SELECT version FROM resource_versions WHERE resource_id = ?",
        (resource_id,),
    )
    versions = {r["version"] for r in cursor.fetchall()}

    cursor = conn.execute(
        "SELECT tag FROM resource_tags WHERE resource_id = ?",
        (resource_id,),
    )
    tags = [r["tag"] for r in cursor.fetchall()]

    return versions, tags
```

**Update Call Sites**:

| Location | Change |
|----------|--------|
| `_process_resource_row()` lines 690-700 | `versions, tags = _fetch_resource_metadata(conn, resource_id)` |
| `_process_chunk_row()` lines 745-755 | `versions, tags = _fetch_resource_metadata(conn, row["resource_id"])` |

### Chunk 1 Verification

After completing Chunk 1, run:
```bash
python -m pytest tests/ -v
ai-lessons recall search "test query"
ai-lessons contribute add -t "Test" -c "Test content" --tag test
```

---

## Chunk 2: DRY Helpers - Filters & Embeddings

**Goal**: Extract duplicated filter-building SQL and embedding storage logic.

### 2.1 - Create Filter Builder Helpers

**Location**: `src/ai_lessons/search.py`

**Current Duplication**: Filter clauses built identically in:
- `_execute_vector_search()` lines 342-380
- `_get_filtered_lessons()` lines 394-431
- `search_resources()` lines 595-620

**New Helpers** (add near top of search.py, after imports):

```python
def _build_lesson_filter_clauses(
    tag_filter: Optional[list[str]] = None,
    context_filter: Optional[list[str]] = None,
    confidence_min: Optional[str] = None,
    source: Optional[str] = None,
) -> tuple[list[str], list]:
    """Build SQL WHERE clauses for lesson filtering.

    Args:
        tag_filter: Filter by tags (ANY match).
        context_filter: Filter by contexts.
        confidence_min: Minimum confidence level.
        source: Filter by source type.

    Returns:
        Tuple of (list of SQL clause strings, list of parameters).
        Clauses do NOT include "WHERE" or "AND" prefix.
    """
    clauses = []
    params = []

    if tag_filter:
        placeholders = ",".join("?" * len(tag_filter))
        clauses.append(f"""
            l.id IN (
                SELECT lesson_id FROM lesson_tags
                WHERE tag IN ({placeholders})
            )
        """)
        params.extend(tag_filter)

    if context_filter:
        placeholders = ",".join("?" * len(context_filter))
        clauses.append(f"""
            l.id IN (
                SELECT lesson_id FROM lesson_contexts
                WHERE context IN ({placeholders}) AND applies = TRUE
            )
        """)
        params.extend(context_filter)

    if confidence_min:
        clauses.append("""
            l.confidence IN (
                SELECT name FROM confidence_levels
                WHERE ordinal >= (
                    SELECT ordinal FROM confidence_levels WHERE name = ?
                )
            )
        """)
        params.append(confidence_min)

    if source:
        clauses.append("l.source = ?")
        params.append(source)

    return clauses, params


def _build_resource_filter_clauses(
    tag_filter: Optional[list[str]] = None,
    resource_type: Optional[str] = None,
    versions: Optional[list[str]] = None,
) -> tuple[list[str], list]:
    """Build SQL WHERE clauses for resource filtering.

    Args:
        tag_filter: Filter by tags (ANY match).
        resource_type: Filter by type ('doc' or 'script').
        versions: Filter by versions.

    Returns:
        Tuple of (list of SQL clause strings, list of parameters).
    """
    clauses = []
    params = []

    if tag_filter:
        placeholders = ",".join("?" * len(tag_filter))
        clauses.append(f"""
            r.id IN (
                SELECT resource_id FROM resource_tags
                WHERE tag IN ({placeholders})
            )
        """)
        params.extend(tag_filter)

    if resource_type:
        clauses.append("r.type = ?")
        params.append(resource_type)

    if versions:
        placeholders = ",".join("?" * len(versions))
        clauses.append(f"""
            r.id IN (
                SELECT resource_id FROM resource_versions
                WHERE version IN ({placeholders})
            )
        """)
        params.extend(versions)

    return clauses, params
```

**Update Call Sites**:

| Function | Lines | Change |
|----------|-------|--------|
| `_execute_vector_search()` | 342-380 | Use `_build_lesson_filter_clauses()`, join with " AND " |
| `_get_filtered_lessons()` | 394-431 | Use `_build_lesson_filter_clauses()` |
| `search_resources()` | 595-620 | Use `_build_resource_filter_clauses()` |

**Example Update for `_execute_vector_search()`**:

```python
# Before (lines 342-380): ~40 lines of inline filter building

# After:
filter_clauses, filter_params = _build_lesson_filter_clauses(
    tag_filter=tag_filter,
    context_filter=context_filter,
    confidence_min=confidence_min,
    source=source,
)

if filter_clauses:
    filter_sql = " AND " + " AND ".join(filter_clauses)
else:
    filter_sql = ""

# Use filter_sql and filter_params in query
```

### 2.2 - Create Embedding Storage Helper

**Location**: `src/ai_lessons/core.py`

**Current Duplication** (4 places):

```python
# add_lesson() lines 232-235, 268-271
embedding = embed_text(f"{title}\n\n{content}", config)
embedding_blob = struct.pack(f"{len(embedding)}f", *embedding)
conn.execute(
    "INSERT INTO lesson_embeddings (lesson_id, embedding) VALUES (?, ?)",
    (lesson_id, embedding_blob),
)

# add_resource() lines 1333-1335, 1361-1364 - similar
# _reimport_resource() lines 1422-1425, 1469-1473 - similar
# _store_chunks() lines 1084-1090 - similar for chunks
```

**New Helper** (add in core.py near other helpers):

```python
def _store_embedding(
    conn: sqlite3.Connection,
    entity_id: str,
    entity_type: str,
    text: str,
    config: Config,
) -> None:
    """Generate and store embedding for an entity.

    Args:
        conn: Database connection (within transaction).
        entity_id: ID of the entity.
        entity_type: One of 'lesson', 'resource', 'chunk'.
        text: Text to embed.
        config: Configuration for embedding model.
    """
    embedding = embed_text(text, config)
    embedding_blob = struct.pack(f"{len(embedding)}f", *embedding)

    table_map = {
        'lesson': ('lesson_embeddings', 'lesson_id'),
        'resource': ('resource_embeddings', 'resource_id'),
        'chunk': ('chunk_embeddings', 'chunk_id'),
    }

    if entity_type not in table_map:
        raise ValueError(f"Unknown entity type: {entity_type}")

    table, id_col = table_map[entity_type]
    conn.execute(
        f"INSERT INTO {table} ({id_col}, embedding) VALUES (?, ?)",
        (entity_id, embedding_blob),
    )


def _delete_embedding(
    conn: sqlite3.Connection,
    entity_id: str,
    entity_type: str,
) -> None:
    """Delete embedding for an entity.

    Args:
        conn: Database connection (within transaction).
        entity_id: ID of the entity.
        entity_type: One of 'lesson', 'resource', 'chunk'.
    """
    table_map = {
        'lesson': ('lesson_embeddings', 'lesson_id'),
        'resource': ('resource_embeddings', 'resource_id'),
        'chunk': ('chunk_embeddings', 'chunk_id'),
    }

    if entity_type not in table_map:
        raise ValueError(f"Unknown entity type: {entity_type}")

    table, id_col = table_map[entity_type]
    conn.execute(f"DELETE FROM {table} WHERE {id_col} = ?", (entity_id,))
```

**Update Call Sites**:

| Function | Lines | Change |
|----------|-------|--------|
| `add_lesson()` | 232-235, 268-271 | `_store_embedding(conn, lesson_id, 'lesson', f"{title}\n\n{content}", config)` |
| `update_lesson()` | 436-446 | `_delete_embedding(...)` then `_store_embedding(...)` |
| `add_resource()` | 1333-1335, 1361-1364 | `_store_embedding(conn, resource_id, 'resource', ...)` |
| `_reimport_resource()` | 1468-1473 | `_delete_embedding(...)` then `_store_embedding(...)` |
| `_store_chunks()` | 1084-1090 | `_store_embedding(conn, chunk_id, 'chunk', embed_input, config)` |

### Chunk 2 Verification

After completing Chunk 2, run:
```bash
python -m pytest tests/ -v
ai-lessons recall search "jira voting"
ai-lessons recall search-resources "filter"
```

---

## Chunk 3: SearchResult Inheritance Refactor

**Goal**: Replace the monolithic `SearchResult` dataclass with an inheritance hierarchy.

### 3.1 - Define Base Class and Subclasses

**Location**: `src/ai_lessons/search.py` lines 14-56

**Current** (25+ fields, many optional):
```python
@dataclass
class SearchResult:
    id: str
    title: str
    content: str
    score: float
    result_type: str  # "lesson", "resource", "chunk", "rule"
    tags: list[str]
    # ... 20+ more optional fields
```

**New Structure** (replace lines 14-56):

```python
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SearchResult:
    """Base class for all search results."""
    id: str
    title: str
    content: str
    score: float
    result_type: str
    tags: list[str] = field(default_factory=list)


@dataclass
class LessonResult(SearchResult):
    """Search result for a lesson."""
    confidence: Optional[str] = None
    source: Optional[str] = None
    source_notes: Optional[str] = None
    contexts: list[str] = field(default_factory=list)
    anti_contexts: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.result_type = "lesson"


@dataclass
class ResourceResult(SearchResult):
    """Search result for a resource (doc or script)."""
    resource_type: Optional[str] = None  # 'doc' or 'script'
    versions: list[str] = field(default_factory=list)
    path: Optional[str] = None

    def __post_init__(self):
        self.result_type = "resource"


@dataclass
class ChunkResult(SearchResult):
    """Search result for a document chunk."""
    chunk_index: Optional[int] = None
    breadcrumb: Optional[str] = None
    resource_id: Optional[str] = None
    resource_title: Optional[str] = None
    versions: list[str] = field(default_factory=list)
    summary: Optional[str] = None
    sections: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.result_type = "chunk"


@dataclass
class RuleResult(SearchResult):
    """Search result for a rule."""
    rationale: Optional[str] = None
    approved: Optional[bool] = None

    def __post_init__(self):
        self.result_type = "rule"
```

### 3.2 - Update Result Creation Functions

**Functions that create SearchResult objects**:

| Function | File | Line | Change |
|----------|------|------|--------|
| `_row_to_result()` | search.py | 439 | Return `LessonResult(...)` |
| `_process_resource_row()` | search.py | 682 | Return `ResourceResult(...)` |
| `_process_chunk_row()` | search.py | 732 | Return `ChunkResult(...)` |
| `search_rules()` | search.py | 899 | Return `RuleResult(...)` in list |

**Example Update for `_row_to_result()`** (search.py ~line 439):

```python
# Before:
return SearchResult(
    id=row["id"],
    title=row["title"],
    content=row["content"],
    score=score,
    result_type="lesson",
    tags=tags,
    confidence=row["confidence"],
    source=row["source"],
    source_notes=row["source_notes"],
    contexts=contexts,
    anti_contexts=anti_contexts,
    # ... many None fields for other types
)

# After:
return LessonResult(
    id=row["id"],
    title=row["title"],
    content=row["content"],
    score=score,
    result_type="lesson",
    tags=tags,
    confidence=row["confidence"],
    source=row["source"],
    source_notes=row["source_notes"],
    contexts=contexts,
    anti_contexts=anti_contexts,
)
```

### 3.3 - Update CLI Display Function

**Location**: `src/ai_lessons/cli.py` lines 69-160 (`_format_search_result`)

The display function checks `result.result_type` to format differently. This still works with inheritance since all subclasses have `result_type`.

**Minor updates needed**:
- Line 85: `result.chunk_breadcrumb` → `result.breadcrumb` (if we rename in ChunkResult)
- Verify all field accesses match new class structure

### 3.4 - Update Exports

**Location**: `src/ai_lessons/search.py` (end of file or `__all__`)

Ensure new classes are exported:
```python
__all__ = [
    "SearchResult",
    "LessonResult",
    "ResourceResult",
    "ChunkResult",
    "RuleResult",
    # ... existing exports
]
```

### Chunk 3 Verification

After completing Chunk 3, run:
```bash
python -m pytest tests/ -v
ai-lessons recall search "jira"
ai-lessons recall search-resources "api"
```

Verify output formatting still works correctly for all result types.

---

## Chunk 4: Unified Edges Schema (v9)

**Goal**: Unify link tables into `edges`, rename `resource_links` to `resource_anchors`.

### 4.1 - Schema Changes

**Location**: `src/ai_lessons/schema.py`

**Current Tables**:
- `edges` (lesson→lesson only)
- `lesson_links` (lesson→resource)
- `resource_links` (resource→resource with markdown metadata)

**New Schema** (SCHEMA_VERSION = 9):

```sql
-- Replace old edges table (lines 53-59)
CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id TEXT NOT NULL,
    from_type TEXT NOT NULL CHECK (from_type IN ('lesson', 'resource', 'chunk')),
    to_id TEXT NOT NULL,
    to_type TEXT NOT NULL CHECK (to_type IN ('lesson', 'resource', 'chunk')),
    relation TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(from_id, from_type, to_id, to_type, relation)
);

CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_id, from_type);
CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_id, to_type);
CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);

-- Rename resource_links to resource_anchors (lines 186-195)
-- Now references edges table for the actual link
CREATE TABLE IF NOT EXISTS resource_anchors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    edge_id INTEGER NOT NULL REFERENCES edges(id) ON DELETE CASCADE,
    to_path TEXT NOT NULL,           -- Original markdown path before resolution
    to_fragment TEXT,                -- Fragment/anchor without #
    link_text TEXT                   -- Display text from [text](path)
);

CREATE INDEX IF NOT EXISTS idx_resource_anchors_edge ON resource_anchors(edge_id);
CREATE INDEX IF NOT EXISTS idx_resource_anchors_path ON resource_anchors(to_path);
```

**Delete**: `lesson_links` table (lines 158-168) - merged into edges

### 4.2 - Migration Logic

**Location**: `src/ai_lessons/db.py` in `_run_migrations()`

Add migration for v9 (after the v8 migration block, around line 306):

```python
if current_version < 9:
    # v9: Unify link tables into edges, rename resource_links to resource_anchors

    # 1. Create new edges table structure
    conn.execute("""
        CREATE TABLE IF NOT EXISTS edges_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_id TEXT NOT NULL,
            from_type TEXT NOT NULL CHECK (from_type IN ('lesson', 'resource', 'chunk')),
            to_id TEXT NOT NULL,
            to_type TEXT NOT NULL CHECK (to_type IN ('lesson', 'resource', 'chunk')),
            relation TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(from_id, from_type, to_id, to_type, relation)
        )
    """)

    # 2. Migrate existing edges (lesson→lesson)
    conn.execute("""
        INSERT INTO edges_new (from_id, from_type, to_id, to_type, relation, created_at)
        SELECT from_id, 'lesson', to_id, 'lesson', relation, created_at
        FROM edges
    """)

    # 3. Migrate lesson_links (lesson→resource)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lesson_links'")
    if cursor.fetchone():
        conn.execute("""
            INSERT INTO edges_new (from_id, from_type, to_id, to_type, relation, created_at)
            SELECT lesson_id, 'lesson', resource_id, 'resource', relation, created_at
            FROM lesson_links
        """)
        conn.execute("DROP TABLE lesson_links")

    # 4. Create resource_anchors table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS resource_anchors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            edge_id INTEGER REFERENCES edges_new(id) ON DELETE CASCADE,
            to_path TEXT NOT NULL,
            to_fragment TEXT,
            link_text TEXT
        )
    """)

    # 5. Migrate resource_links to edges + resource_anchors
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='resource_links'")
    if cursor.fetchone():
        # Get all resource_links with resolved targets
        cursor = conn.execute("""
            SELECT id, from_resource_id, from_chunk_id, to_path, to_fragment, link_text,
                   resolved_resource_id, resolved_chunk_id
            FROM resource_links
            WHERE resolved_resource_id IS NOT NULL
        """)

        for row in cursor.fetchall():
            # Determine from_type and from_id
            if row["from_chunk_id"]:
                from_id = row["from_chunk_id"]
                from_type = "chunk"
            else:
                from_id = row["from_resource_id"]
                from_type = "resource"

            # Determine to_type and to_id
            if row["resolved_chunk_id"]:
                to_id = row["resolved_chunk_id"]
                to_type = "chunk"
            else:
                to_id = row["resolved_resource_id"]
                to_type = "resource"

            # Insert edge
            conn.execute("""
                INSERT OR IGNORE INTO edges_new (from_id, from_type, to_id, to_type, relation)
                VALUES (?, ?, ?, ?, 'references')
            """, (from_id, from_type, to_id, to_type))

            # Get the edge ID
            edge_cursor = conn.execute("""
                SELECT id FROM edges_new
                WHERE from_id = ? AND from_type = ? AND to_id = ? AND to_type = ? AND relation = 'references'
            """, (from_id, from_type, to_id, to_type))
            edge_row = edge_cursor.fetchone()

            if edge_row:
                # Insert anchor metadata
                conn.execute("""
                    INSERT INTO resource_anchors (edge_id, to_path, to_fragment, link_text)
                    VALUES (?, ?, ?, ?)
                """, (edge_row["id"], row["to_path"], row["to_fragment"], row["link_text"]))

        conn.execute("DROP TABLE resource_links")

    # 6. Replace old edges table
    conn.execute("DROP TABLE IF EXISTS edges")
    conn.execute("ALTER TABLE edges_new RENAME TO edges")

    # 7. Create indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_id, from_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_id, to_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_resource_anchors_edge ON resource_anchors(edge_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_resource_anchors_path ON resource_anchors(to_path)")

    current_version = 9
```

### 4.3 - Update Core Functions

**Location**: `src/ai_lessons/core.py`

**Functions to update**:

| Function | Current | New |
|----------|---------|-----|
| `link_lessons()` lines 599-632 | Inserts into `edges` (lesson-only) | Add `from_type='lesson', to_type='lesson'` |
| `unlink_lessons()` lines 634-669 | Deletes from `edges` | Add type filters |
| `get_related()` lines 544-597 | Queries `edges` only | Update for new schema, optionally traverse all types |
| `link_lesson_to_resource()` lines 674-707 | Inserts into `lesson_links` | Insert into `edges` with types |
| `unlink_lesson_from_resource()` lines 709-736 | Deletes from `lesson_links` | Delete from `edges` with types |
| `get_lesson_resource_links()` lines 747-783 | Queries `lesson_links` | Query `edges` with type filter |
| `get_lessons_for_resource()` lines 785-821 | Queries `lesson_links` | Query `edges` with type filter |

**Example Update for `link_lessons()`**:

```python
# Before (lines 622-628):
conn.execute(
    "INSERT INTO edges (from_id, to_id, relation) VALUES (?, ?, ?)",
    (from_id, to_id, relation),
)

# After:
conn.execute(
    """INSERT INTO edges (from_id, from_type, to_id, to_type, relation)
       VALUES (?, 'lesson', ?, 'lesson', ?)""",
    (from_id, to_id, relation),
)
```

**Example Update for `link_lesson_to_resource()`**:

```python
# Before (lines 698-701):
conn.execute(
    "INSERT INTO lesson_links (lesson_id, resource_id, relation) VALUES (?, ?, ?)",
    (lesson_id, resource_id, relation),
)

# After:
conn.execute(
    """INSERT INTO edges (from_id, from_type, to_id, to_type, relation)
       VALUES (?, 'lesson', ?, 'resource', ?)""",
    (lesson_id, resource_id, relation),
)
```

### 4.4 - Update Links Module

**Location**: `src/ai_lessons/links.py`

The `_store_and_resolve_links()` function in `core.py` (lines 1118-1178) uses `resource_links`. Update to:

1. Insert edge into `edges` table
2. Insert anchor metadata into `resource_anchors` table

**Update `_store_and_resolve_links()`** (core.py lines 1158-1175):

```python
# Before:
conn.execute(
    """
    INSERT INTO resource_links
    (from_resource_id, from_chunk_id, to_path, to_fragment, link_text,
     resolved_resource_id, resolved_chunk_id)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
    (resource_id, from_chunk_id, link.absolute_path, link.fragment,
     link.link_text, resolved_resource_id, resolved_chunk_id),
)

# After:
# Only create edge if we resolved the target
if resolved_resource_id:
    # Determine from entity
    from_id = from_chunk_id if from_chunk_id else resource_id
    from_type = "chunk" if from_chunk_id else "resource"

    # Determine to entity
    to_id = resolved_chunk_id if resolved_chunk_id else resolved_resource_id
    to_type = "chunk" if resolved_chunk_id else "resource"

    # Insert edge
    conn.execute(
        """INSERT OR IGNORE INTO edges (from_id, from_type, to_id, to_type, relation)
           VALUES (?, ?, ?, ?, 'references')""",
        (from_id, from_type, to_id, to_type),
    )

    # Get edge ID for anchor
    cursor = conn.execute(
        """SELECT id FROM edges
           WHERE from_id = ? AND from_type = ? AND to_id = ? AND to_type = ? AND relation = 'references'""",
        (from_id, from_type, to_id, to_type),
    )
    edge_row = cursor.fetchone()

    if edge_row:
        conn.execute(
            """INSERT INTO resource_anchors (edge_id, to_path, to_fragment, link_text)
               VALUES (?, ?, ?, ?)""",
            (edge_row["id"], link.absolute_path, link.fragment, link.link_text),
        )
```

### 4.5 - Update Search Link Boosting

**Location**: `src/ai_lessons/search.py` lines 1004-1024 (`_apply_link_boosting`)

Update to query unified `edges` table:

```python
# Before:
cursor = conn.execute(
    "SELECT resource_id FROM lesson_links WHERE lesson_id = ?",
    (result.id,)
)

# After:
cursor = conn.execute(
    """SELECT to_id FROM edges
       WHERE from_id = ? AND from_type = 'lesson' AND to_type = 'resource'""",
    (result.id,)
)
```

### Chunk 4 Verification

After completing Chunk 4, run:
```bash
python -m pytest tests/ -v
ai-lessons admin init --force  # Reinitialize to test migration
ai-lessons recall search "test"
ai-lessons contribute link-resource <lesson_id> <resource_id>  # Test linking
```

---

## Chunk 5: CLI Directory Split

**Goal**: Split `cli.py` (1811 lines) into a `cli/` package with focused modules.

### 5.1 - New Directory Structure

```
src/ai_lessons/
├── cli/
│   ├── __init__.py      # Main entry point, group definitions
│   ├── display.py       # Result formatting functions
│   ├── admin.py         # Admin commands
│   ├── contribute.py    # Contribute commands
│   ├── recall.py        # Recall/search commands
│   └── utils.py         # Shared utilities (_parse_tags, etc.)
└── ... (other modules unchanged)
```

### 5.2 - Create `cli/__init__.py`

**Content**: Main CLI group and command registration

```python
"""Command-line interface for ai-lessons."""

import click

from . import admin, contribute, recall


@click.group()
@click.version_option()
def main():
    """AI Lessons - Knowledge management with semantic search.

    Commands are organized into three groups:

    - admin: Database and system management
    - contribute: Add lessons, resources, rules, and feedback
    - recall: Search and view knowledge
    """
    pass


# Register command groups
main.add_command(admin.admin)
main.add_command(contribute.contribute)
main.add_command(recall.recall)


if __name__ == "__main__":
    main()
```

### 5.3 - Create `cli/utils.py`

**Content**: Shared utilities

```python
"""Shared CLI utilities."""

from typing import Optional

import click

from ..config import get_config


def parse_tags(tags: Optional[str]) -> Optional[list[str]]:
    """Parse comma-separated tags string."""
    if not tags:
        return None
    return [t.strip() for t in tags.split(",") if t.strip()]


def show_feedback_reminder():
    """Show a reminder to submit feedback after search commands."""
    config = get_config()
    if config.suggest_feedback:
        click.echo()
        click.secho(
            "Tip: Help improve ai-lessons! When done searching, run:",
            dim=True,
        )
        click.secho(
            '  ai-lessons contribute feedback -t "your goal" -q "queries;used" -n <# of searches>',
            dim=True,
        )
```

### 5.4 - Create `cli/display.py`

**Content**: All `_format_*` functions

Move from current `cli.py`:
- `_format_lesson()` (lines 38-66)
- `_format_search_result()` (lines 69-160)
- `_format_resource()` (lines 163-195)
- `_format_rule()` (lines 198-230)
- `_format_chunk()` (lines 233-265)

```python
"""Display formatting for CLI output."""

from .. import core
from ..search import SearchResult, LessonResult, ChunkResult, ResourceResult, RuleResult


def format_lesson(lesson: core.Lesson, verbose: bool = False) -> str:
    """Format a lesson for display."""
    # ... (copy from cli.py lines 38-66)


def format_search_result(result: SearchResult, verbose: bool = False) -> str:
    """Format a search result for display."""
    # ... (copy from cli.py lines 69-160)
    # Update to use isinstance() checks for better type handling:
    # if isinstance(result, ChunkResult): ...


def format_resource(resource: core.Resource, verbose: bool = False) -> str:
    """Format a resource for display."""
    # ... (copy from cli.py lines 163-195)


def format_rule(rule: core.Rule, verbose: bool = False) -> str:
    """Format a rule for display."""
    # ... (copy from cli.py lines 198-230)


def format_chunk(chunk: core.ResourceChunk, verbose: bool = False) -> str:
    """Format a chunk for display."""
    # ... (copy from cli.py lines 233-265)
```

### 5.5 - Create `cli/admin.py`

**Content**: Admin command group

Move from current `cli.py`:
- `admin` group definition (line 319-322)
- `init` command (lines 325-350)
- `status` command (lines 353-395)
- `delete-resource` command (lines 780-810)
- `feedback-stats` command (lines 813-883)

```python
"""Admin commands for ai-lessons."""

import click

from .. import core
from ..config import get_config
from ..db import init_db, get_schema_version


@click.group()
def admin():
    """Database and system management commands."""
    pass


@admin.command()
@click.option("--force", is_flag=True, help="Force reinitialization")
def init(force: bool):
    """Initialize or reinitialize the database."""
    # ... (copy from cli.py)


@admin.command()
def status():
    """Show database status and statistics."""
    # ... (copy from cli.py)


# ... other admin commands
```

### 5.6 - Create `cli/contribute.py`

**Content**: Contribute command group

Move from current `cli.py`:
- `contribute` group (lines 890-893)
- `add` command (lessons) (lines 896-970)
- `add-resource` command (lines 973-1050)
- `suggest-rule` command (lines 1053-1120)
- `approve-rule` command (lines 1123-1145)
- `reject-rule` command (lines 1148-1170)
- `link-resource` command (lines 1173-1210)
- `unlink-resource` command (lines 1213-1245)
- `feedback` command (lines 1248-1295)

### 5.7 - Create `cli/recall.py`

**Content**: Recall command group

Move from current `cli.py`:
- `recall` group (lines 1413-1422)
- `search` command (lines 1425-1465)
- `show` command (lines 1467-1478)
- `related` command (lines 1480-1510)
- `tags` command (lines 1513-1535)
- `sources` command (lines 1538-1555)
- `confidence` command (lines 1558-1575)
- `search-resources` command (lines 1528-1577)
- `show-resource` command (lines 1580-1610)
- `show-chunk` command (lines 1613-1640)
- `list-chunks` command (lines 1643-1675)
- `list-resources` command (lines 1678-1720)
- `show-rule` command (lines 1723-1750)
- `pending-rules` command (lines 1753-1780)
- `run-resource` command (lines 1783-1811)

### 5.8 - Update Package Entry Point

**Location**: `pyproject.toml`

Ensure entry point points to new location:
```toml
[project.scripts]
ai-lessons = "ai_lessons.cli:main"
```

This should still work since `cli/__init__.py` exports `main`.

### 5.9 - Delete Old `cli.py`

After verifying everything works, delete `src/ai_lessons/cli.py`.

### Chunk 5 Verification

After completing Chunk 5, run:
```bash
python -m pytest tests/ -v
ai-lessons --help
ai-lessons admin --help
ai-lessons contribute --help
ai-lessons recall --help
ai-lessons recall search "test"
```

---

## Chunk 6: Exception Handling & Basic Type Hints

**Goal**: Replace broad `except Exception` with specific exceptions, add basic missing type hints.

### 6.1 - Fix Exception Handling

**Location**: `src/ai_lessons/core.py`

**Current Problem** (multiple locations):
```python
except Exception:  # TOO BROAD
    return False
```

**Locations to fix**:

| Function | Lines | Current | New |
|----------|-------|---------|-----|
| `link_lessons()` | 629-631 | `except Exception` | `except sqlite3.IntegrityError` |
| `link_lesson_to_resource()` | 704-706 | `except Exception` | `except sqlite3.IntegrityError` |
| `add_source()` | 941-942 | `except Exception` | `except sqlite3.IntegrityError` |
| `link_to_rule()` | 2171-2173 | `except Exception` | `except sqlite3.IntegrityError` |

**Example Fix**:

```python
# Before:
def link_lessons(...) -> bool:
    with get_db(config) as conn:
        try:
            conn.execute(...)
            conn.commit()
            return True
        except Exception:
            return False

# After:
import sqlite3  # Add to imports if not present

def link_lessons(...) -> bool:
    with get_db(config) as conn:
        try:
            conn.execute(...)
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Link already exists (unique constraint violation)
            return False
```

### 6.2 - Add Type Hints

**Location**: Throughout codebase

**Add to top of files**:
```python
from __future__ import annotations
```

**Key functions missing type hints**:

| File | Function | Missing |
|------|----------|---------|
| core.py | `_store_chunks()` line 1013 | `conn` parameter |
| core.py | `_reimport_resource()` line 1383 | Several parameters |
| search.py | `_row_to_result()` line 439 | `conn` parameter |
| search.py | `_process_resource_row()` line 682 | `conn` parameter |
| db.py | `_run_migrations()` line 180 | `conn` parameter |

**Example**:
```python
# Before:
def _store_chunks(
    conn,  # Missing type
    resource_id: str,
    ...
):

# After:
def _store_chunks(
    conn: sqlite3.Connection,
    resource_id: str,
    ...
):
```

### Chunk 6 Verification

After completing Chunk 6, run:
```bash
python -m pytest tests/ -v
python -m mypy src/ai_lessons/ --ignore-missing-imports  # Optional type check
```

---

## Chunk 7: Missing Features (Rules, Batch Ops)

**Goal**: Add missing CRUD operations and batch functionality.

### 7.1 - Add `update_rule()` Function

**Location**: `src/ai_lessons/core.py` (add after `get_rule()`, around line 2057)

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

### 7.2 - Add `unlink_from_rule()` Function

**Location**: `src/ai_lessons/core.py` (add after `link_to_rule()`, around line 2175)

```python
def unlink_from_rule(
    rule_id: str,
    target_id: str,
    config: Optional[Config] = None,
) -> bool:
    """Remove a link from a rule to a lesson or resource.

    Args:
        rule_id: The rule ID.
        target_id: The lesson or resource ID to unlink.
        config: Configuration to use.

    Returns:
        True if unlinked, False if link didn't exist.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    with get_db(config) as conn:
        cursor = conn.execute(
            "DELETE FROM rule_links WHERE rule_id = ? AND target_id = ?",
            (rule_id, target_id),
        )
        conn.commit()
        return cursor.rowcount > 0
```

### 7.3 - Add Batch Lesson Operation

**Location**: `src/ai_lessons/core.py` (add after `add_lesson()`, around line 276)

```python
def add_lessons_batch(
    lessons: list[dict],
    config: Optional[Config] = None,
) -> list[str]:
    """Add multiple lessons in a single transaction.

    Args:
        lessons: List of lesson dicts, each with keys:
            - title (required)
            - content (required)
            - tags (optional)
            - contexts (optional)
            - anti_contexts (optional)
            - confidence (optional)
            - source (optional)
            - source_notes (optional)
        config: Configuration to use.

    Returns:
        List of generated lesson IDs.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    ids = []

    with get_db(config) as conn:
        for lesson_dict in lessons:
            # Validate required fields
            title = lesson_dict.get("title")
            content = lesson_dict.get("content")
            if not title or not content:
                raise ValueError("Each lesson must have 'title' and 'content'")

            # Optional fields
            tags = lesson_dict.get("tags")
            contexts = lesson_dict.get("contexts")
            anti_contexts = lesson_dict.get("anti_contexts")
            confidence = lesson_dict.get("confidence")
            source = lesson_dict.get("source")
            source_notes = lesson_dict.get("source_notes")

            # Resolve tag aliases
            if tags:
                tags = _resolve_tag_aliases(tags, config)

            # Generate ID
            lesson_id = _generate_id()
            ids.append(lesson_id)

            # Insert lesson
            conn.execute(
                """
                INSERT INTO lessons (id, title, content, confidence, source, source_notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (lesson_id, title, content, confidence, source, source_notes),
            )

            # Save tags
            _save_tags(conn, lesson_id, 'lesson', tags)

            # Insert contexts
            if contexts:
                conn.executemany(
                    "INSERT INTO lesson_contexts (lesson_id, context, applies) VALUES (?, ?, TRUE)",
                    [(lesson_id, ctx) for ctx in contexts],
                )

            # Insert anti-contexts
            if anti_contexts:
                conn.executemany(
                    "INSERT INTO lesson_contexts (lesson_id, context, applies) VALUES (?, ?, FALSE)",
                    [(lesson_id, ctx) for ctx in anti_contexts],
                )

            # Store embedding
            _store_embedding(conn, lesson_id, 'lesson', f"{title}\n\n{content}", config)

        conn.commit()

    return ids
```

### 7.4 - Add CLI Commands for New Features

**Location**: `src/ai_lessons/cli/contribute.py` (after Chunk 5)

Add `update-rule` command:
```python
@contribute.command("update-rule")
@click.argument("rule_id")
@click.option("--title", "-t", help="New title")
@click.option("--content", "-c", help="New content")
@click.option("--rationale", "-r", help="New rationale")
@click.option("--tags", help="New tags (comma-separated, replaces existing)")
def update_rule_cmd(rule_id: str, title: str, content: str, rationale: str, tags: str):
    """Update an existing rule."""
    from ..utils import parse_tags

    updated = core.update_rule(
        rule_id,
        title=title,
        content=content,
        rationale=rationale,
        tags=parse_tags(tags),
    )

    if updated:
        click.echo(f"Updated rule {rule_id}")
    else:
        click.echo(f"Rule not found: {rule_id}", err=True)
        sys.exit(1)
```

### Chunk 7 Verification

After completing Chunk 7, run:
```bash
python -m pytest tests/ -v
ai-lessons contribute update-rule --help
```

---

## Chunk 8: Strict Type Hinting & mypy

**Goal**: Achieve 100% strict type coverage across all modules with zealous mypy enforcement.

### 8.1 - Configure Strict mypy in pyproject.toml

**Location**: `pyproject.toml`

Add the strictest mypy configuration:

```toml
[tool.mypy]
python_version = "3.10"
strict = true
warn_return_any = true
warn_unused_configs = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_no_return = true
warn_unreachable = true
disallow_untyped_defs = true
disallow_untyped_calls = true
disallow_incomplete_defs = true
disallow_untyped_decorators = true
check_untyped_defs = true
no_implicit_optional = true
strict_equality = true
strict_concatenate = true
show_error_codes = true
show_column_numbers = true
pretty = true

# Per-module overrides if needed
[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false
```

### 8.2 - Add `from __future__ import annotations` to All Modules

**Files to update** (add as first import after module docstring):

```python
from __future__ import annotations
```

| File | Status |
|------|--------|
| `src/ai_lessons/__init__.py` | Add |
| `src/ai_lessons/chunking.py` | Add |
| `src/ai_lessons/config.py` | Add |
| `src/ai_lessons/core.py` | Add |
| `src/ai_lessons/db.py` | Add |
| `src/ai_lessons/embeddings.py` | Add |
| `src/ai_lessons/links.py` | Add |
| `src/ai_lessons/schema.py` | Add |
| `src/ai_lessons/search.py` | Add |
| `src/ai_lessons/cli/__init__.py` | Add |
| `src/ai_lessons/cli/admin.py` | Add |
| `src/ai_lessons/cli/contribute.py` | Add |
| `src/ai_lessons/cli/recall.py` | Add |
| `src/ai_lessons/cli/display.py` | Add |
| `src/ai_lessons/cli/utils.py` | Add |

### 8.3 - Type Hint Patterns to Apply

**Pattern 1: Database connections**
```python
# Before:
def _some_function(conn, ...):

# After:
import sqlite3
def _some_function(conn: sqlite3.Connection, ...) -> ReturnType:
```

**Pattern 2: Optional parameters with None default**
```python
# Before:
def func(param=None):

# After:
def func(param: Optional[str] = None) -> ReturnType:
# Or with modern syntax:
def func(param: str | None = None) -> ReturnType:
```

**Pattern 3: List/Dict with specific types**
```python
# Before:
def func(items):
    return {}

# After:
def func(items: list[str]) -> dict[str, int]:
```

**Pattern 4: Callable types**
```python
from typing import Callable

# Before:
def func(callback):

# After:
def func(callback: Callable[[str, int], bool]) -> None:
```

**Pattern 5: TypedDict for complex dicts**
```python
from typing import TypedDict

class FeedbackStats(TypedDict):
    total_feedback: int
    avg_invocations: float
    min_invocations: int
    max_invocations: int
    with_suggestions: int

def get_feedback_stats(...) -> FeedbackStats:
```

### 8.4 - Files Requiring Significant Type Work

**Priority 1: Core modules with many functions**

| File | Key Functions Needing Types |
|------|---------------------------|
| `core.py` | `_store_chunks()`, `_reimport_resource()`, `_store_and_resolve_links()`, `_resolve_dangling_links()` |
| `search.py` | `_row_to_result()`, `_process_resource_row()`, `_process_chunk_row()`, all filter builders |
| `db.py` | `_run_migrations()`, `_ensure_vector_table()` |

**Priority 2: Helper modules**

| File | Key Items |
|------|-----------|
| `links.py` | `ExtractedLink` dataclass, `extract_links()`, `resolve_*` functions |
| `chunking.py` | `Chunk` dataclass, `ChunkingConfig`, `chunk_document()` |
| `embeddings.py` | Backend functions, `embed_text()` |

**Priority 3: CLI modules** (after Chunk 5 split)

All CLI modules should have typed Click commands and helper functions.

### 8.5 - Run mypy and Fix All Errors

**Command**:
```bash
python -m mypy src/ai_lessons/ --strict
```

**Common fixes needed**:

| Error Type | Fix |
|------------|-----|
| `Missing return type` | Add `-> ReturnType` |
| `Missing type annotation` | Add `: Type` to parameter |
| `Incompatible return type` | Fix return statement or annotation |
| `Argument has incompatible type` | Fix caller or callee type |
| `Item "None" has no attribute` | Add None check or use `assert` |
| `Cannot infer type` | Add explicit annotation |

**Example fix for "Item None has no attribute"**:
```python
# Before (mypy error):
def get_lesson(lesson_id: str) -> Lesson:
    row = cursor.fetchone()
    return Lesson(id=row["id"], ...)  # Error: row could be None

# After:
def get_lesson(lesson_id: str) -> Lesson | None:
    row = cursor.fetchone()
    if row is None:
        return None
    return Lesson(id=row["id"], ...)
```

### 8.6 - Add TYPE_CHECKING Imports for Circular Dependencies

**Pattern**:
```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Config
    from .chunking import ChunkingConfig
```

This allows type hints without runtime circular imports.

### 8.7 - Protocol Classes for Duck Typing (if needed)

If mypy complains about duck-typed objects:

```python
from typing import Protocol

class SupportsRead(Protocol):
    def read(self, n: int = -1) -> str: ...

def process_file(f: SupportsRead) -> str:
    return f.read()
```

### Chunk 8 Verification

```bash
# Run mypy with strict settings
python -m mypy src/ai_lessons/ --strict

# Should output: "Success: no issues found"

# Also run tests to ensure types don't break runtime
python -m pytest tests/ -v
```

---

## Chunk 9: Constants, Tests & Documentation

**Goal**: Extract magic numbers, add tests, update documentation.

### 9.1 - Extract Scoring Constants

**Location**: `src/ai_lessons/search.py`

**Create constants section** (add after imports, around line 12):

```python
# =============================================================================
# Scoring Constants
# =============================================================================

# Sigmoid function parameters for distance-to-score conversion
# Formula: 1 / (1 + exp(k * (distance - center)))
SIGMOID_K = 6.0  # Steepness: higher = sharper transition
SIGMOID_CENTER = 1.15  # Distance that maps to 0.5 score

# Keyword boosting parameters
KEYWORD_BOOST_MAX = 0.15  # Maximum additive boost from keyword matches
KEYWORD_BOOST_SCALE = 0.025  # Multiplier for raw keyword score

# Title/tag/content weights for keyword scoring
KEYWORD_WEIGHT_TITLE = 3.0  # Title matches weighted highest
KEYWORD_WEIGHT_TAG = 2.5  # Tag matches weighted high
KEYWORD_WEIGHT_CONTENT = 1.0  # Content matches baseline

# Chunk specificity boost
CHUNK_SPECIFICITY_BOOST = 1.03  # Multiplier for chunk vs resource results

# Link boosting parameters
LINK_BOOST_FACTOR = 0.25  # How much to boost from linked high-scoring resources
LINK_BOOST_MIN_SCORE = 0.65  # Minimum score for linked resource to trigger boost
```

**Update functions to use constants**:

| Function | Line | Current | New |
|----------|------|---------|-----|
| `_distance_to_score()` | ~98 | `k: float = 6.0, center: float = 1.15` | `k: float = SIGMOID_K, center: float = SIGMOID_CENTER` |
| `_keyword_score_with_tags()` | ~140 | `3.0`, `2.5`, `1.0` | Use `KEYWORD_WEIGHT_*` constants |
| `_compute_resource_score()` | ~190 | `0.15`, `0.025`, `1.03` | Use constants |
| `_apply_link_boosting()` | ~972 | `0.25`, `0.65` | Use `LINK_BOOST_*` constants |

### 9.2 - Add Tests for Search

**Location**: `tests/test_search.py` (new file)

```python
"""Tests for search functionality."""

import pytest
from ai_lessons import search
from ai_lessons.search import (
    _distance_to_score,
    _keyword_score_with_tags,
    SIGMOID_K,
    SIGMOID_CENTER,
)


class TestScoring:
    """Tests for scoring functions."""

    def test_distance_to_score_zero_distance(self):
        """Zero distance should give high score."""
        score = _distance_to_score(0.0)
        assert score > 0.99

    def test_distance_to_score_center_distance(self):
        """Distance at center should give ~0.5 score."""
        score = _distance_to_score(SIGMOID_CENTER)
        assert 0.45 < score < 0.55

    def test_distance_to_score_high_distance(self):
        """High distance should give low score."""
        score = _distance_to_score(2.0)
        assert score < 0.1

    def test_keyword_score_title_match(self):
        """Title match should score higher than content match."""
        title_score = _keyword_score_with_tags("python", "python basics", "", [])
        content_score = _keyword_score_with_tags("python", "basics", "python is great", [])
        assert title_score > content_score

    def test_keyword_score_tag_match(self):
        """Tag match should boost score."""
        with_tag = _keyword_score_with_tags("python", "basics", "content", ["python"])
        without_tag = _keyword_score_with_tags("python", "basics", "content", [])
        assert with_tag > without_tag


class TestSearchResultTypes:
    """Tests for SearchResult subclasses."""

    def test_lesson_result_type(self):
        """LessonResult should have result_type='lesson'."""
        result = search.LessonResult(
            id="test",
            title="Test",
            content="Content",
            score=0.9,
            result_type="lesson",
            tags=[],
        )
        assert result.result_type == "lesson"

    def test_chunk_result_type(self):
        """ChunkResult should have result_type='chunk'."""
        result = search.ChunkResult(
            id="test",
            title="Test",
            content="Content",
            score=0.9,
            result_type="chunk",
            tags=[],
        )
        assert result.result_type == "chunk"
```

### 9.3 - Add Tests for Unified Edges

**Location**: `tests/test_edges.py` (new file)

```python
"""Tests for unified edges functionality."""

import pytest
from ai_lessons import core
from ai_lessons.config import Config
from ai_lessons.db import init_db


@pytest.fixture
def test_config(tmp_path):
    """Create a test configuration with temporary database."""
    config = Config(db_path=tmp_path / "test.db")
    init_db(config)
    return config


class TestUnifiedEdges:
    """Tests for unified edge/link system."""

    def test_link_lessons(self, test_config):
        """Test linking two lessons."""
        lesson1 = core.add_lesson("Lesson 1", "Content 1", config=test_config)
        lesson2 = core.add_lesson("Lesson 2", "Content 2", config=test_config)

        result = core.link_lessons(lesson1, lesson2, "related_to", config=test_config)
        assert result is True

        # Duplicate should return False
        result = core.link_lessons(lesson1, lesson2, "related_to", config=test_config)
        assert result is False

    def test_link_lesson_to_resource(self, test_config):
        """Test linking a lesson to a resource."""
        lesson = core.add_lesson("Lesson", "Content", config=test_config)
        resource = core.add_resource("doc", "Resource", content="Doc content", config=test_config)

        result = core.link_lesson_to_resource(lesson, resource, config=test_config)
        assert result is True

        # Verify link exists
        links = core.get_lesson_resource_links(lesson, config=test_config)
        assert len(links) == 1
        assert links[0].resource_id == resource
```

### 9.4 - Update Documentation

**Location**: `docs/implementation/v4-cleanup/CHANGELOG.md` (new file)

```markdown
# v4-cleanup Changelog

## Schema v9

### Breaking Changes
- `edges` table now has `from_type` and `to_type` columns
- `lesson_links` table removed (merged into `edges`)
- `resource_links` renamed to `resource_anchors`

### New Features
- Unified link traversal across all entity types
- `update_rule()` function for editing rules
- `unlink_from_rule()` function
- `add_lessons_batch()` for bulk imports
- Documented scoring constants

### Improvements
- DRY: Extracted tag handling helpers
- DRY: Extracted filter building helpers
- DRY: Extracted embedding storage helpers
- SearchResult inheritance hierarchy
- Specific exception handling
- CLI split into modular package

### Migration
Migration from v8 to v9 is automatic. Existing data in `edges`, `lesson_links`,
and `resource_links` will be migrated to the new unified schema.
```

### Chunk 9 Verification

After completing Chunk 9, run:
```bash
python -m pytest tests/ -v
ai-lessons --version
```

---

## Important Notes for Future Sessions

### Chunk Completion Checklist

After each chunk:
1. Run `python -m pytest tests/ -v`
2. Test CLI commands manually
3. Commit changes with message: `v4-cleanup: Complete chunk N - <description>`
4. Update todo list to mark chunk complete

### Key Files Reference

| Purpose | File |
|---------|------|
| Schema definitions | `src/ai_lessons/schema.py` |
| Migrations | `src/ai_lessons/db.py` → `_run_migrations()` |
| Core CRUD | `src/ai_lessons/core.py` |
| Search logic | `src/ai_lessons/search.py` |
| CLI commands | `src/ai_lessons/cli/` (after Chunk 5) |
| Tests | `tests/` |

### Decisions Made

1. **SearchResult**: Use inheritance, not union types
2. **Contexts**: Case-sensitive (do NOT normalize)
3. **Links**: Unified into `edges`, markdown metadata in `resource_anchors`
4. **CLI**: Split into `cli/` directory

---

**STOP**: Before continuing work after a compactification, DO NOT mark re-reading this document as complete. That todo item is intended to help ensure that this document is re-read across compactifications until this cleanup process is complete.

When the system prompts you to create a summary for the next session, include a **STRONG instruction** to RE-READ THIS DOCUMENT (`docs/implementation/v4-cleanup/PLANNING.md`) before doing anything else.

---

**WORK UNTIL COMPLETE**: Do NOT prompt the user for feedback, questions, or input until ALL chunks have been completed and ALL todo items are marked done. Work autonomously through each chunk in order, running verification tests after each chunk, and only engage the user once the final verification is complete.
