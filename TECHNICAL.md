# Technical Documentation

This document provides technical details about the AI Lessons architecture, design decisions, and implementation.

## Architecture Overview

AI Lessons is a knowledge management system built on three core components:

1. **SQLite Database** - Stores entities and their relationships with vector embeddings
2. **Embedding Pipeline** - Generates and manages semantic embeddings for search
3. **CLI/MCP Interface** - Provides both command-line and programmatic access

```
┌─────────────────────────────────────────────────────────┐
│                    User Interface                        │
│  ┌──────────────┐              ┌───────────────────┐   │
│  │  CLI (Click) │              │  MCP Server       │   │
│  └──────┬───────┘              └────────┬──────────┘   │
│         │                               │               │
└─────────┼───────────────────────────────┼───────────────┘
          │                               │
          ▼                               ▼
┌─────────────────────────────────────────────────────────┐
│                    Core API Layer                        │
│  ┌────────────┐  ┌────────────┐  ┌─────────────────┐  │
│  │  Lessons   │  │ Resources  │  │     Rules       │  │
│  │  (core.py) │  │ (core.py)  │  │   (core.py)     │  │
│  └─────┬──────┘  └─────┬──────┘  └────────┬────────┘  │
└────────┼───────────────┼──────────────────┼────────────┘
         │               │                  │
         ▼               ▼                  ▼
┌─────────────────────────────────────────────────────────┐
│                  Supporting Services                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐ ┌─────────┐ │
│  │Embeddings│  │ Chunking │  │  Search  │ │  Links  │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘ └────┬────┘ │
└───────┼─────────────┼─────────────┼────────────┼───────┘
        │             │             │            │
        ▼             ▼             ▼            ▼
┌─────────────────────────────────────────────────────────┐
│                    Data Layer                            │
│  ┌───────────────────────────────────────────────────┐  │
│  │     SQLite Database (db.py, schema.py)            │  │
│  │  - Entity tables (lessons, resources, rules)      │  │
│  │  - Vector tables (lesson_embeddings, etc.)        │  │
│  │  - Graph edges (unified relationship table)       │  │
│  │  - Metadata (tags, contexts, chunks)              │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Major Components

### 1. Database Layer (`db.py`, `schema.py`)

**Location**: `src/ai_lessons/db.py`, `src/ai_lessons/schema.py`

**Purpose**: Manages SQLite database with vector search capabilities.

**Key Features**:
- Uses `sqlite-vec` extension for vector similarity search
- WAL mode enabled for better concurrency
- Foreign key constraints enforced
- Schema versioning with automatic migrations

**Design Decisions**:
- **Why SQLite?** - Single-file, zero-config, excellent for local-first applications
- **Why sqlite-vec?** - Native vector search without external dependencies
- **Type-prefixed IDs** - LSN/RES/RUL prefixes make entity types instantly recognizable
- **Unified edges table** - Single table for all relationships simplifies graph traversal

**Schema Structure**:
```sql
-- Core entities
lessons (id, title, content, confidence, source, ...)
resources (id, type, title, path, content, ...)
rules (id, title, content, rationale, approved, ...)
resource_chunks (id, resource_id, chunk_index, content, ...)

-- Relationships
edges (from_id, from_type, to_id, to_type, relation)
resource_anchors (from_id, edge_id, to_path, link_text, ...)

-- Metadata
lesson_tags, lesson_contexts, resource_tags, rule_tags
resource_versions (resource_id, version)

-- Vector search
lesson_embeddings (lesson_id, embedding)
resource_embeddings (resource_id, embedding)
chunk_embeddings (chunk_id, embedding)
```

**Migration System**:
- Schema version tracked in `meta` table
- Migrations in `_run_migrations()` are idempotent
- Each migration checks current version and applies changes conditionally

### 2. Core API (`core.py`)

**Location**: `src/ai_lessons/core.py`

**Purpose**: Primary programmatic interface for managing lessons, resources, and rules.

**Key Functions**:

**Lessons**:
- `add_lesson()` - Create new lesson with tags, contexts, confidence, source
- `get_lesson()` - Retrieve lesson by ID
- `update_lesson()` - Modify existing lesson
- `delete_lesson()` - Remove lesson
- `recall()` - Search for lessons (wrapper around search.py)
- `get_related()` - Find related entities via graph edges

**Resources**:
- `add_resource()` - Add document or script with automatic chunking
- `get_resource()` - Retrieve resource by ID
- `update_resource()` - Modify resource metadata
- `delete_resource()` - Remove resource and its chunks
- `refresh_resource()` - Re-read content from filesystem
- `get_chunk()` - Retrieve specific chunk
- `list_chunks()` - List chunks for a resource

**Rules**:
- `suggest_rule()` - Create rule (requires approval)
- `approve_rule()` - Approve pending rule
- `get_rule()` - Retrieve rule by ID
- `update_rule()` - Modify rule
- `delete_rule()` - Remove rule

**Graph**:
- `link_lessons()` - Create edge between entities
- `unlink_lessons()` - Remove edge
- `get_related()` - Traverse graph from entity

**Design Decisions**:
- **Type-prefixed IDs generated at creation** - LSN/RES/RUL prefixes for instant type recognition
- **Chunk IDs derived from resource** - Format: `RES<ulid>.<index>` makes parent relationship structural
- **Automatic embedding generation** - Embeddings created/updated transparently
- **Tag normalization** - Tag aliases resolved automatically via config

### 3. Embeddings (`embeddings.py`)

**Location**: `src/ai_lessons/embeddings.py`

**Purpose**: Abstract embedding generation with pluggable backends.

**Backends**:

1. **SentenceTransformersBackend** (default, free)
   - Uses `sentence-transformers` library
   - Runs locally on CPU (or GPU if available)
   - Default model: `all-MiniLM-L6-v2` (384 dimensions)
   - No API key required

2. **OpenAIBackend** (higher quality, requires API key)
   - Uses OpenAI's embedding API
   - Default model: `text-embedding-3-small` (1536 dimensions)
   - Requires `OPENAI_API_KEY` environment variable

**Design Decisions**:
- **Backend abstraction** - Easy to add new embedding providers
- **Lazy loading** - Models loaded only when first used
- **Batch support** - Efficient bulk embedding generation
- **Dimension tracking** - Database schema validates against configured dimensions

**Adding a New Backend**:
```python
class YourBackend(EmbeddingBackend):
    def embed(self, text: str) -> list[float]:
        # Generate single embedding
        pass

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        # Generate multiple embeddings efficiently
        pass

    @property
    def dimensions(self) -> int:
        # Return embedding dimensionality
        pass
```

### 4. Search (`search.py`)

**Location**: `src/ai_lessons/search.py`

**Purpose**: Hybrid semantic + keyword search with sophisticated scoring.

**Search Strategies**:

1. **vector_search()** - Pure semantic search using embeddings
2. **keyword_search()** - Pure keyword matching
3. **hybrid_search()** - Combines both (recommended)
4. **unified_search()** - Search across all entity types

**Scoring Algorithm**:

For semantic search:
```python
# Convert cosine distance to score using sigmoid
score = 1 / (1 + exp(k * (distance - center)))

# Add keyword boost (scaled)
keyword_boost = min(0.15, keyword_score * 0.025)

# Apply version scoring for resources
version_mult = compute_version_score(resource_versions, query_versions)

# Apply chunk specificity boost (3% for chunk matches)
specificity_mult = 1.03 if is_chunk else 1.0

final_score = (score + keyword_boost) * version_mult * specificity_mult
```

**Design Decisions**:
- **Sigmoid-based distance scoring** - Better differentiation than linear `1/(1+d)`
- **Keyword boosting** - Title matches weighted 3x, tags 2.5x, content 1x
- **Version scoring** - Resources scored by version relevance (exact > superset > subset > overlap)
- **Link boosting** - Lessons linked to high-scoring resources get score boost
- **Chunk-level search** - Documents searchable at both resource and chunk granularity

**Search Result Types**:
- `LessonResult` - Lesson match with confidence, source, contexts
- `ResourceResult` - Resource match with type, versions, path
- `ChunkResult` - Specific chunk match with breadcrumb, section info
- `RuleResult` - Rule match (only surfaces with tag overlap)
- `GroupedResourceResult` - Resource with all matching chunks grouped

### 5. Chunking (`chunking.py`)

**Location**: `src/ai_lessons/chunking.py`

**Purpose**: Intelligently split large documents into searchable chunks.

**Strategies**:

1. **headers** - Split on markdown headers (h2, h3, etc.)
   - Preserves document structure
   - Builds breadcrumb hierarchy
   - Best for well-structured markdown docs

2. **delimiter** - Split on custom regex patterns
   - Good for documents with consistent separators
   - Examples: horizontal rules (`---`), section markers

3. **fixed** - Fixed-size chunks with overlap
   - Fallback for unstructured text
   - Ensures no chunk exceeds max size
   - Overlap prevents information loss at boundaries

4. **single** - No chunking for small documents
   - Documents < 2x min_chunk_size kept whole
   - Avoids unnecessary splitting

5. **auto** - Detect best strategy automatically
   - Analyzes document structure
   - Chooses most appropriate strategy

**Chunking Pipeline**:
```
1. Strategy Selection (auto-detect or user-specified)
   ↓
2. Initial Chunking (by chosen strategy)
   ↓
3. Handle Oversized Chunks (recursive fixed-size split)
   ↓
4. Merge Undersized Chunks (combine adjacent small chunks)
   ↓
5. Extract Section Headers (for search hints)
   ↓
6. Generate Chunk Metadata (breadcrumbs, line numbers, warnings)
```

**Design Decisions**:
- **Preserve structure** - Headers become breadcrumbs for context
- **Graceful degradation** - Falls back to fixed-size if structure unclear
- **Size constraints** - Default 100-800 tokens balances context and specificity
- **Section extraction** - Headers within chunks stored for fragment linking

**Chunk Metadata**:
```python
@dataclass
class Chunk:
    index: int                    # Order in document (0-based)
    content: str                  # Chunk text
    title: str | None             # Section title (from header)
    breadcrumb: str | None        # "Parent > Child > Section"
    start_line: int               # First line (0-indexed)
    end_line: int                 # Last line (0-indexed)
    token_count: int              # Estimated tokens (chars/4)
    sections: list[str]           # Headers within chunk
    is_continuation: bool         # Part of split oversized chunk
    warnings: list[str]           # "oversized", "undersized"
```

### 6. Link Resolution (`links.py`)

**Location**: `src/ai_lessons/links.py`

**Purpose**: Extract and resolve markdown links between resources.

**Features**:
- Extracts markdown links `[text](path)` and `[text](path#fragment)`
- Resolves relative paths to absolute paths
- Finds target resource in database
- Resolves fragments to specific chunks
- Creates edges when targets exist
- Tracks unresolved links (dangling references)

**Link Flow**:
```
1. Extract links from markdown content
   ↓
2. Resolve relative paths → absolute paths
   ↓
3. Find source chunk (line number → chunk_id)
   ↓
4. Look up target resource (path → resource_id)
   ↓
5. Resolve fragment (section name → chunk_id)
   ↓
6. Create edge (if target exists)
   ↓
7. Store anchor metadata (path, fragment, link_text)
```

**Design Decisions**:
- **Store unresolved links** - Tracks references before targets imported
- **Fragment normalization** - Handles different header formats (hyphens, underscores)
- **Same-file references** - Supports `[text](#section)` within document
- **Automatic resolution** - Links resolved when targets added later

**Database Structure**:
```sql
-- Unified edges for resolved links
edges (from_id, from_type, to_id, to_type, relation='references')

-- Anchor metadata (includes unresolved links with edge_id=NULL)
resource_anchors (
    from_id,        -- Source chunk/resource
    edge_id,        -- NULL if unresolved
    to_path,        -- Original markdown path
    to_fragment,    -- Section anchor
    link_text       -- Display text
)
```

### 7. CLI (`cli/`)

**Location**: `src/ai_lessons/cli/`

**Purpose**: Command-line interface built with Click.

**Structure**:
- `admin.py` - Database management (init, stats, migrations)
- `contribute.py` - Add/modify entities (lessons, resources, rules)
- `recall.py` - Search and view entities
- `display.py` - Output formatting (tables, JSON, colored text)
- `utils.py` - Shared utilities (ID parsing, error handling)

**Command Groups**:

1. **admin** - System management
   - `init` - Initialize database
   - `stats` - Show entity counts, tags, sources
   - `merge-tags` - Merge tag A into B
   - `add-source` - Register new source type
   - `pending-rules` - List unapproved rules
   - `approve-rule` - Approve a rule

2. **contribute** - Content management
   - `add-lesson` - Create lesson
   - `add-resource` - Add doc/script with chunking
   - `suggest-rule` - Propose rule for approval
   - `update` - Unified update (detects type from ID)
   - `delete` - Unified delete (detects type from ID)
   - `link` - Create edge between entities
   - `unlink` - Remove edge
   - `refresh` - Reload resource from filesystem

3. **recall** - Search and view
   - `search` - Unified search across types
   - `show` - Display entity (detects type from ID)
   - `list` - List entities by type
   - `related` - Show related entities via graph
   - `tags` - List all tags
   - `sources` - List source types
   - `confidence` - List confidence levels

**Design Decisions**:
- **Unified commands** - `update`, `delete`, `show` work with any ID type
- **Type detection from ID prefix** - Commands automatically handle LSN/RES/RUL/chunk IDs
- **Rich output** - Colors, tables, JSON export for scripting
- **Preview mode** - `--preview` shows chunking without committing

### 8. MCP Server (`mcp_server.py`)

**Location**: `src/ai_lessons/mcp_server.py`

**Purpose**: Model Context Protocol server for Claude Code integration.

**Available Tools**:
- `learn` - Save a new lesson
- `recall` - Search for lessons
- `get_lesson` - Retrieve specific lesson
- `list_lessons` - List recent lessons
- `link` - Create relationship between lessons
- `search_resources` - Find relevant documents
- `get_resource` - Retrieve resource content
- `run_script` - Execute a script resource
- `suggest_rule` - Propose a new rule

**Design Decisions**:
- **Async/await** - MCP server is fully async
- **Structured responses** - Returns JSON-serializable dictionaries
- **Safety** - Script execution is opt-in and sandboxed
- **Context-aware** - Can infer tags/contexts from conversation

**Integration**:
```json
{
  "mcpServers": {
    "ai-lessons": {
      "command": "ai-lessons-mcp"
    }
  }
}
```

## Design Patterns

### 1. Type-Prefixed IDs

**Why**: Instant type recognition without database lookup.

**Format**:
- Lessons: `LSN<ulid>` (e.g., `LSN01KCPN9VWAZNSKYVHPCWVPXA2C`)
- Resources: `RES<ulid>`
- Rules: `RUL<ulid>`
- Chunks: `RES<ulid>.<index>` (e.g., `RES01KCPN....0`, `RES01KCPN....1`)

**Benefits**:
- No database lookup to determine type
- Unified CLI commands work across types
- Chunk parent relationship is structural
- Better error messages

### 2. Unified Edges Table

**Why**: Simplify graph relationships across entity types.

**Schema**:
```sql
edges (
    from_id TEXT,      -- Any entity ID (LSN/RES/RUL/chunk)
    from_type TEXT,    -- 'lesson', 'resource', 'rule', 'chunk'
    to_id TEXT,        -- Any entity ID
    to_type TEXT,      -- 'lesson', 'resource', 'rule', 'chunk'
    relation TEXT      -- 'related_to', 'documents', 'references', etc.
)
```

**Benefits**:
- Any entity can link to any other entity
- Single query to find all relationships
- Consistent traversal logic
- Extensible relations

### 3. Resource + Chunk Embeddings

**Why**: Balance between broad relevance and specific matches.

**Approach**:
- Whole resource embeddings capture overall themes
- Chunk embeddings enable section-level matching
- Search results deduplicated by resource (best score wins)

**Benefits**:
- Find relevant documents (resource-level)
- Jump to specific sections (chunk-level)
- Better than document-only or chunk-only approaches

### 4. Idempotent Migrations

**Why**: Safe to run migrations multiple times.

**Pattern**:
```python
if current_version < N:
    # Check if already migrated
    cursor = conn.execute("PRAGMA table_info(table_name)")
    existing_cols = {row[1] for row in cursor}

    if "new_column" not in existing_cols:
        conn.execute("ALTER TABLE table_name ADD COLUMN new_column TEXT")

    current_version = N
```

**Benefits**:
- Can re-run migrations if interrupted
- Easier to test migration logic
- Safer for production databases

## Performance Considerations

### Database

- **WAL mode** - Better concurrency for multiple readers
- **Indexes** - Strategic indexes on foreign keys, search fields
- **Vector limits** - Fetch `k=limit*2` for filtering, then limit
- **Batch embeddings** - Generate multiple embeddings in single call

### Search

- **Hybrid approach** - Combines semantic + keyword for best results
- **Version filtering** - Prune disjoint versions early
- **Link boosting** - Only for high-scoring linked resources (> 0.65)
- **Result limits** - Configurable default (10) to control response time

### Chunking

- **Strategy detection** - Quick regex checks before full parse
- **Lazy embedding** - Only embed when stored, not during preview
- **Oversized handling** - Recursive splitting for outliers
- **Token estimation** - Fast approximation (chars/4) vs. accurate tokenization

## Configuration

**Location**: `~/.ai/lessons/config.yaml`

**Options**:
```yaml
# Embedding configuration
embedding:
  backend: sentence-transformers   # or: openai
  model: all-MiniLM-L6-v2         # or: text-embedding-3-small
  api_key: ${OPENAI_API_KEY}      # Optional, can reference env vars
  dimensions: 384                  # Auto-detected if omitted

# Search tuning
search:
  default_limit: 10
  hybrid_weight_semantic: 0.7
  hybrid_weight_keyword: 0.3

# Tag normalization
tag_aliases:
  js: javascript
  ts: typescript
  py: python

# Known tags (for validation/autocomplete)
known_tags:
  - jira
  - api
  - python
  - javascript

# Feature flags
suggest_feedback: true            # Prompt for search quality feedback
```

## Testing

**Location**: `tests/`

**Coverage**:
- `test_core.py` - Core API functions
- `test_chunking.py` - Document chunking strategies
- `test_search.py` - Search and scoring
- `test_edges.py` - Graph relationships
- `test_chunk_ids.py` - Chunk ID parsing

**Run tests**:
```bash
pytest
```

## Future Improvements

### Potential Enhancements

1. **Full-text search** - SQLite FTS5 for better keyword search
2. **Async API** - Async variants of core functions for better concurrency
3. **Incremental updates** - Smart re-embedding on content changes
4. **Batch operations** - Bulk import/export utilities
5. **Query caching** - Cache frequent search results
6. **Embedding compression** - Reduce storage with quantization
7. **Multi-user support** - User namespaces and permissions
8. **Web UI** - Browser-based interface for browsing/searching
9. **Import/export** - Backup and restore entire knowledge base
10. **LLM summarization** - Auto-generate chunk summaries for better matching

### Known Limitations

1. **Local only** - No remote database support (by design)
2. **Single process** - WAL mode helps but not designed for high concurrency
3. **English-focused** - Embeddings and chunking optimized for English
4. **Memory usage** - Large embedding models require significant RAM
5. **No versioning** - Entities updated in-place (no history tracking)

## Additional Resources

- SQLite-vec documentation: https://github.com/asg017/sqlite-vec
- Sentence Transformers: https://www.sbert.net/
- Model Context Protocol: https://modelcontextprotocol.io/
- Click documentation: https://click.palletsprojects.com/
