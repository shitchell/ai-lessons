# Resource Linking & Section Hints - Implementation Specification

This document provides complete implementation details for adding resource linking and section hints to ai-lessons. A developer with no prior context should be able to implement this feature using only this specification.

## Overview

This feature adds:
1. **Section hints**: Extract and display headers within each chunk
2. **Resource linking**: Extract markdown links, resolve to other resources/chunks
3. **Re-import handling**: Detect existing resources by path, rebuild cleanly
4. **Admin commands**: `update-paths` for bulk path changes, `related` for exploring links

**Rationale**: Documentation often references other docs. Automatic link extraction creates a navigable graph. Section hints show what's inside a chunk before fetching it. Together, these improve discoverability and navigation.

---

## Schema Changes (v4 → v5)

### New Table: resource_links

```sql
CREATE TABLE resource_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_resource_id TEXT NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    from_chunk_id TEXT REFERENCES resource_chunks(id) ON DELETE CASCADE,
    to_path TEXT NOT NULL,
    to_fragment TEXT,
    link_text TEXT,
    resolved_resource_id TEXT REFERENCES resources(id) ON DELETE SET NULL,
    resolved_chunk_id TEXT REFERENCES resource_chunks(id) ON DELETE SET NULL
);

CREATE INDEX idx_resource_links_to_path ON resource_links(to_path);
CREATE INDEX idx_resource_links_from_resource ON resource_links(from_resource_id);
```

**Column descriptions:**

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Auto-increment primary key |
| `from_resource_id` | TEXT | Resource containing this link |
| `from_chunk_id` | TEXT | Chunk containing this link (nullable for resource-level links) |
| `to_path` | TEXT | Absolute path of linked file |
| `to_fragment` | TEXT | Fragment/anchor without `#` (nullable) |
| `link_text` | TEXT | The display text from `[text](path)` |
| `resolved_resource_id` | TEXT | Matched resource ID if found (nullable) |
| `resolved_chunk_id` | TEXT | Matched chunk ID if fragment resolved (nullable) |

**Rationale**: Storing links separately from content means path updates don't require re-embedding. The `resolved_*` columns cache lookups and enable efficient querying.

### New Column: resource_chunks.sections

```sql
ALTER TABLE resource_chunks ADD COLUMN sections TEXT;
```

**Description**: JSON array of header texts within this chunk (e.g., `["Parameters", "Return type", "Authorization"]`).

**Rationale**: Enables "section hints" in search results without fetching full content.

### Migration (v4 → v5)

In `db.py`, add migration:

```python
def _migrate_v4_to_v5(conn: sqlite3.Connection) -> None:
    """Add resource_links table and sections column."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS resource_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_resource_id TEXT NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
            from_chunk_id TEXT REFERENCES resource_chunks(id) ON DELETE CASCADE,
            to_path TEXT NOT NULL,
            to_fragment TEXT,
            link_text TEXT,
            resolved_resource_id TEXT REFERENCES resources(id) ON DELETE SET NULL,
            resolved_chunk_id TEXT REFERENCES resource_chunks(id) ON DELETE SET NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_resource_links_to_path ON resource_links(to_path)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_resource_links_from_resource ON resource_links(from_resource_id)")

    # Add sections column if not exists
    cursor = conn.execute("PRAGMA table_info(resource_chunks)")
    columns = [row[1] for row in cursor.fetchall()]
    if "sections" not in columns:
        conn.execute("ALTER TABLE resource_chunks ADD COLUMN sections TEXT")

    conn.execute("UPDATE schema_version SET version = 5")
    conn.commit()
```

---

## Section Extraction

### Location: `chunking.py`

Add section extraction to the `ChunkResult` dataclass and chunking functions.

### Updated ChunkResult Dataclass

```python
@dataclass
class ChunkResult:
    index: int
    content: str
    title: Optional[str] = None
    breadcrumb: Optional[str] = None
    start_line: int = 0
    end_line: int = 0
    token_count: int = 0
    warnings: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)  # NEW
```

### Section Extraction Function

```python
import re

def extract_sections(content: str) -> list[str]:
    """Extract header texts from markdown content.

    Args:
        content: Markdown content to scan.

    Returns:
        List of header texts, cleaned of formatting.
    """
    # Match markdown headers (# to ######)
    header_pattern = r'^#{1,6}\s+(.+)$'
    matches = re.findall(header_pattern, content, re.MULTILINE)

    sections = []
    for header in matches:
        # Clean up: remove bold/italic markers, trailing anchors, etc.
        cleaned = header.strip()
        cleaned = re.sub(r'\*\*([^*]+)\*\*', r'\1', cleaned)  # **bold**
        cleaned = re.sub(r'\*([^*]+)\*', r'\1', cleaned)      # *italic*
        cleaned = re.sub(r'`([^`]+)`', r'\1', cleaned)        # `code`
        cleaned = re.sub(r'\s*<a\s+name="[^"]*">\s*</a>\s*', '', cleaned)  # anchors
        cleaned = re.sub(r'\s*\{#[^}]+\}\s*$', '', cleaned)   # {#anchor} suffix
        sections.append(cleaned.strip())

    return sections
```

**Rationale**: Headers within a chunk tell users what information is available. Cleaning removes markdown formatting for cleaner display.

### Integration Point

In `chunk_document()` or the strategy functions, after creating each chunk:

```python
chunk.sections = extract_sections(chunk.content)
```

---

## Link Extraction

### Location: `core.py` (new module `links.py` also acceptable)

### Link Extraction Function

```python
import re
from pathlib import Path
from typing import NamedTuple

class ExtractedLink(NamedTuple):
    link_text: str
    path: str           # Original path from markdown
    fragment: Optional[str]  # Without # prefix
    absolute_path: str  # Resolved absolute path
    line_number: int    # For determining which chunk

def extract_links(content: str, source_path: str) -> list[ExtractedLink]:
    """Extract markdown links from content and resolve to absolute paths.

    Args:
        content: Document content.
        source_path: Absolute path of the source file (for resolving relative links).

    Returns:
        List of extracted links with resolved paths.
    """
    # Pattern: [text](path) or [text](path#fragment)
    # Excludes URLs (http://, https://, etc.)
    pattern = r'\[([^\]]+)\]\((?!https?://|mailto:|#)([^)#\s]+)(#[^)\s]+)?\)'

    source_dir = Path(source_path).parent
    links = []

    for line_num, line in enumerate(content.split('\n'), 1):
        for match in re.finditer(pattern, line):
            link_text = match.group(1)
            path = match.group(2)
            fragment_with_hash = match.group(3)

            # Handle same-file fragments: [text](#section)
            # These are caught by a separate pattern

            # Resolve relative path to absolute
            if path.startswith('/'):
                absolute_path = path
            else:
                absolute_path = str((source_dir / path).resolve())

            # Extract fragment without #
            fragment = None
            if fragment_with_hash:
                fragment = fragment_with_hash[1:]  # Remove leading #

            links.append(ExtractedLink(
                link_text=link_text,
                path=path,
                fragment=fragment,
                absolute_path=absolute_path,
                line_number=line_num,
            ))

    # Also extract same-file fragment links: [text](#section)
    fragment_pattern = r'\[([^\]]+)\]\((#[^)\s]+)\)'
    for line_num, line in enumerate(content.split('\n'), 1):
        for match in re.finditer(fragment_pattern, line):
            link_text = match.group(1)
            fragment = match.group(2)[1:]  # Remove #

            links.append(ExtractedLink(
                link_text=link_text,
                path='',  # Same file
                fragment=fragment,
                absolute_path=source_path,  # Same file
                line_number=line_num,
            ))

    return links
```

**Rationale**: We extract all markdown-style links, resolve relative paths to absolute, and preserve fragment information for chunk-level linking.

### Determine Which Chunk Contains a Link

```python
def find_chunk_for_line(chunks: list[ChunkResult], line_number: int) -> Optional[str]:
    """Find which chunk contains a given line number.

    Args:
        chunks: List of chunks with start_line and end_line.
        line_number: 1-indexed line number.

    Returns:
        Chunk ID if found, None otherwise.
    """
    # Convert to 0-indexed for comparison with chunk.start_line/end_line
    line_idx = line_number - 1

    for chunk in chunks:
        if chunk.start_line <= line_idx <= chunk.end_line:
            return chunk.id

    return None
```

---

## Link Resolution

### Resolve Links to Resources

```python
def resolve_link_to_resource(conn: sqlite3.Connection, to_path: str) -> Optional[str]:
    """Find a resource matching the given path.

    Args:
        conn: Database connection.
        to_path: Absolute path to look up.

    Returns:
        Resource ID if found, None otherwise.
    """
    cursor = conn.execute(
        "SELECT id FROM resources WHERE path = ?",
        (to_path,)
    )
    row = cursor.fetchone()
    return row["id"] if row else None
```

### Resolve Fragment to Chunk

```python
import json

def resolve_fragment_to_chunk(
    conn: sqlite3.Connection,
    resource_id: str,
    fragment: str,
) -> Optional[str]:
    """Find a chunk within a resource that contains the given section.

    Args:
        conn: Database connection.
        resource_id: Parent resource ID.
        fragment: Section name to find (without #).

    Returns:
        Chunk ID if found, None otherwise.
    """
    cursor = conn.execute(
        "SELECT id, sections FROM resource_chunks WHERE resource_id = ?",
        (resource_id,)
    )

    # Normalize fragment for comparison (lowercase, hyphen-to-space)
    fragment_normalized = fragment.lower().replace('-', ' ').replace('_', ' ')

    for row in cursor.fetchall():
        if row["sections"]:
            sections = json.loads(row["sections"])
            for section in sections:
                section_normalized = section.lower().replace('-', ' ').replace('_', ' ')
                if fragment_normalized == section_normalized:
                    return row["id"]

    return None
```

**Rationale**: Fragment normalization handles common variations (kebab-case anchors vs. title case headers).

---

## Updated add_resource Flow

### Two-Phase Approach

```python
def add_resource(
    type: str,
    title: str,
    path: str,
    versions: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
    chunking_config: Optional[ChunkingConfig] = None,
    config: Optional[Config] = None,
) -> str:
    """Add a resource with link extraction and resolution."""

    if config is None:
        config = get_config()

    # Check for existing resource (re-import)
    existing = get_resource_by_path(path)
    if existing:
        return _reimport_resource(existing.id, type, title, path, versions, tags, chunking_config, config)

    # ... [existing resource creation code] ...

    # Phase 1: Chunk and extract sections
    if type == "doc" and chunking_config:
        content = Path(path).read_text()
        chunk_result = chunk_document(content, chunking_config, source_path=path)

        # Store chunks with sections
        for chunk in chunk_result.chunks:
            chunk.sections = extract_sections(chunk.content)
            # ... [existing chunk storage code] ...
            # Store sections as JSON
            conn.execute(
                "UPDATE resource_chunks SET sections = ? WHERE id = ?",
                (json.dumps(chunk.sections), chunk_id)
            )

    # Phase 2: Extract and resolve links
    links = extract_links(content, path)
    _store_and_resolve_links(conn, resource_id, chunks, links, config)

    # Phase 3: Check for dangling links pointing to this resource
    _resolve_dangling_links(conn, path, resource_id, chunks)

    return resource_id
```

### Store and Resolve Links

```python
def _store_and_resolve_links(
    conn: sqlite3.Connection,
    resource_id: str,
    chunks: list,  # List of stored chunks with IDs
    links: list[ExtractedLink],
    config: Config,
) -> None:
    """Store extracted links and attempt resolution."""

    for link in links:
        # Find which chunk this link is in
        from_chunk_id = find_chunk_for_line(chunks, link.line_number)

        # Attempt resolution
        resolved_resource_id = resolve_link_to_resource(conn, link.absolute_path)
        resolved_chunk_id = None

        if resolved_resource_id and link.fragment:
            resolved_chunk_id = resolve_fragment_to_chunk(
                conn, resolved_resource_id, link.fragment
            )

        # Skip self-links (same chunk)
        if from_chunk_id and from_chunk_id == resolved_chunk_id:
            continue

        # Store link
        conn.execute("""
            INSERT INTO resource_links
            (from_resource_id, from_chunk_id, to_path, to_fragment, link_text,
             resolved_resource_id, resolved_chunk_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            resource_id,
            from_chunk_id,
            link.absolute_path,
            link.fragment,
            link.link_text,
            resolved_resource_id,
            resolved_chunk_id,
        ))

        # Create edge if resolved
        if resolved_resource_id:
            _create_link_edge(conn, resource_id, resolved_resource_id)
```

**Rationale**: Self-links (fragment resolving to same chunk) are skipped as they're meaningless in the graph.

### Resolve Dangling Links

```python
def _resolve_dangling_links(
    conn: sqlite3.Connection,
    new_resource_path: str,
    new_resource_id: str,
    new_chunks: list,
) -> None:
    """Find unresolved links pointing to this newly imported resource."""

    cursor = conn.execute("""
        SELECT id, from_resource_id, to_fragment
        FROM resource_links
        WHERE to_path = ? AND resolved_resource_id IS NULL
    """, (new_resource_path,))

    for row in cursor.fetchall():
        resolved_chunk_id = None
        if row["to_fragment"]:
            resolved_chunk_id = resolve_fragment_to_chunk(
                conn, new_resource_id, row["to_fragment"]
            )

        conn.execute("""
            UPDATE resource_links
            SET resolved_resource_id = ?, resolved_chunk_id = ?
            WHERE id = ?
        """, (new_resource_id, resolved_chunk_id, row["id"]))

        # Create edge
        _create_link_edge(conn, row["from_resource_id"], new_resource_id)
```

**Rationale**: When importing Doc B that Doc A already links to, we retroactively resolve A's dangling link.

---

## Re-import Handling

```python
def get_resource_by_path(path: str, config: Optional[Config] = None) -> Optional[Resource]:
    """Find a resource by its filesystem path."""
    if config is None:
        config = get_config()

    with get_db(config) as conn:
        cursor = conn.execute("SELECT * FROM resources WHERE path = ?", (path,))
        row = cursor.fetchone()
        if row:
            return _row_to_resource(conn, row)
    return None


def _reimport_resource(
    existing_id: str,
    type: str,
    title: str,
    path: str,
    versions: Optional[list[str]],
    tags: Optional[list[str]],
    chunking_config: Optional[ChunkingConfig],
    config: Config,
) -> str:
    """Re-import a resource, keeping the same ID but rebuilding chunks/links."""

    with get_db(config) as conn:
        # Delete old chunks (cascades to chunk_embeddings)
        conn.execute("DELETE FROM resource_chunks WHERE resource_id = ?", (existing_id,))

        # Delete old links from this resource
        conn.execute("DELETE FROM resource_links WHERE from_resource_id = ?", (existing_id,))

        # Delete edges from this resource (keep edges TO this resource)
        conn.execute("DELETE FROM edges WHERE from_id = ?", (existing_id,))

        # Update resource metadata
        content = Path(path).read_text()
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        conn.execute("""
            UPDATE resources
            SET type = ?, title = ?, content = ?, content_hash = ?, updated_at = ?
            WHERE id = ?
        """, (type, title, content, content_hash, datetime.utcnow().isoformat(), existing_id))

        # Update versions
        conn.execute("DELETE FROM resource_versions WHERE resource_id = ?", (existing_id,))
        for version in (versions or ["unversioned"]):
            conn.execute(
                "INSERT INTO resource_versions (resource_id, version) VALUES (?, ?)",
                (existing_id, version)
            )

        # Update tags
        conn.execute("DELETE FROM resource_tags WHERE resource_id = ?", (existing_id,))
        for tag in (tags or []):
            conn.execute(
                "INSERT INTO resource_tags (resource_id, tag) VALUES (?, ?)",
                (existing_id, tag)
            )

        conn.commit()

    # Re-chunk and re-extract links (reuse existing logic)
    # ... [same as new resource flow] ...

    return existing_id
```

**Rationale**: We keep the same resource ID so external references remain valid, but rebuild everything else for a clean slate.

---

## CLI Commands

### Enhanced Search Result Display

In `cli.py`, update `_format_search_result()`:

```python
def _format_search_result(result: SearchResult, verbose: bool = False) -> str:
    """Format a search result for display."""
    lines = []

    if result.result_type == "chunk":
        # ... [existing breadcrumb/title logic] ...

        lines.append(f"[chunk] [{result.id}] (score: {result.score:.3f}) {display_title}")

        meta = []
        if result.versions:
            meta.append(f"versions: {', '.join(result.versions)}")
        if result.sections:  # NEW
            sections_str = ", ".join(result.sections[:4])  # Limit display
            if len(result.sections) > 4:
                sections_str += f" (+{len(result.sections) - 4} more)"
            meta.append(f"sections: {sections_str}")
        if meta:
            lines.append(f"  {' | '.join(meta)}")

        # ... [rest of existing logic] ...
```

### Enhanced show-chunk Display

Add linked resources footer:

```python
@recall.command("show-chunk")
@click.argument("chunk_id")
def show_chunk(chunk_id: str):
    """Show a resource chunk by ID."""
    chunk = core.get_chunk(chunk_id)

    if chunk is None:
        click.echo(f"Chunk not found: {chunk_id}", err=True)
        sys.exit(1)

    click.echo(_format_chunk(chunk, verbose=True))

    # Show linked resources
    links = core.get_chunk_links(chunk_id)
    if links:
        click.echo()
        click.echo("---")
        click.echo("Linked resources:")
        for link in links:
            if link.resolved_resource_id:
                resource = core.get_resource(link.resolved_resource_id)
                target = f"[{link.resolved_resource_id[:12]}...] {resource.title}"
            else:
                target = "(not imported)"

            # Show original link syntax
            fragment = f"#{link.to_fragment}" if link.to_fragment else ""
            click.echo(f"  [{link.link_text}](...{fragment}) -> {target}")
```

### New Command: update-paths

```python
@admin.command("update-paths")
@click.option("--from", "from_path", required=True, help="Old path prefix")
@click.option("--to", "to_path", required=True, help="New path prefix")
@click.option("--dry-run", is_flag=True, help="Show what would be updated")
def update_paths(from_path: str, to_path: str, dry_run: bool):
    """Update resource paths after files move.

    Example:
        ai-lessons admin update-paths --from /old/docs --to /new/docs
    """
    config = get_config()
    core.ensure_initialized(config)

    counts = core.update_resource_paths(from_path, to_path, dry_run=dry_run, config=config)

    if dry_run:
        click.echo("Dry run - would update:")
    else:
        click.echo("Updated:")

    click.echo(f"  Resources: {counts['resources']}")
    click.echo(f"  Links: {counts['links']}")

    if counts['newly_resolved'] > 0:
        click.echo(f"  Newly resolved links: {counts['newly_resolved']}")
```

### New Command: related

```python
@recall.command("related")
@click.argument("resource_id")
def show_related(resource_id: str):
    """Show resources related to the given resource via links."""
    resource = core.get_resource(resource_id)

    if resource is None:
        click.echo(f"Resource not found: {resource_id}", err=True)
        sys.exit(1)

    outgoing, incoming = core.get_related_resources(resource_id)

    click.echo(f"Links from \"{resource.title}\":")
    if outgoing:
        for link in outgoing:
            if link.resolved_resource_id:
                target = core.get_resource(link.resolved_resource_id)
                click.echo(f"  -> [{link.resolved_resource_id[:12]}...] {target.title}")
            else:
                click.echo(f"  -> {link.to_path} (not imported)")
    else:
        click.echo("  (none)")

    click.echo()
    click.echo(f"Links to \"{resource.title}\":")
    if incoming:
        for link in incoming:
            source = core.get_resource(link.from_resource_id)
            click.echo(f"  <- [{link.from_resource_id[:12]}...] {source.title}")
    else:
        click.echo("  (none)")
```

---

## Core Functions to Add

### In `core.py`:

```python
def get_chunk_links(chunk_id: str, config: Optional[Config] = None) -> list:
    """Get links from a specific chunk."""
    # Query resource_links where from_chunk_id = chunk_id
    pass

def get_related_resources(resource_id: str, config: Optional[Config] = None) -> tuple[list, list]:
    """Get outgoing and incoming links for a resource.

    Returns:
        Tuple of (outgoing_links, incoming_links)
    """
    pass

def update_resource_paths(
    from_prefix: str,
    to_prefix: str,
    dry_run: bool = False,
    config: Optional[Config] = None,
) -> dict[str, int]:
    """Update paths for resources and links.

    Returns:
        Dict with counts: {'resources': N, 'links': N, 'newly_resolved': N}
    """
    pass
```

---

## SearchResult Updates

### In `search.py`:

Add to dataclass:
```python
@dataclass
class SearchResult:
    # ... existing fields ...
    sections: Optional[list[str]] = None  # NEW: Headers within this chunk
```

Update `_process_chunk_row()`:
```python
def _process_chunk_row(...) -> Optional[SearchResult]:
    # ... existing code ...

    # Parse sections from JSON
    sections = None
    if row["sections"]:
        sections = json.loads(row["sections"])

    return SearchResult(
        # ... existing fields ...
        sections=sections,
    )
```

---

## Testing Checklist

1. **Section extraction**
   - Headers at all levels (H1-H6) are extracted
   - Formatting (bold, code, anchors) is cleaned
   - Empty chunks have empty sections list

2. **Link extraction**
   - Relative paths resolved correctly
   - Absolute paths preserved
   - Fragments extracted and stored
   - Same-file fragments handled (`#section`)
   - URLs (http://) are ignored
   - Non-markdown files still scanned

3. **Link resolution**
   - Links resolve to existing resources
   - Fragments resolve to correct chunks
   - Self-links are skipped
   - Dangling links stored for future resolution

4. **Re-import**
   - Same path detected as re-import
   - Old chunks/links deleted
   - Resource ID preserved
   - New chunks/links created

5. **update-paths**
   - Resource paths updated
   - Link to_paths updated
   - Dangling links re-resolved

6. **Display**
   - Sections shown in search results
   - Linked resources shown in show-chunk
   - related command shows both directions

---

## Implementation Order

1. **Schema migration** (v4 → v5)
2. **Section extraction** in chunking
3. **Link extraction** function
4. **Link resolution** functions
5. **Updated add_resource** with two-phase approach
6. **Re-import detection** and handling
7. **Dangling link resolution** on new imports
8. **CLI updates** (search display, show-chunk footer)
9. **New commands** (update-paths, related)
10. **Tests**
