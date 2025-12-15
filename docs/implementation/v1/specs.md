# AI Lessons v1 - Technical Specifications

This document provides detailed technical specifications for the AI Lessons system, including rationale for design decisions and implementation details.

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Database](#2-database)
3. [Schema](#3-schema)
4. [Embeddings](#4-embeddings)
5. [Search](#5-search)
6. [Organization](#6-organization)
7. [Confidence & Source](#7-confidence--source)
8. [Graph](#8-graph)
9. [Configuration](#9-configuration)
10. [Interfaces](#10-interfaces)
11. [Operational Constraints](#11-operational-constraints)
12. [Future Considerations](#12-future-considerations)

---

## 1. Problem Statement

### Core Need

AI agents and developers accumulate knowledge through debugging and problem-solving. This knowledge is typically lost between sessions. AI Lessons provides a persistent, searchable knowledge base that:

1. Captures lessons at the moment of discovery
2. Retrieves relevant knowledge when facing similar problems
3. Builds connections between related concepts over time

### Trigger Conditions

A lesson should be saved when:
- You didn't know how to solve something initially
- You tried something and got an unexpected result
- You had to debug/iterate to find a solution

**Rationale:** These moments generate hard-won knowledge. Capturing them prevents re-learning the same lessons repeatedly.

### Multi-Agent Requirement

The system must work with:
- Claude Code (via MCP server)
- Custom CLI agents (via CLI)
- Gemini or other LLMs (via CLI)
- Direct human use (via CLI)

**Rationale:** Knowledge should be tool-agnostic. A lesson learned in Claude should help Gemini.

---

## 2. Database

### Decision: SQLite + sqlite-vec

### Alternatives Considered

| Database | Pros | Cons | Verdict |
|----------|------|------|---------|
| **ChromaDB** | Easy vector search, metadata filtering | Separate directory, Python-only, version issues | Viable but less portable |
| **SQLite + sqlite-vec** | Single file, portable, SQL power, vector search | More DIY | **Selected** |
| **LanceDB** | Single file, native vectors, fast | Newer ecosystem | Strong alternative |
| **Postgres + pgvector** | Production-grade | Overkill for local, needs server | Over-engineered |
| **Neo4j** | True graph DB | Heavy, needs server | Too heavy |

### Rationale

1. **Single file** is critical—syncs with dotfiles, portable across machines
2. **<2-3GB RAM** constraint eliminates server-based solutions
3. SQLite is rock-solid and universally available
4. sqlite-vec adds vector capabilities via extension
5. The edges table provides "graph-like" traversal without graph DB overhead
6. If we outgrow it, the schema maps cleanly to a "real" graph DB

### Connection Management

```python
# Use pysqlite3 for extension loading support
try:
    import pysqlite3 as sqlite3
except ImportError:
    import sqlite3

def _get_connection(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
```

**Note:** Standard library sqlite3 may not have extension loading enabled. pysqlite3-binary provides this capability.

### WAL Mode

Write-Ahead Logging (WAL) enables concurrent reads during writes. At expected scale (human-paced learning), write conflicts are rare.

---

## 3. Schema

### Reference Tables vs CHECK Constraints

For enum-like fields (confidence, source), we use reference tables instead of CHECK constraints:

```sql
CREATE TABLE confidence_levels (
    name TEXT PRIMARY KEY,
    ordinal INTEGER  -- For sorting
);

CREATE TABLE source_types (
    name TEXT PRIMARY KEY,
    description TEXT,
    typical_confidence TEXT
);

-- Lessons reference via FK
CREATE TABLE lessons (
    ...
    confidence TEXT REFERENCES confidence_levels(name),
    source TEXT REFERENCES source_types(name),
    ...
);
```

### Tradeoffs

| Aspect | CHECK Constraint | Reference Table |
|--------|------------------|-----------------|
| Add new value | Schema change (table rebuild in SQLite) | `INSERT` |
| Query valid values | Parse schema or hardcode | `SELECT * FROM source_types` |
| Store metadata | Not possible | Natural |
| Enforce validity | Always (DB level) | FK = strict |
| Typo risk | None (rejected) | With FK = none |

**Rationale:** Reference tables turn schema into data. Data is easy to change; schema is not. Adding a new source type becomes `INSERT INTO source_types ...` rather than a migration.

### Core Tables

```sql
-- Metadata
CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Reference tables
CREATE TABLE confidence_levels (
    name TEXT PRIMARY KEY,
    ordinal INTEGER NOT NULL
);

CREATE TABLE source_types (
    name TEXT PRIMARY KEY,
    description TEXT,
    typical_confidence TEXT
);

-- Core entity
CREATE TABLE lessons (
    id TEXT PRIMARY KEY,              -- ULID
    title TEXT NOT NULL,              -- Keyword searchable
    content TEXT NOT NULL,            -- Semantic searchable
    confidence TEXT REFERENCES confidence_levels(name),
    source TEXT REFERENCES source_types(name),
    source_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Many-to-many relationships
CREATE TABLE lesson_tags (
    lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (lesson_id, tag)
);

CREATE TABLE lesson_contexts (
    lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    context TEXT NOT NULL,
    applies BOOLEAN DEFAULT TRUE,  -- FALSE = anti-context
    PRIMARY KEY (lesson_id, context, applies)
);

-- Graph edges
CREATE TABLE edges (
    from_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    to_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    relation TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (from_id, to_id, relation)
);

-- Tag relationships (for aliases, hierarchy)
CREATE TABLE tag_relations (
    from_tag TEXT NOT NULL,
    to_tag TEXT NOT NULL,
    relation TEXT NOT NULL,
    PRIMARY KEY (from_tag, to_tag, relation)
);
```

### Vector Table

```sql
CREATE VIRTUAL TABLE lesson_embeddings USING vec0(
    lesson_id TEXT PRIMARY KEY,
    embedding FLOAT[{dimensions}]  -- 384 for MiniLM, 1536 for OpenAI
);
```

**Note:** Dimensions must match the embedding model. Changing models requires rebuilding the vector table.

### Indexes

```sql
CREATE INDEX idx_lesson_tags_tag ON lesson_tags(tag);
CREATE INDEX idx_lesson_tags_lesson ON lesson_tags(lesson_id);
CREATE INDEX idx_lesson_contexts_context ON lesson_contexts(context);
CREATE INDEX idx_edges_from ON edges(from_id);
CREATE INDEX idx_edges_to ON edges(to_id);
CREATE INDEX idx_lessons_created ON lessons(created_at);
CREATE INDEX idx_lessons_updated ON lessons(updated_at);
CREATE INDEX idx_lessons_confidence ON lessons(confidence);
CREATE INDEX idx_lessons_source ON lessons(source);
```

### ID Generation

Uses ULIDs (Universally Unique Lexicographically Sortable Identifiers):

```python
from ulid import ULID
lesson_id = str(ULID())  # e.g., "01ARZ3NDEKTSV4RRFFQ69G5FAV"
```

**Rationale:**
- Sortable by creation time (unlike UUIDv4)
- Short and URL-safe (unlike UUIDv1)
- No coordination needed (unlike auto-increment)

---

## 4. Embeddings

### Architecture

```python
class EmbeddingBackend(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]: ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...

    @property
    @abstractmethod
    def dimensions(self) -> int: ...
```

### Backends

#### Sentence-Transformers (Default)

```python
class SentenceTransformersBackend(EmbeddingBackend):
    def __init__(self, model_name="all-MiniLM-L6-v2", device="cpu"):
        self.model_name = model_name
        self.device = device
        self._model = None  # Lazy loaded
```

- **Model:** all-MiniLM-L6-v2 (384 dimensions)
- **Pros:** Free, runs locally, no API key
- **Cons:** Lower quality than OpenAI, requires PyTorch

**Note:** Forces CPU mode to avoid CUDA compatibility issues on older GPUs.

#### OpenAI

```python
class OpenAIBackend(EmbeddingBackend):
    def __init__(self, model_name="text-embedding-3-small", api_key=None):
        self.model_name = model_name
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
```

- **Model:** text-embedding-3-small (1536 dimensions)
- **Pros:** Higher quality embeddings
- **Cons:** Costs money, requires API key, network dependency

### Embedding Strategy

Content is embedded as: `{title}\n\n{content}`

**Rationale:** Title provides keywords, content provides context. Combining them gives the embedding model both signals.

### Model Switching

Changing embedding models requires re-embedding all lessons:

```bash
# If config changes model, db.init_db() will detect dimension mismatch
# Use force=True to rebuild:
ai-lessons admin init --force
```

---

## 5. Search

### Hybrid Search Strategy

Pure semantic search often misses exact keyword matches. Pure keyword search misses semantic relationships. Hybrid search combines both.

### Implementation

```
Query → [Vector Search] + [Keyword Search] → Reciprocal Rank Fusion → Results
```

#### Vector Search

```sql
SELECT l.*, le.distance
FROM lessons l
JOIN lesson_embeddings le ON l.id = le.lesson_id
WHERE le.embedding MATCH ?
AND k = ?
```

Uses sqlite-vec's MATCH operator for approximate nearest neighbor search.

#### Keyword Search

Simple TF-like scoring:
- Title matches weighted 3x
- Content matches weighted 1x
- Normalized by query term count

```python
def _keyword_score(query, title, content):
    query_terms = query.lower().split()
    score = 0
    for term in query_terms:
        if term in title.lower():
            score += 3.0
        if term in content.lower():
            score += 1.0
    return score / len(query_terms)
```

#### Reciprocal Rank Fusion (RRF)

Combines rankings from both methods:

```python
k = 60  # RRF constant
for lesson_id in all_ids:
    score = 0
    if lesson_id in vector_ranks:
        score += semantic_weight / (k + vector_ranks[lesson_id])
    if lesson_id in keyword_ranks:
        score += keyword_weight / (k + keyword_ranks[lesson_id])
```

Default weights: semantic=0.7, keyword=0.3 (configurable).

### Filtering

Filters are applied before scoring:
- Tag filter: Lesson must have at least one matching tag
- Context filter: Lesson must apply in given context
- Confidence minimum: Lesson must meet minimum confidence
- Source filter: Lesson must have specified source

**Rationale:** Filter-then-rank is more efficient than rank-then-filter for small datasets.

---

## 6. Organization

### Decision: Tags + Graph Edges (No Hierarchy)

### Alternatives Considered

#### Directory Hierarchy
```
~/.ai/lessons/
├── jira/
│   └── workflows/
│       └── update-gotcha.md
```

**Discarded:** Same knowledge often belongs in multiple places. "Jira API rate limiting" is both a Jira lesson and an API patterns lesson.

#### Flat Files with Frontmatter
```yaml
---
tags: [jira, api, gotcha]
---
Content here...
```

**Considered viable but:** Requires file parsing, harder to query, no relationship modeling.

### Tags

- Free-form strings, normalized to lowercase
- No constraints (any tag is valid)
- Aliases resolved via config (`js` → `javascript`)
- CLI warns on unknown tags (if `known_tags` configured)

### Tag Management

```yaml
# config.yaml
tag_aliases:
  js: javascript
  proj: project

known_tags:
  - jira
  - api
  - python
```

Periodic cleanup:
```bash
ai-lessons recall tags --counts     # See all tags with usage
ai-lessons admin merge-tags js javascript  # Consolidate
```

### Contexts and Anti-Contexts

Contexts describe when a lesson applies:
```python
contexts=["shared team branch", "after rebase"]
anti_contexts=["personal feature branch", "solo project"]
```

**Rationale:** Same knowledge can be helpful or harmful depending on situation. `git push -f` is dangerous on shared branches, fine on personal branches.

---

## 7. Confidence & Source

### Why Both?

Confidence means nothing without source context:
- "High confidence inference from misread logs" = unreliable
- "Medium confidence from testing" = probably reliable

### Confidence Levels

| Level | Ordinal | Meaning |
|-------|---------|---------|
| very-low | 1 | Wild guess, untested assumption |
| low | 2 | Some evidence but shaky |
| medium | 3 | Reasonable confidence, worked once |
| high | 4 | Well-tested, multiple confirmations |
| very-high | 5 | Extremely confident, battle-tested |

**Note:** No "verified" level. "Verified" sounds objective but isn't—someone can confidently "verify" a wrong conclusion.

### Source Types

| Source | Description | Typical Confidence |
|--------|-------------|-------------------|
| tested | Ran code, verified behavior | high |
| documented | Official docs/specs | medium-high |
| observed | Saw in logs/output | medium |
| inferred | Reasoned from evidence | low-medium |
| hearsay | Someone said so | low |

### Source Notes

Free-form text for context:
```python
source_notes="Lost 3 statuses on HSP project, had to recreate manually"
```

---

## 8. Graph

### Use Cases

| Need | Solution |
|------|----------|
| "What's related to X?" | Direct edge traversal |
| "How does A connect to B?" | Path finding |
| "Show me the cluster around X" | Subgraph extraction |

### Edge Types

Free-form relation strings. Common patterns:
- `related_to` - General relationship
- `derived_from` - This lesson came from that one
- `contradicts` - These lessons conflict
- `supersedes` - This lesson replaces that one
- `example_of` - This is an instance of that pattern

### Graph Traversal

Uses recursive CTE for N-hop traversal:

```sql
WITH RECURSIVE related AS (
    SELECT to_id, 1 as depth
    FROM edges WHERE from_id = ?

    UNION

    SELECT e.to_id, r.depth + 1
    FROM edges e
    JOIN related r ON e.from_id = r.to_id
    WHERE r.depth < ?
)
SELECT DISTINCT to_id FROM related;
```

**Rationale:** SQLite recursive CTEs give us graph-like traversal without a graph DB.

---

## 9. Configuration

### Location

`~/.ai/lessons/config.yaml`

### Structure

```yaml
# Embedding configuration
embedding:
  backend: sentence-transformers  # or: openai
  model: all-MiniLM-L6-v2         # model name
  # api_key: ${OPENAI_API_KEY}    # for openai backend

# Search tuning
search:
  default_limit: 10
  hybrid_weight_semantic: 0.7
  hybrid_weight_keyword: 0.3

# Tag management
tag_aliases:
  js: javascript
  proj: project

known_tags:
  - jira
  - api
```

### Environment Variables

API keys support environment variable syntax:
```yaml
embedding:
  api_key: ${OPENAI_API_KEY}
```

Resolved at config load time.

---

## 10. Interfaces

### CLI

Click-based CLI with three command groups:

```
ai-lessons
├── admin     # Database management
├── learn     # Create/modify lessons
└── recall    # Search/view lessons
```

Entry point defined in `pyproject.toml`:
```toml
[project.scripts]
ai-lessons = "ai_lessons.cli:main"
```

### MCP Server

Exposes core functionality as MCP tools:

| Tool | Purpose |
|------|---------|
| `learn` | Add a new lesson |
| `recall` | Search for lessons |
| `get_lesson` | Get lesson by ID |
| `update_lesson` | Modify lesson |
| `delete_lesson` | Remove lesson |
| `related` | Get related lessons |
| `link` | Create edge |
| `tags` | List tags |
| `sources` | List source types |
| `confidence_levels` | List confidence levels |

Entry point:
```toml
[project.scripts]
ai-lessons-mcp = "ai_lessons.mcp_server:run"
```

### Core API

All interfaces call the same core functions:

```python
# CRUD
add_lesson(title, content, tags, ...) -> str
get_lesson(lesson_id) -> Lesson
update_lesson(lesson_id, ...) -> bool
delete_lesson(lesson_id) -> bool

# Search
recall(query, tags, contexts, ...) -> list[SearchResult]

# Graph
get_related(lesson_id, depth, relations) -> list[Lesson]
link_lessons(from_id, to_id, relation) -> bool
unlink_lessons(from_id, to_id, relation) -> int

# Reference data
list_tags(with_counts) -> list[Tag]
list_sources() -> list[SourceType]
list_confidence_levels() -> list[ConfidenceLevel]
```

---

## 11. Operational Constraints

### Resource Limits

- **RAM:** <2-3GB (eliminates server-based solutions)
- **Storage:** Single SQLite file (tens of MB for thousands of lessons)

### Concurrency

- WAL mode enables concurrent reads
- Short transactions for writes
- At human pace, conflicts are rare

### Portability

- Single file database syncs with dotfiles
- No server process = no port conflicts
- Config file also syncs

### Backup

```bash
# Simple file copy
cp ~/.ai/lessons/knowledge.db ~/.ai/lessons/knowledge.db.bak

# Export to JSON (future)
ai-lessons admin export > backup.json
```

### Scale Expectations

| Lessons | Performance |
|---------|-------------|
| 100 | Instant |
| 1,000 | Instant |
| 10,000 | Sub-second, may need index tuning |
| 100,000+ | Unlikely to reach; revisit if needed |

---

## 12. Future Considerations

### Documented but Not Implemented

1. **Tags as graph nodes** - Full relationship modeling between tags
2. **Semantic tag deduplication** - Embed tags, auto-merge similar ones
3. **Contexts as graph nodes** - Promote contexts to first-class entities
4. **LLM re-ranking** - Use LLM to re-rank top N results
5. **Query expansion** - LLM suggests related terms before search
6. **Confidence decay** - Lower confidence over time unless revalidated
7. **Rationale integration** - Bridge to state-tracking project

### Migration Paths

#### Contexts to Graph Nodes

Current: Contexts are strings in `lesson_contexts` table.

Future:
```sql
CREATE TABLE contexts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ...
);

-- Edges between contexts
INSERT INTO edges (from_id, to_id, relation)
VALUES ('ctx:shared-branch', 'ctx:team-environment', 'subset_of');
```

#### Different Embedding Model

1. Update `config.yaml` with new model
2. Run `ai-lessons admin init --force`
3. Re-embed all lessons (automatic)

---

## Appendix: Lessons from Jira MCP Server

This project was informed by building the Jira API documentation search:

1. **Lightweight search results** - Return summaries, not full content
2. **Deterministic lookups** - `get_lesson(id)` for exact retrieval
3. **Hybrid retrieval** - Pure semantic search misses exact matches
4. **Focused chunks embed better** - One lesson = one concept

These lessons directly shaped the AI Lessons architecture.
