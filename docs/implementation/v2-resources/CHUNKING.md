# Chunking Implementation Plan

Technical specification for document chunking in ai-lessons. This document is designed to be self-contained—a fresh implementer should be able to build the feature from this spec alone.

## Table of Contents

1. [Overview](#overview)
2. [Design Decisions](#design-decisions)
3. [Architecture](#architecture)
4. [Data Structures](#data-structures)
5. [Chunking Strategies](#chunking-strategies)
6. [Algorithm Details](#algorithm-details)
7. [CLI Interface](#cli-interface)
8. [MCP Interface](#mcp-interface)
9. [Integration Points](#integration-points)
10. [Testing Plan](#testing-plan)
11. [Implementation Order](#implementation-order)

---

## Overview

### What We're Building

A chunking system that splits large documents into smaller, semantically meaningful pieces for embedding and retrieval. The system should:

1. **Auto-detect** the best chunking strategy based on document structure
2. **Split intelligently** at natural boundaries (headers, paragraphs, sentences)
3. **Preview** chunking results before committing (`--preview` flag)
4. **Store chunks** with parent relationships and breadcrumb context
5. **Search chunks** individually but display with parent context

### Why Chunking Matters

- Large documents embed poorly (signal gets diluted)
- Optimal chunk size for retrieval: 250-800 tokens
- Structure-aware chunking outperforms fixed-size by ~70% in retrieval accuracy
- Self-contained chunks with context enable better search results

### Scope

**In scope:**
- Header-based chunking (markdown `##`, `###`, etc.)
- Delimiter-based chunking (custom patterns)
- Fixed-size chunking with overlap (fallback)
- Auto-detection of best strategy
- Preview mode
- Breadcrumb/hierarchy preservation

**Out of scope (future):**
- Semantic chunking (embedding-based boundary detection)
- Code-aware chunking (AST-based)
- PDF text extraction (require pre-conversion)

---

## Design Decisions

These decisions were made through discussion and should be preserved:

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Token counting | Approximation (chars/4) | No dependencies, good enough for chunking |
| Overlap handling | Complete sentence/paragraph | Better UX than mid-sentence cuts |
| Code in docs | Split on newlines | AST parsing too complex for v1 |
| PDF support | Require pre-conversion | We're not a document converter |
| Breadcrumbs | Full trail always | Minimal overhead, valuable context |
| Min chunk size | ~100 tokens | Below this, merge with adjacent |
| Max chunk size | ~800 tokens | Above this, sub-chunk |
| Default strategy | Auto-detect | Headers → delimiters → fixed-size |

---

## Architecture

### File Locations

```
src/ai_lessons/
├── chunking.py          # NEW: All chunking logic
├── core.py              # Update: add_resource() calls chunking
├── cli.py               # Update: --preview flag, chunking options
├── mcp_server.py        # Update: chunking options in add_resource tool
├── schema.py            # EXISTS: resource_chunks table already defined
└── search.py            # Update: search chunks, return with parent context
```

### Module Responsibilities

**`chunking.py`** (new file):
- `ChunkingConfig` dataclass
- `Chunk` dataclass
- `chunk_document()` main entry point
- Strategy implementations: `chunk_by_headers()`, `chunk_by_delimiter()`, `chunk_fixed_size()`
- Auto-detection: `detect_strategy()`
- Utilities: `estimate_tokens()`, `find_sentence_boundary()`, `extract_breadcrumb()`

**`core.py`** changes:
- `add_resource()` gains `chunking_config` parameter
- New function: `_store_chunks()` to insert chunks and embeddings
- `get_resource()` optionally includes chunks

**`cli.py`** changes:
- `add-resource` command gains chunking options and `--preview` flag
- Preview mode: call chunking, display results, exit without storing

**`search.py`** changes:
- `search_resources()` also searches `chunk_embeddings`
- Results include chunk context (breadcrumb, parent title)

---

## Data Structures

### ChunkingConfig

```python
@dataclass
class ChunkingConfig:
    """Configuration for document chunking."""

    # Strategy selection
    strategy: str = "auto"  # "auto", "headers", "delimiter", "fixed", "none"

    # Size constraints (in tokens, estimated as chars/4)
    min_chunk_size: int = 100
    max_chunk_size: int = 800

    # Header-based options
    header_split_levels: list[int] = field(default_factory=lambda: [2, 3])  # h2, h3
    include_parent_context: bool = True  # Prepend breadcrumb to chunk

    # Delimiter-based options
    delimiter_pattern: str | None = None  # Regex pattern
    include_delimiter: bool = False

    # Fixed-size options
    fixed_chunk_size: int = 500
    fixed_overlap: int = 50

    # Behavior
    complete_sentences: bool = True  # Don't cut mid-sentence
    continuation_marker: str = "[continued...]"  # Added when chunk continues
```

### Chunk

```python
@dataclass
class Chunk:
    """A chunk of a document."""

    # Identity
    index: int  # Order within document (0-based)

    # Content
    content: str
    title: str | None  # Section title if from header split
    breadcrumb: str | None  # "Parent > Child > Grandchild"

    # Boundaries
    start_line: int
    end_line: int

    # Metrics
    token_count: int  # Estimated

    # Flags
    is_continuation: bool = False  # Part of an oversized section
    continuation_of: int | None = None  # Index of chunk this continues

    # Warnings
    warnings: list[str] = field(default_factory=list)  # "oversized", "undersized"
```

### ChunkingResult

```python
@dataclass
class ChunkingResult:
    """Result of chunking a document."""

    # Input info
    document_path: str
    total_tokens: int

    # Strategy used
    strategy: str
    strategy_reason: str  # Why this strategy was chosen

    # Output
    chunks: list[Chunk]

    # Summary
    warnings: list[str]

    def summary(self) -> dict:
        """Return summary statistics."""
        return {
            "total_chunks": len(self.chunks),
            "avg_tokens": sum(c.token_count for c in self.chunks) // len(self.chunks),
            "min_tokens": min(c.token_count for c in self.chunks),
            "max_tokens": max(c.token_count for c in self.chunks),
            "oversized": sum(1 for c in self.chunks if "oversized" in c.warnings),
            "undersized": sum(1 for c in self.chunks if "undersized" in c.warnings),
        }
```

### Database Schema (already exists in schema.py)

```sql
-- Already defined, but repeated here for reference
CREATE TABLE resource_chunks (
    id TEXT PRIMARY KEY,           -- ULID
    resource_id TEXT NOT NULL,     -- Parent resource
    chunk_index INTEGER NOT NULL,  -- Order within document
    title TEXT,                    -- Section title if applicable
    content TEXT NOT NULL,
    FOREIGN KEY (resource_id) REFERENCES resources(id) ON DELETE CASCADE
);

CREATE VIRTUAL TABLE chunk_embeddings USING vec0(
    chunk_id TEXT PRIMARY KEY,
    embedding FLOAT[{dimensions}]
);
```

**Schema additions needed:**

```sql
-- Add to resource_chunks (migration required)
ALTER TABLE resource_chunks ADD COLUMN breadcrumb TEXT;
ALTER TABLE resource_chunks ADD COLUMN start_line INTEGER;
ALTER TABLE resource_chunks ADD COLUMN end_line INTEGER;
ALTER TABLE resource_chunks ADD COLUMN token_count INTEGER;
```

---

## Chunking Strategies

### Strategy: `auto` (default)

Auto-detection logic:

```python
def detect_strategy(content: str, config: ChunkingConfig) -> str:
    """Detect the best chunking strategy for content."""

    tokens = estimate_tokens(content)

    # Small documents: no chunking needed
    if tokens < config.min_chunk_size * 2:
        return "none"

    # Check for markdown headers
    header_pattern = r'^#{1,6}\s+.+$'
    headers = re.findall(header_pattern, content, re.MULTILINE)
    if len(headers) >= 3:  # Enough structure to chunk on
        return "headers"

    # Check for common delimiters
    delimiter_patterns = [
        r'^---+$',           # Horizontal rules
        r'^===+$',           # Alternative HR
        r'^<a\s+name=',      # HTML anchors (common in generated docs)
        r'^\*\*\*+$',        # Asterisk HR
    ]
    for pattern in delimiter_patterns:
        if len(re.findall(pattern, content, re.MULTILINE)) >= 3:
            return "delimiter"

    # Fallback to fixed-size
    return "fixed"
```

### Strategy: `headers`

Split on markdown headers at specified levels.

**Input:**
```markdown
# Top Level (h1)

Intro paragraph.

## Section One (h2)

Content for section one.

### Subsection (h3)

More detailed content.

## Section Two (h2)

Content for section two.
```

**Output (split on h2):**
- Chunk 0: "# Top Level\n\nIntro paragraph." (breadcrumb: "Top Level")
- Chunk 1: "## Section One\n\nContent..." (breadcrumb: "Top Level > Section One")
- Chunk 2: "## Section Two\n\nContent..." (breadcrumb: "Top Level > Section Two")

Note: h3 subsections stay with their parent h2.

**Configurable:**
- Which header levels trigger splits (`header_split_levels`)
- Whether to include breadcrumb in chunk content (`include_parent_context`)

### Strategy: `delimiter`

Split on a regex pattern.

**Example patterns:**
- `^---+$` - Horizontal rules
- `^## ` - Any h2 header (simpler than full header parsing)
- `\n\n\n` - Triple newlines
- `^<a name=` - HTML anchors

**Configurable:**
- Pattern (`delimiter_pattern`)
- Whether delimiter is included in chunk (`include_delimiter`)

### Strategy: `fixed`

Split every N tokens with M token overlap.

**Behavior:**
1. Split at `fixed_chunk_size` tokens
2. Include `fixed_overlap` tokens from previous chunk at start
3. If `complete_sentences` is true, extend to sentence boundary

**Example:**
- Document: 1500 tokens
- Chunk size: 500, Overlap: 50
- Result: 4 chunks
  - Chunk 0: tokens 0-500
  - Chunk 1: tokens 450-950 (50 overlap)
  - Chunk 2: tokens 900-1400
  - Chunk 3: tokens 1350-1500

### Strategy: `none`

Don't chunk. Store document as single unit.

Used when:
- Document is small (< 2 * min_chunk_size)
- User explicitly requests no chunking

---

## Algorithm Details

### Main Entry Point

```python
def chunk_document(
    content: str,
    config: ChunkingConfig | None = None,
    source_path: str | None = None,
) -> ChunkingResult:
    """
    Chunk a document according to configuration.

    Args:
        content: Document content (string)
        config: Chunking configuration (defaults applied if None)
        source_path: Original file path (for reporting)

    Returns:
        ChunkingResult with chunks and metadata
    """
    if config is None:
        config = ChunkingConfig()

    # Auto-detect strategy if needed
    strategy = config.strategy
    strategy_reason = "user specified"

    if strategy == "auto":
        strategy = detect_strategy(content, config)
        strategy_reason = f"auto-detected ({_detection_reason(content, strategy)})"

    # Dispatch to strategy implementation
    if strategy == "none":
        chunks = [_whole_document_chunk(content)]
    elif strategy == "headers":
        chunks = chunk_by_headers(content, config)
    elif strategy == "delimiter":
        chunks = chunk_by_delimiter(content, config)
    elif strategy == "fixed":
        chunks = chunk_fixed_size(content, config)
    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    # Post-process: handle oversized chunks
    chunks = _handle_oversized(chunks, config)

    # Post-process: merge undersized chunks
    chunks = _handle_undersized(chunks, config)

    # Add warnings
    for chunk in chunks:
        if chunk.token_count > config.max_chunk_size:
            chunk.warnings.append("oversized")
        if chunk.token_count < config.min_chunk_size:
            chunk.warnings.append("undersized")

    return ChunkingResult(
        document_path=source_path or "<string>",
        total_tokens=estimate_tokens(content),
        strategy=strategy,
        strategy_reason=strategy_reason,
        chunks=chunks,
        warnings=_collect_warnings(chunks),
    )
```

### Header-Based Chunking

```python
def chunk_by_headers(content: str, config: ChunkingConfig) -> list[Chunk]:
    """Split document on markdown headers."""

    lines = content.split('\n')
    chunks = []

    # Build header hierarchy for breadcrumbs
    header_stack = []  # [(level, title), ...]

    current_chunk_lines = []
    current_chunk_start = 0
    current_title = None
    current_breadcrumb = None

    for i, line in enumerate(lines):
        header_match = re.match(r'^(#{1,6})\s+(.+)$', line)

        if header_match:
            level = len(header_match.group(1))
            title = header_match.group(2).strip()

            # Check if this header level triggers a split
            if level in config.header_split_levels:
                # Save current chunk if it has content
                if current_chunk_lines:
                    chunks.append(Chunk(
                        index=len(chunks),
                        content='\n'.join(current_chunk_lines),
                        title=current_title,
                        breadcrumb=current_breadcrumb,
                        start_line=current_chunk_start,
                        end_line=i - 1,
                        token_count=estimate_tokens('\n'.join(current_chunk_lines)),
                    ))

                # Start new chunk
                current_chunk_lines = [line]
                current_chunk_start = i
                current_title = title

                # Update breadcrumb
                # Pop headers at same or lower level
                while header_stack and header_stack[-1][0] >= level:
                    header_stack.pop()
                header_stack.append((level, title))
                current_breadcrumb = ' > '.join(h[1] for h in header_stack)
            else:
                # Header doesn't trigger split, include in current chunk
                current_chunk_lines.append(line)

                # Still update header stack for breadcrumb tracking
                while header_stack and header_stack[-1][0] >= level:
                    header_stack.pop()
                header_stack.append((level, title))
        else:
            current_chunk_lines.append(line)

    # Don't forget the last chunk
    if current_chunk_lines:
        chunks.append(Chunk(
            index=len(chunks),
            content='\n'.join(current_chunk_lines),
            title=current_title,
            breadcrumb=current_breadcrumb,
            start_line=current_chunk_start,
            end_line=len(lines) - 1,
            token_count=estimate_tokens('\n'.join(current_chunk_lines)),
        ))

    return chunks
```

### Fixed-Size Chunking

```python
def chunk_fixed_size(content: str, config: ChunkingConfig) -> list[Chunk]:
    """Split document into fixed-size chunks with overlap."""

    lines = content.split('\n')
    chunks = []

    # Convert token sizes to approximate line counts
    # (rough estimate: ~20 tokens per line for prose)
    chars_per_chunk = config.fixed_chunk_size * 4
    chars_overlap = config.fixed_overlap * 4

    current_chars = 0
    current_lines = []
    current_start = 0
    overlap_lines = []

    for i, line in enumerate(lines):
        line_chars = len(line) + 1  # +1 for newline

        if current_chars + line_chars > chars_per_chunk and current_lines:
            # Find sentence boundary if configured
            if config.complete_sentences:
                current_lines, remainder = _split_at_sentence(current_lines)
            else:
                remainder = []

            # Create chunk
            chunk_content = '\n'.join(overlap_lines + current_lines)
            chunks.append(Chunk(
                index=len(chunks),
                content=chunk_content,
                title=None,
                breadcrumb=None,
                start_line=current_start,
                end_line=i - 1,
                token_count=estimate_tokens(chunk_content),
                is_continuation=len(chunks) > 0,
                continuation_of=len(chunks) - 1 if len(chunks) > 0 else None,
            ))

            # Calculate overlap for next chunk
            overlap_chars = 0
            overlap_lines = []
            for line in reversed(current_lines):
                if overlap_chars + len(line) > chars_overlap:
                    break
                overlap_lines.insert(0, line)
                overlap_chars += len(line)

            # Start new chunk
            current_lines = remainder + [line]
            current_chars = sum(len(l) for l in current_lines)
            current_start = i - len(remainder)
        else:
            current_lines.append(line)
            current_chars += line_chars

    # Last chunk
    if current_lines:
        chunk_content = '\n'.join(overlap_lines + current_lines)
        chunks.append(Chunk(
            index=len(chunks),
            content=chunk_content,
            title=None,
            breadcrumb=None,
            start_line=current_start,
            end_line=len(lines) - 1,
            token_count=estimate_tokens(chunk_content),
            is_continuation=len(chunks) > 0,
        ))

    return chunks
```

### Utility Functions

```python
def estimate_tokens(text: str) -> int:
    """Estimate token count. Approximation: chars / 4."""
    return len(text) // 4


def find_sentence_boundary(text: str, near_position: int) -> int:
    """Find nearest sentence boundary to a position."""
    # Look for sentence-ending punctuation followed by space or newline
    sentence_enders = re.compile(r'[.!?]\s')

    # Search backwards from position
    for i in range(near_position, max(0, near_position - 200), -1):
        if sentence_enders.match(text[i:i+2]):
            return i + 1

    # Search forwards
    for i in range(near_position, min(len(text), near_position + 200)):
        if sentence_enders.match(text[i:i+2]):
            return i + 1

    # No sentence boundary found, return original position
    return near_position


def _split_at_sentence(lines: list[str]) -> tuple[list[str], list[str]]:
    """Split lines at the last sentence boundary."""
    text = '\n'.join(lines)

    # Find last sentence boundary
    sentence_enders = list(re.finditer(r'[.!?]\s', text))

    if not sentence_enders:
        return lines, []

    last_boundary = sentence_enders[-1].end()

    # Convert back to lines
    before = text[:last_boundary]
    after = text[last_boundary:]

    return before.split('\n'), after.split('\n') if after.strip() else []


def _handle_oversized(chunks: list[Chunk], config: ChunkingConfig) -> list[Chunk]:
    """Sub-chunk any chunks that exceed max_chunk_size."""
    result = []

    for chunk in chunks:
        if chunk.token_count <= config.max_chunk_size:
            result.append(chunk)
        else:
            # Recursively chunk with fixed-size strategy
            sub_config = ChunkingConfig(
                strategy="fixed",
                fixed_chunk_size=config.max_chunk_size - 50,  # Leave room
                fixed_overlap=config.fixed_overlap,
                complete_sentences=config.complete_sentences,
            )
            sub_chunks = chunk_fixed_size(chunk.content, sub_config)

            # Preserve parent breadcrumb
            for i, sub in enumerate(sub_chunks):
                sub.breadcrumb = chunk.breadcrumb
                sub.title = f"{chunk.title} (part {i + 1})" if chunk.title else None
                sub.is_continuation = i > 0
                result.append(sub)

    # Re-index
    for i, chunk in enumerate(result):
        chunk.index = i

    return result


def _handle_undersized(chunks: list[Chunk], config: ChunkingConfig) -> list[Chunk]:
    """Merge undersized chunks with adjacent chunks."""
    if len(chunks) <= 1:
        return chunks

    result = []
    i = 0

    while i < len(chunks):
        chunk = chunks[i]

        # If undersized and there's a next chunk, merge
        if chunk.token_count < config.min_chunk_size and i + 1 < len(chunks):
            next_chunk = chunks[i + 1]
            merged = Chunk(
                index=len(result),
                content=chunk.content + '\n\n' + next_chunk.content,
                title=chunk.title or next_chunk.title,
                breadcrumb=chunk.breadcrumb or next_chunk.breadcrumb,
                start_line=chunk.start_line,
                end_line=next_chunk.end_line,
                token_count=chunk.token_count + next_chunk.token_count,
            )
            result.append(merged)
            i += 2
        else:
            chunk.index = len(result)
            result.append(chunk)
            i += 1

    return result
```

---

## CLI Interface

### Updated `add-resource` Command

```python
@contribute.command("add-resource")
@click.option("--type", "-t", "resource_type", required=True,
              type=click.Choice(["doc", "script"]), help="Resource type")
@click.option("--path", "-p", required=True, help="Filesystem path")
@click.option("--title", required=True, help="Resource title")
@click.option("--version", "versions", multiple=True, help="Version(s)")
@click.option("--tags", help="Comma-separated tags")
# Chunking options
@click.option("--chunk-strategy",
              type=click.Choice(["auto", "headers", "delimiter", "fixed", "none"]),
              default="auto", help="Chunking strategy")
@click.option("--chunk-min-size", default=100, help="Min chunk size (tokens)")
@click.option("--chunk-max-size", default=800, help="Max chunk size (tokens)")
@click.option("--chunk-header-levels", default="2,3",
              help="Header levels to split on (comma-separated)")
@click.option("--chunk-delimiter", help="Custom delimiter pattern (regex)")
@click.option("--preview", is_flag=True, help="Preview chunking without storing")
def add_resource(
    resource_type, path, title, versions, tags,
    chunk_strategy, chunk_min_size, chunk_max_size,
    chunk_header_levels, chunk_delimiter, preview
):
    """Add a doc or script resource."""
    from pathlib import Path
    from .chunking import ChunkingConfig, chunk_document

    path_obj = Path(path)
    if not path_obj.exists():
        click.echo(f"Error: Path does not exist: {path}", err=True)
        sys.exit(1)

    content = path_obj.read_text()

    # Build chunking config
    header_levels = [int(x) for x in chunk_header_levels.split(",")]
    chunking_config = ChunkingConfig(
        strategy=chunk_strategy,
        min_chunk_size=chunk_min_size,
        max_chunk_size=chunk_max_size,
        header_split_levels=header_levels,
        delimiter_pattern=chunk_delimiter,
    )

    # Always run chunking to get preview
    result = chunk_document(content, chunking_config, source_path=path)

    if preview:
        _display_chunking_preview(result)
        return

    # Actual storage
    resource_id = core.add_resource(
        type=resource_type,
        title=title,
        path=path,
        versions=list(versions) if versions else None,
        tags=_parse_tags(tags),
        chunking_config=chunking_config,
    )

    click.echo(f"Added {resource_type}: {resource_id}")
    click.echo(f"  Chunks: {len(result.chunks)}")
    if result.warnings:
        for warning in result.warnings:
            click.echo(f"  ⚠️  {warning}")
```

### Preview Display Function

```python
def _display_chunking_preview(result: ChunkingResult):
    """Display chunking preview in a nice format."""

    click.echo(f"Document: {result.document_path}")
    click.echo(f"Total tokens: {result.total_tokens:,}")
    click.echo(f"Strategy: {result.strategy} ({result.strategy_reason})")
    click.echo()

    # Table header
    click.echo("Chunks:")
    click.echo()
    click.echo("  #   Tokens  Title")
    click.echo("  " + "─" * 60)

    for chunk in result.chunks:
        title = chunk.breadcrumb or chunk.title or f"(lines {chunk.start_line}-{chunk.end_line})"
        if len(title) > 45:
            title = title[:42] + "..."

        warning = ""
        if "oversized" in chunk.warnings:
            warning = " ⚠️ oversized"
        elif "undersized" in chunk.warnings:
            warning = " ⚠️ undersized"

        click.echo(f"  {chunk.index:3d}  {chunk.token_count:6d}  {title}{warning}")

    # Summary
    summary = result.summary()
    click.echo()
    click.echo("Summary:")
    click.echo(f"  Total chunks: {summary['total_chunks']}")
    click.echo(f"  Avg size: {summary['avg_tokens']} tokens")
    click.echo(f"  Range: {summary['min_tokens']} - {summary['max_tokens']} tokens")

    if summary['oversized']:
        click.echo(f"  ⚠️  {summary['oversized']} oversized chunk(s)")
    if summary['undersized']:
        click.echo(f"  ⚠️  {summary['undersized']} undersized chunk(s)")
```

---

## MCP Interface

### Updated `add_resource` Tool

```python
Tool(
    name="add_resource",
    description="Add a doc or script resource with optional chunking configuration.",
    inputSchema={
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["doc", "script"]},
            "path": {"type": "string", "description": "Filesystem path"},
            "title": {"type": "string"},
            "versions": {"type": "array", "items": {"type": "string"}},
            "tags": {"type": "array", "items": {"type": "string"}},
            "chunking": {
                "type": "object",
                "description": "Chunking configuration",
                "properties": {
                    "strategy": {
                        "type": "string",
                        "enum": ["auto", "headers", "delimiter", "fixed", "none"],
                        "default": "auto"
                    },
                    "min_size": {"type": "integer", "default": 100},
                    "max_size": {"type": "integer", "default": 800},
                    "header_levels": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "default": [2, 3]
                    },
                    "delimiter_pattern": {"type": "string"},
                },
            },
            "preview": {
                "type": "boolean",
                "description": "If true, return chunking preview without storing",
                "default": False
            },
        },
        "required": ["type", "path", "title"],
    },
),
```

---

## Integration Points

### `core.py` - Storage

```python
def add_resource(
    type: str,
    title: str,
    path: str | None = None,
    content: str | None = None,
    versions: list[str] | None = None,
    tags: list[str] | None = None,
    chunking_config: ChunkingConfig | None = None,
    config: Config | None = None,
) -> str:
    """Add a resource, optionally with chunking."""
    # ... existing resource creation code ...

    # Chunk if needed
    if chunking_config and chunking_config.strategy != "none":
        from .chunking import chunk_document

        doc_content = content or Path(path).read_text()
        result = chunk_document(doc_content, chunking_config, source_path=path)

        # Store chunks
        _store_chunks(conn, resource_id, result.chunks, config)

    return resource_id


def _store_chunks(
    conn,
    resource_id: str,
    chunks: list[Chunk],
    config: Config
) -> None:
    """Store chunks and their embeddings."""
    from .embedding import get_embedding

    for chunk in chunks:
        chunk_id = generate_ulid()

        # Store chunk
        conn.execute("""
            INSERT INTO resource_chunks
            (id, resource_id, chunk_index, title, content, breadcrumb, start_line, end_line, token_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            chunk_id, resource_id, chunk.index, chunk.title, chunk.content,
            chunk.breadcrumb, chunk.start_line, chunk.end_line, chunk.token_count
        ))

        # Generate and store embedding
        # Use breadcrumb + content for embedding if available
        embed_text = chunk.content
        if chunk.breadcrumb:
            embed_text = f"{chunk.breadcrumb}\n\n{chunk.content}"

        embedding = get_embedding(embed_text, config)
        conn.execute(
            "INSERT INTO chunk_embeddings (chunk_id, embedding) VALUES (?, ?)",
            (chunk_id, embedding)
        )
```

### `search.py` - Retrieval

```python
def search_resources(
    query: str,
    # ... existing params ...
    include_chunks: bool = True,  # NEW: search chunks too
    config: Config | None = None,
) -> list[SearchResult]:
    """Search resources and optionally their chunks."""

    # ... existing resource search code ...

    if include_chunks:
        # Also search chunk embeddings
        chunk_results = _search_chunks(query_embedding, limit * 2, config)

        # Merge results, deduplicating by resource_id
        # Chunks boost their parent resource's score
        results = _merge_resource_and_chunk_results(resource_results, chunk_results)

    return results


def _search_chunks(
    query_embedding: list[float],
    limit: int,
    config: Config,
) -> list[dict]:
    """Search chunk embeddings."""
    with get_db(config) as conn:
        # Vector similarity search on chunks
        results = conn.execute("""
            SELECT
                c.id as chunk_id,
                c.resource_id,
                c.title as chunk_title,
                c.breadcrumb,
                c.content as chunk_content,
                r.title as resource_title,
                r.type as resource_type,
                vec_distance_cosine(ce.embedding, ?) as distance
            FROM chunk_embeddings ce
            JOIN resource_chunks c ON ce.chunk_id = c.id
            JOIN resources r ON c.resource_id = r.id
            ORDER BY distance ASC
            LIMIT ?
        """, (query_embedding, limit))

        return [dict(row) for row in results.fetchall()]
```

---

## Testing Plan

### Unit Tests (`tests/test_chunking.py`)

```python
class TestTokenEstimation:
    def test_estimate_tokens_basic(self):
        assert estimate_tokens("hello world") == 2  # 11 chars / 4

    def test_estimate_tokens_empty(self):
        assert estimate_tokens("") == 0


class TestStrategyDetection:
    def test_detect_small_document(self):
        content = "Short doc"
        assert detect_strategy(content, ChunkingConfig()) == "none"

    def test_detect_markdown_headers(self):
        content = "# Title\n\n## Section 1\n\nContent\n\n## Section 2\n\nMore"
        assert detect_strategy(content, ChunkingConfig()) == "headers"

    def test_detect_delimiter(self):
        content = "Part 1\n\n---\n\nPart 2\n\n---\n\nPart 3\n\n---\n\nPart 4"
        assert detect_strategy(content, ChunkingConfig()) == "delimiter"

    def test_detect_fallback_to_fixed(self):
        content = "A" * 2000  # Long but no structure
        assert detect_strategy(content, ChunkingConfig()) == "fixed"


class TestHeaderChunking:
    def test_basic_h2_split(self):
        content = "# Title\n\nIntro\n\n## Section 1\n\nContent 1\n\n## Section 2\n\nContent 2"
        result = chunk_document(content, ChunkingConfig(strategy="headers"))

        assert len(result.chunks) == 3
        assert result.chunks[0].breadcrumb == "Title"
        assert result.chunks[1].breadcrumb == "Title > Section 1"
        assert result.chunks[2].breadcrumb == "Title > Section 2"

    def test_nested_headers(self):
        content = "# Title\n\n## A\n\n### A.1\n\nContent\n\n## B\n\nContent"
        config = ChunkingConfig(strategy="headers", header_split_levels=[2])
        result = chunk_document(content, config)

        # h3 should NOT trigger split, stays with parent h2
        assert len(result.chunks) == 3  # intro, A (with A.1), B

    def test_breadcrumb_depth(self):
        content = "# L1\n\n## L2\n\n### L3\n\nContent"
        config = ChunkingConfig(strategy="headers", header_split_levels=[2, 3])
        result = chunk_document(content, config)

        assert result.chunks[-1].breadcrumb == "L1 > L2 > L3"


class TestFixedSizeChunking:
    def test_basic_fixed_split(self):
        content = "word " * 500  # ~500 tokens
        config = ChunkingConfig(strategy="fixed", fixed_chunk_size=200)
        result = chunk_document(content, config)

        assert len(result.chunks) >= 2

    def test_overlap(self):
        content = "word " * 500
        config = ChunkingConfig(strategy="fixed", fixed_chunk_size=200, fixed_overlap=50)
        result = chunk_document(content, config)

        # Check overlap exists
        if len(result.chunks) >= 2:
            chunk1_end = result.chunks[0].content[-100:]
            chunk2_start = result.chunks[1].content[:100]
            # Some overlap should exist
            assert any(word in chunk2_start for word in chunk1_end.split())


class TestOversizedHandling:
    def test_oversized_chunk_gets_split(self):
        # Create a doc with one huge section
        content = "# Title\n\n## Big Section\n\n" + ("Content. " * 500)
        config = ChunkingConfig(strategy="headers", max_chunk_size=200)
        result = chunk_document(content, config)

        # The big section should be sub-chunked
        assert len(result.chunks) > 2


class TestUndersizedHandling:
    def test_undersized_chunks_get_merged(self):
        content = "# Title\n\n## A\n\nTiny\n\n## B\n\nAlso tiny\n\n## C\n\nTiny too"
        config = ChunkingConfig(strategy="headers", min_chunk_size=100)
        result = chunk_document(content, config)

        # Some chunks should be merged
        assert len(result.chunks) < 4


class TestSentenceBoundary:
    def test_splits_at_sentence(self):
        content = "First sentence. Second sentence. Third sentence. Fourth sentence."
        config = ChunkingConfig(strategy="fixed", fixed_chunk_size=10, complete_sentences=True)
        result = chunk_document(content, config)

        # Chunks should end with periods
        for chunk in result.chunks[:-1]:  # Last chunk might not
            assert chunk.content.rstrip().endswith('.')
```

### Integration Tests

```python
class TestChunkStorage:
    def test_add_resource_with_chunks(self, temp_config):
        # Create a test document
        doc = "# API\n\n## Endpoint 1\n\nContent 1\n\n## Endpoint 2\n\nContent 2"

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(doc)
            path = f.name

        resource_id = core.add_resource(
            type="doc",
            title="Test API",
            path=path,
            chunking_config=ChunkingConfig(strategy="headers"),
        )

        # Verify chunks were stored
        with get_db(temp_config) as conn:
            chunks = conn.execute(
                "SELECT * FROM resource_chunks WHERE resource_id = ?",
                (resource_id,)
            ).fetchall()

        assert len(chunks) >= 2

    def test_search_finds_chunk_content(self, temp_config):
        # Add resource with chunks
        doc = "# API\n\n## Create User\n\nCreates a new user in the system"
        # ... add resource ...

        # Search should find via chunk content
        results = search_resources("create new user", config=temp_config)
        assert len(results) > 0
```

---

## Implementation Order

Execute in this order for incremental, testable progress:

### Phase 1: Core Chunking Logic (no storage)

1. Create `src/ai_lessons/chunking.py`
2. Implement data structures: `ChunkingConfig`, `Chunk`, `ChunkingResult`
3. Implement `estimate_tokens()`
4. Implement `detect_strategy()`
5. Implement `chunk_by_headers()` - most common case
6. Implement `chunk_fixed_size()` - fallback
7. Implement `chunk_by_delimiter()` - optional patterns
8. Implement `_handle_oversized()` and `_handle_undersized()`
9. Write unit tests for all above
10. **Checkpoint: All chunking tests pass**

### Phase 2: CLI Preview

1. Add chunking options to `add-resource` command
2. Implement `_display_chunking_preview()`
3. Add `--preview` flag that shows preview and exits
4. Test manually with sample documents
5. **Checkpoint: `--preview` works end-to-end**

### Phase 3: Storage Integration

1. Add schema migration for new `resource_chunks` columns
2. Update `core.add_resource()` to accept `chunking_config`
3. Implement `_store_chunks()` in `core.py`
4. Wire up non-preview path in CLI
5. Write integration tests
6. **Checkpoint: Resources with chunks persist correctly**

### Phase 4: Search Integration

1. Update `search_resources()` to include chunk search
2. Implement `_search_chunks()` and `_merge_resource_and_chunk_results()`
3. Update search result display to show chunk context
4. Write search tests
5. **Checkpoint: Chunk content is searchable**

### Phase 5: MCP Integration

1. Update `add_resource` MCP tool schema
2. Update MCP handler to support chunking options
3. Add `preview` mode to MCP
4. Test with MCP inspector or Claude
5. **Checkpoint: MCP tools work with chunking**

### Phase 6: Documentation & Polish

1. Fill in CLI instructions in `docs/contributing/resources/README.md`
2. Add chunking examples to documentation
3. Add `--help` text for all new options
4. Final review and cleanup

---

## Open Questions / Future Work

1. **Embedding strategy for chunks**: Currently embeds `breadcrumb + content`. Should we also embed just the title for faster title-matching?

2. **Chunk retrieval display**: When a chunk matches, show just the chunk or the full parent resource? (Probably: chunk in results list, full resource on "show")

3. **Re-chunking**: If chunking config changes, should `refresh-resource` re-chunk? (Probably yes)

4. **Cross-chunk references**: Some chunks might reference others ("see above"). How to handle? (Probably: ignore for v1, consider for v2)

5. **Performance**: For 1934 Jira docs, chunking + embedding could take a while. Progress bar? Background job? (Progress bar for v1)
