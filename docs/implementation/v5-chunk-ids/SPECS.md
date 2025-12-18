# v5-chunk-ids: Implementation Specifications

**Created**: 2025-12-17
**Schema Version**: v11 (from current v10)

---

## Overview

This refactoring improves chunk identification and search UX:
1. Chunk IDs become `<resource_id>.<chunk_index>` format
2. All resources (docs AND scripts) always have at least 1 chunk
3. Search results group chunks under their parent resource
4. Unified `show` command works for both resources and chunks

---

## Summary of Changes

| Change | Details |
|--------|---------|
| Chunk IDs | `<resource_id>.<N>` format (actual storage) |
| Minimum chunks | Always create at least 1 chunk for all resources |
| Scripts | Chunked like docs (first-class citizens) |
| Search display | Top matches summary + grouped resources with ranked chunks |
| Unified command | `show <id>` works for both; `.N` suffix = chunk |

---

## Implementation Chunks

| Chunk | Description | Est. Lines | Files |
|-------|-------------|------------|-------|
| 1 | Chunk ID format helpers | ~100 | core.py, new: chunk_ids.py |
| 2 | Schema migration (v11) | ~150 | schema.py, db.py |
| 3 | Always-chunk behavior | ~200 | core.py, chunking.py |
| 4 | Grouped search results | ~300 | search.py |
| 5 | CLI display updates | ~200 | cli/display.py, cli/recall.py |
| 6 | Tests & verification | ~250 | tests/ |

---

## Chunk 1: Chunk ID Format Helpers

**Goal**: Create utilities for generating, parsing, and validating chunk IDs in `<resource_id>.<N>` format.

### 1.1 - Create `src/ai_lessons/chunk_ids.py`

```python
"""Chunk ID utilities.

Chunk IDs follow the format: <resource_id>.<chunk_index>
Example: 01KCPN9VWAZNSKYVHPCWVPXA2C.1

This makes the parent relationship structural and allows easy parsing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedChunkId:
    """Parsed chunk ID components."""
    resource_id: str
    chunk_index: int

    @property
    def chunk_id(self) -> str:
        """Reconstruct the full chunk ID."""
        return f"{self.resource_id}.{self.chunk_index}"


def generate_chunk_id(resource_id: str, chunk_index: int) -> str:
    """Generate a chunk ID from resource ID and index.

    Args:
        resource_id: Parent resource ULID.
        chunk_index: Zero-based chunk index.

    Returns:
        Chunk ID in format "<resource_id>.<chunk_index>".
    """
    return f"{resource_id}.{chunk_index}"


def parse_chunk_id(chunk_id: str) -> Optional[ParsedChunkId]:
    """Parse a chunk ID into components.

    Args:
        chunk_id: Chunk ID to parse (e.g., "01KCPN9V.1").

    Returns:
        ParsedChunkId if valid, None if invalid format.
    """
    if "." not in chunk_id:
        return None

    parts = chunk_id.rsplit(".", 1)
    if len(parts) != 2:
        return None

    resource_id, index_str = parts

    try:
        chunk_index = int(index_str)
    except ValueError:
        return None

    if chunk_index < 0:
        return None

    return ParsedChunkId(resource_id=resource_id, chunk_index=chunk_index)


def is_chunk_id(id_str: str) -> bool:
    """Check if a string is a chunk ID (contains .N suffix).

    Args:
        id_str: ID string to check.

    Returns:
        True if looks like a chunk ID, False otherwise.
    """
    return parse_chunk_id(id_str) is not None


def is_resource_id(id_str: str) -> bool:
    """Check if a string is a resource ID (no .N suffix).

    Args:
        id_str: ID string to check.

    Returns:
        True if looks like a resource ID, False otherwise.
    """
    return "." not in id_str
```

### 1.2 - Update `core.py` Chunk ID Generation

**Location**: `src/ai_lessons/core.py` line 1331

**Current**:
```python
chunk_id = _generate_id()
```

**New**:
```python
from .chunk_ids import generate_chunk_id

# In _store_chunks():
chunk_id = generate_chunk_id(resource_id, chunk.index)
```

### 1.3 - Update `core.py` get_chunk() Lookup

**Location**: `src/ai_lessons/core.py` lines 1985-2009

**Current**: Looks up by `id = ?`

**New**: Parse chunk ID and look up by `resource_id + chunk_index`

```python
from .chunk_ids import parse_chunk_id

def get_chunk(
    chunk_id: str,
    include_parent: bool = True,
    config: Optional[Config] = None,
) -> Optional[ResourceChunk]:
    """Get a chunk by ID.

    Args:
        chunk_id: The chunk ID in format "<resource_id>.<chunk_index>".
        include_parent: Include parent resource metadata.
        config: Configuration to use.
    """
    parsed = parse_chunk_id(chunk_id)
    if parsed is None:
        return None

    # ... rest of function, query by resource_id AND chunk_index
    cursor = conn.execute(
        "SELECT * FROM resource_chunks WHERE resource_id = ? AND chunk_index = ?",
        (parsed.resource_id, parsed.chunk_index),
    )
```

### Chunk 1 Verification

```bash
python -c "from ai_lessons.chunk_ids import *; print(generate_chunk_id('ABC123', 0))"
# Should output: ABC123.0

python -c "from ai_lessons.chunk_ids import *; print(parse_chunk_id('ABC123.5'))"
# Should output: ParsedChunkId(resource_id='ABC123', chunk_index=5)
```

---

## Chunk 2: Schema Migration (v11)

**Goal**: Migrate existing chunk IDs to new format and update indexes.

### 2.1 - Update Schema Version

**Location**: `src/ai_lessons/schema.py` line 5

```python
SCHEMA_VERSION = 11
```

### 2.2 - Add Migration Logic

**Location**: `src/ai_lessons/db.py` in `_run_migrations()`

```python
if current_version < 11:
    # v11: Change chunk IDs from ULIDs to <resource_id>.<chunk_index> format

    # 1. Get all existing chunks
    cursor = conn.execute(
        "SELECT id, resource_id, chunk_index FROM resource_chunks"
    )
    chunks = cursor.fetchall()

    # 2. Build mapping of old ID to new ID
    id_mapping = {}
    for chunk in chunks:
        old_id = chunk["id"]
        new_id = f"{chunk['resource_id']}.{chunk['chunk_index']}"
        id_mapping[old_id] = new_id

    # 3. Update chunk IDs in resource_chunks
    for old_id, new_id in id_mapping.items():
        conn.execute(
            "UPDATE resource_chunks SET id = ? WHERE id = ?",
            (new_id, old_id),
        )

    # 4. Update chunk_embeddings foreign keys
    for old_id, new_id in id_mapping.items():
        conn.execute(
            "UPDATE chunk_embeddings SET chunk_id = ? WHERE chunk_id = ?",
            (new_id, old_id),
        )

    # 5. Update edges table (to_id where to_type='chunk', from_id where from_type='chunk')
    for old_id, new_id in id_mapping.items():
        conn.execute(
            "UPDATE edges SET to_id = ? WHERE to_id = ? AND to_type = 'chunk'",
            (new_id, old_id),
        )
        conn.execute(
            "UPDATE edges SET from_id = ? WHERE from_id = ? AND from_type = 'chunk'",
            (new_id, old_id),
        )

    # 6. Update resource_anchors (from_id where from_type='chunk')
    for old_id, new_id in id_mapping.items():
        conn.execute(
            "UPDATE resource_anchors SET from_id = ? WHERE from_id = ? AND from_type = 'chunk'",
            (new_id, old_id),
        )

    current_version = 11
```

### Chunk 2 Verification

```bash
# Backup database first
cp ~/.ai/lessons/knowledge.db ~/.ai/lessons/knowledge.db.backup

# Run migration
ai-lessons admin stats

# Check chunk IDs have new format
sqlite3 ~/.ai/lessons/knowledge.db "SELECT id FROM resource_chunks LIMIT 5"
# Should show: <resource_id>.<N> format
```

---

## Chunk 3: Always-Chunk Behavior

**Goal**: Ensure ALL resources (docs AND scripts) always have at least 1 chunk.

### 3.1 - Update Chunking for Small Docs

**Location**: `src/ai_lessons/chunking.py` lines 158-160

**Current**:
```python
# Small documents: no chunking needed
if tokens < config.min_chunk_size * 2:
    return "none", f"document too small ({tokens} tokens)"
```

**New**:
```python
# Small documents: create single chunk with full content
if tokens < config.min_chunk_size * 2:
    return "single", f"document small enough for single chunk ({tokens} tokens)"
```

Also need to handle "single" strategy in `chunk_document()`.

### 3.2 - Add Single-Chunk Strategy

**Location**: `src/ai_lessons/chunking.py` in `chunk_document()`

Add handling for `strategy == "single"` that creates one chunk with full content:

```python
if strategy == "single":
    # Create single chunk with entire content
    chunks = [Chunk(
        index=0,
        content=content,
        title=None,  # Will use resource title
        breadcrumb=None,
        start_line=0,
        end_line=content.count('\n'),
        token_count=estimate_tokens(content),
        sections=_extract_headers(content),  # Still extract headers for searchability
    )]
    return ChunkingResult(
        document_path=source_path or "",
        total_tokens=tokens,
        strategy="single",
        strategy_reason=reason,
        chunks=chunks,
    )
```

### 3.3 - Enable Chunking for Scripts

**Location**: `src/ai_lessons/core.py` lines 1671-1674

**Current**:
```python
# Chunk and store chunks for docs
stored_chunks = []
if type == 'doc':
    stored_chunks = _store_chunks(conn, resource_id, content, path, chunking_config, config)
```

**New**:
```python
# Chunk and store chunks for ALL resources (docs and scripts)
stored_chunks = _store_chunks(conn, resource_id, content, path, chunking_config, config)
```

Also update `_reimport_resource()` similarly (lines 1770-1772).

### 3.4 - Script-Specific Chunking Config

For scripts, we might want different chunking behavior (e.g., chunk on function definitions). For now, use the same logic but could be extended later:

```python
# In _store_chunks(), add awareness of resource type if needed
# For v5, scripts just get single-chunk treatment like small docs
```

### Chunk 3 Verification

```bash
# Add a small doc (should get 1 chunk)
ai-lessons contribute add-resource -t doc small.md --content "Small content"

# Add a script (should get 1+ chunks)
ai-lessons contribute add-resource -t script test.py --path /path/to/script.py

# Verify chunks exist
sqlite3 ~/.ai/lessons/knowledge.db "SELECT resource_id, COUNT(*) FROM resource_chunks GROUP BY resource_id"
```

---

## Chunk 4: Grouped Search Results

**Goal**: Restructure search to group chunks under resources and rank by best chunk.

### 4.1 - New Search Result Types

**Location**: `src/ai_lessons/search.py`

Add new result type for grouped results:

```python
@dataclass
class GroupedResourceResult:
    """A resource with its matching chunks."""
    resource_id: str
    resource_title: str
    resource_type: str  # 'doc' or 'script'
    versions: list[str]
    tags: list[str]
    path: Optional[str]
    best_score: float  # Highest chunk score
    chunks: list[ChunkResult]  # All matching chunks, sorted by score

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)
```

### 4.2 - New Search Function

**Location**: `src/ai_lessons/search.py`

Add `search_resources_grouped()`:

```python
def search_resources_grouped(
    query: str,
    limit: int = 10,
    resource_type: Optional[str] = None,
    versions: Optional[list[str]] = None,
    tag_filter: Optional[list[str]] = None,
    config: Optional[Config] = None,
) -> tuple[list[ChunkResult], list[GroupedResourceResult]]:
    """Search resources and return grouped results.

    Returns:
        Tuple of (top_matches, grouped_results):
        - top_matches: Top N chunks across all resources (flat list)
        - grouped_results: Resources with their matching chunks (grouped)

    Note: Resources that match at resource-level but have no specific chunk
    matches are still included (with empty chunks list). This ensures
    resources with strong overall relevance are shown even if no
    particular chunk stood out.
    """
    # 1. Search chunk embeddings
    # 2. Search resource embeddings (for resources without chunk matches)
    # 3. Group chunks by resource_id
    # 4. For each resource:
    #    - Get resource metadata
    #    - Sort chunks by score (if any)
    #    - Calculate best_score (from chunks or resource-level)
    # 5. Sort resource groups by best_score
    # 6. Return top N chunks and grouped results
```

### 4.3 - Modify Existing Search to Use Grouping

Keep `search_resources()` for backwards compatibility but have it call the grouped version internally if needed.

### Chunk 4 Verification

```bash
python -c "
from ai_lessons.search import search_resources_grouped
top, grouped = search_resources_grouped('OAuth2')
print(f'Top matches: {len(top)}')
for g in grouped[:3]:
    print(f'{g.resource_title}: {len(g.chunks)} chunks, best={g.best_score:.2f}')
"
```

---

## Chunk 5: CLI Display Updates

**Goal**: Update CLI to show grouped results and unified `show` command.

### 5.1 - Update Search Display

**Location**: `src/ai_lessons/cli/display.py`

Add function to format grouped results:

```python
def format_grouped_search_results(
    top_matches: list[ChunkResult],
    grouped: list[GroupedResourceResult],
    show_top_n: int = 3,
) -> str:
    """Format grouped search results for display.

    Output format:
    ```
    Top matches: README.md.58 (0.87), AnnouncementBannerApi.md.1 (0.75)

    README.md (v3) [jira, api]
      .58 (0.87) Authorization > OAuth2
      .62 (0.81) basicAuth

    AnnouncementBannerApi.md (v3) [jira, api]
      .1  (0.75) getBanner
      .3  (0.68) setBanner
    ```
    """
```

### 5.2 - Unified `show` Command

**Location**: `src/ai_lessons/cli/recall.py`

Replace separate `show-resource` and `show-chunk` with unified `show`:

```python
@recall.command("show")
@click.argument("id")
@click.option("--verbose", "-v", is_flag=True)
def show(id: str, verbose: bool):
    """Show a resource or chunk by ID.

    IDs with a .N suffix are chunks (e.g., ABC123.5).
    IDs without a suffix are resources (e.g., ABC123).
    """
    from ..chunk_ids import is_chunk_id

    if is_chunk_id(id):
        chunk = core.get_chunk(id)
        if chunk is None:
            click.echo(f"Chunk not found: {id}", err=True)
            sys.exit(1)
        click.echo(format_chunk(chunk, verbose=verbose))
    else:
        resource = core.get_resource(id)
        if resource is None:
            click.echo(f"Resource not found: {id}", err=True)
            sys.exit(1)
        click.echo(format_resource(resource, verbose=verbose))
```

### 5.3 - Keep Backwards Compatibility

Keep `show-resource` and `show-chunk` as aliases:

```python
@recall.command("show-resource")
@click.argument("resource_id")
def show_resource(resource_id: str):
    """Show a resource by ID (alias for 'show')."""
    ctx = click.get_current_context()
    ctx.invoke(show, id=resource_id)

@recall.command("show-chunk")
@click.argument("chunk_id")
def show_chunk(chunk_id: str):
    """Show a chunk by ID (alias for 'show')."""
    ctx = click.get_current_context()
    ctx.invoke(show, id=chunk_id)
```

### Chunk 5 Verification

```bash
# Test unified show
ai-lessons recall show <resource_id>
ai-lessons recall show <resource_id>.0

# Test grouped search
ai-lessons recall search-resources "OAuth2"
```

---

## Chunk 6: Tests & Verification

**Goal**: Add comprehensive tests for new functionality.

### 6.1 - Test Chunk ID Utilities

**Location**: `tests/test_chunk_ids.py` (new file)

```python
"""Tests for chunk ID utilities."""

import pytest
from ai_lessons.chunk_ids import (
    generate_chunk_id,
    parse_chunk_id,
    is_chunk_id,
    is_resource_id,
    ParsedChunkId,
)


class TestChunkIdGeneration:
    def test_generate_basic(self):
        assert generate_chunk_id("ABC123", 0) == "ABC123.0"
        assert generate_chunk_id("ABC123", 5) == "ABC123.5"

    def test_generate_full_ulid(self):
        ulid = "01KCPN9VWAZNSKYVHPCWVPXA2C"
        assert generate_chunk_id(ulid, 0) == f"{ulid}.0"


class TestChunkIdParsing:
    def test_parse_valid(self):
        result = parse_chunk_id("ABC123.5")
        assert result == ParsedChunkId(resource_id="ABC123", chunk_index=5)

    def test_parse_invalid_no_dot(self):
        assert parse_chunk_id("ABC123") is None

    def test_parse_invalid_non_numeric(self):
        assert parse_chunk_id("ABC123.xyz") is None

    def test_parse_negative_index(self):
        assert parse_chunk_id("ABC123.-1") is None


class TestIdTypeChecks:
    def test_is_chunk_id(self):
        assert is_chunk_id("ABC123.0") is True
        assert is_chunk_id("ABC123") is False

    def test_is_resource_id(self):
        assert is_resource_id("ABC123") is True
        assert is_resource_id("ABC123.0") is False
```

### 6.2 - Test Migration

**Location**: `tests/test_migration_v11.py` (new file)

Test that existing chunk IDs are properly migrated.

### 6.3 - Test Always-Chunk Behavior

**Location**: `tests/test_chunking.py` (add tests)

```python
class TestSingleChunk:
    def test_small_doc_gets_one_chunk(self):
        """Small documents should get exactly 1 chunk."""
        content = "Small content"
        result = chunk_document(content, ChunkingConfig())
        assert len(result.chunks) == 1
        assert result.strategy == "single"
```

### 6.4 - Test Grouped Search

**Location**: `tests/test_search.py` (add tests)

```python
class TestGroupedSearch:
    def test_chunks_grouped_by_resource(self, test_config):
        """Chunks should be grouped under their parent resource."""
        # Add resource with multiple chunks
        # Search and verify grouping
```

### Chunk 6 Verification

```bash
python -m pytest tests/ -v
python -m pytest tests/test_chunk_ids.py -v
```

---

## Files Modified Summary

| File | Changes |
|------|---------|
| `src/ai_lessons/chunk_ids.py` | NEW - Chunk ID utilities |
| `src/ai_lessons/schema.py` | SCHEMA_VERSION = 11 |
| `src/ai_lessons/db.py` | v11 migration |
| `src/ai_lessons/core.py` | Chunk ID generation, get_chunk lookup, always-chunk |
| `src/ai_lessons/chunking.py` | Single-chunk strategy |
| `src/ai_lessons/search.py` | Grouped search results |
| `src/ai_lessons/cli/display.py` | Grouped result formatting |
| `src/ai_lessons/cli/recall.py` | Unified show command |
| `tests/test_chunk_ids.py` | NEW - Chunk ID tests |
| `tests/test_chunking.py` | Single-chunk tests |
| `tests/test_search.py` | Grouped search tests |

---

## Migration Notes

- Schema v11 migration updates existing chunk IDs
- Backup database before migration: `cp ~/.ai/lessons/knowledge.db ~/.ai/lessons/knowledge.db.backup`
- Migration is automatic on first run after update

---

**STOP**: Before continuing work after a compactification, DO NOT mark re-reading this document as complete. That todo item is intended to help ensure that this document is re-read across compactifications until this cleanup process is complete.

When the system prompts you to create a summary for the next session, include a **STRONG instruction** to RE-READ THIS DOCUMENT (`docs/implementation/v5-chunk-ids/SPECS.md`) before doing anything else.

---

**WORK UNTIL COMPLETE**: Do NOT prompt the user for feedback, questions, or input until ALL chunks have been completed and ALL todo items are marked done. Work autonomously through each chunk in order, running verification tests after each chunk, and only engage the user once the final verification is complete.
