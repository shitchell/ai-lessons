# AI Memory System - Technical Design

This document provides a technical overview of all system components, their relationships, and designed flexibility points for future adaptation.

---

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Interfaces                          │
├─────────────────────────────┬───────────────────────────────────┤
│      MCP Server             │           CLI Tool                │
│  (Claude Code, MCP agents)  │  (Gemini, custom agents, human)   │
└──────────────┬──────────────┴──────────────┬────────────────────┘
               │                             │
               └──────────────┬──────────────┘
                              │
                              ▼
               ┌──────────────────────────────┐
               │        Core Library          │
               │  (Python: ai_lessons/core.py) │
               │  - CRUD operations           │
               │  - Search (hybrid)           │
               │  - Graph traversal           │
               │  - Embedding generation      │
               │  - Reference table mgmt      │
               └──────────────┬───────────────┘
                              │
                              ▼
               ┌──────────────────────────────┐
               │      SQLite + sqlite-vec     │
               │      (~/.ai/lessons/)         │
               │  - knowledge.db              │
               │  - config.yaml               │
               └──────────────────────────────┘
```

**Key principle:** All interfaces share the same core library and database. No interface has special capabilities; they differ only in interaction mode.

---

## 2. Component Breakdown

### 2.1 Storage Layer (SQLite + sqlite-vec)

**File:** `~/.ai/lessons/knowledge.db`

#### Tables

```sql
-- Metadata
meta (key, value)

-- Reference tables (enum-like, but mutable)
confidence_levels (name, ordinal)
source_types (name, description, typical_confidence)

-- Core entities
lessons (id, title, content, confidence, source, source_notes, created_at, updated_at)
lesson_tags (lesson_id, tag)
lesson_contexts (lesson_id, context, applies)

-- Graph structure
edges (from_id, to_id, relation)
tag_relations (from_tag, to_tag, relation)

-- Vector search
lesson_embeddings VIRTUAL TABLE (lesson_id, embedding FLOAT[384])
```

#### Indexes

```sql
CREATE INDEX idx_lesson_tags_tag ON lesson_tags(tag);
CREATE INDEX idx_lesson_tags_lesson ON lesson_tags(lesson_id);
CREATE INDEX idx_lesson_contexts_context ON lesson_contexts(context);
CREATE INDEX idx_edges_from ON edges(from_id);
CREATE INDEX idx_edges_to ON edges(to_id);
CREATE INDEX idx_lessons_created ON lessons(created_at);
CREATE INDEX idx_lessons_updated ON lessons(updated_at);
```

#### Configuration

**File:** `~/.ai/lessons/config.yaml`

```yaml
# Tag management
tag_aliases:
  proj: project
  projects: project
  js: javascript

known_tags:
  - jira
  - api
  - python
  # ... (optional, for warnings)

# Search settings
search:
  default_limit: 10
  hybrid_weight_semantic: 0.7
  hybrid_weight_keyword: 0.3

# Embedding model
embedding:
  model: all-MiniLM-L6-v2
  # model: text-embedding-3-small  # OpenAI alternative
```

---

### 2.2 Core Library

**Module:** `ai_lessons/core.py`

Provides all business logic, shared by MCP and CLI.

#### Primary Functions

```python
# CRUD
def add_lesson(title, content, tags, contexts, anti_contexts,
               confidence, source, source_notes) -> str  # returns lesson_id
def get_lesson(lesson_id) -> Lesson
def update_lesson(lesson_id, **fields) -> None
def delete_lesson(lesson_id) -> None

# Search
def recall(query, tags=None, contexts=None, confidence_min=None,
           source=None, limit=10) -> List[SearchResult]
def keyword_search(query, **filters) -> List[Lesson]
def hybrid_search(query, **filters) -> List[SearchResult]  # semantic + keyword

# Graph
def get_related(lesson_id, depth=1, relations=None) -> List[Lesson]
def link_lessons(from_id, to_id, relation) -> None
def unlink_lessons(from_id, to_id, relation=None) -> None

# Reference tables
def list_sources() -> List[SourceType]
def add_source(name, description, typical_confidence) -> None
def list_confidence_levels() -> List[ConfidenceLevel]
def list_tags(with_counts=False) -> List[Tag]
def merge_tags(from_tag, to_tag) -> int  # returns affected count

# Embedding
def embed_text(text) -> List[float]
def reembed_lesson(lesson_id) -> None
def reembed_all() -> None
```

#### Internal Helpers

```python
def _resolve_tag_aliases(tags: List[str]) -> List[str]
def _validate_reference(table, value) -> bool
def _suggest_similar(table, value) -> List[str]
def _run_migrations() -> None
```

---

### 2.3 MCP Server

**File:** `~/.ai/lessons/mcp-server/server.py`

Exposes core library as MCP tools for Claude Code and MCP-compatible agents.

#### Tools

| Tool | Parameters | Returns |
|------|------------|---------|
| `learn` | title, content, tags[], contexts[], anti_contexts[], confidence?, source?, source_notes? | lesson_id |
| `recall` | query, tags[]?, contexts[]?, confidence_min?, source?, limit? | List of matches with scores |
| `get` | lesson_id | Full lesson with metadata |
| `update` | lesson_id, ...fields | Success/failure |
| `delete` | lesson_id | Success/failure |
| `related` | lesson_id, depth?, relations[]? | List of related lessons |
| `link` | from_id, to_id, relation | Success/failure |
| `tags` | with_counts? | List of tags |
| `sources` | - | List of source types |
| `contexts` | - | List of known contexts |

#### Response Format

```json
{
  "success": true,
  "data": { ... },
  "warnings": ["tag 'jra' not recognized, did you mean 'jira'?"],
  "suggestions": { ... }
}
```

---

### 2.4 CLI Tool

**File:** `~/bin/ai-lessons` (symlink to `~/.ai/lessons/cli/main.py`)

Same capabilities as MCP, optimized for terminal interaction.

#### Commands

```bash
# Learning
ai-lessons add --title "..." --content "..." --tags a,b,c [options]
ai-lessons add --interactive  # Guided prompts

# Searching
ai-lessons search "query" [--tags ...] [--context ...] [--limit N]
ai-lessons show <lesson_id>

# Graph
ai-lessons related <lesson_id> [--depth N]
ai-lessons link <from_id> <to_id> --relation "derived_from"
ai-lessons unlink <from_id> <to_id>

# Management
ai-lessons tags [--counts]
ai-lessons sources [--review]
ai-lessons sources --add "name" --description "..."
ai-lessons sources --merge "old" "new"
ai-lessons contexts

# Maintenance
ai-lessons export [--format json|yaml] [--tags ...] > backup.json
ai-lessons import < backup.json
ai-lessons reembed [--all | --lesson <id>]
ai-lessons stats
```

#### Interactive Mode Features

- Tab completion for tags, sources, contexts
- Fuzzy matching with "did you mean?" suggestions
- Multi-line content input
- Preview before commit

---

## 3. Data Flow

### 3.1 Learning Flow

```
User/Agent provides lesson
         │
         ▼
┌─────────────────────────────────┐
│ 1. Validate & normalize input   │
│    - Resolve tag aliases        │
│    - Check reference tables     │
│    - Suggest corrections        │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│ 2. Create/update references     │
│    - Auto-create unknown        │
│      sources (flag for review)  │
│    - Warn on unknown tags       │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│ 3. Generate embedding           │
│    - Combine title + content    │
│    - sentence-transformers      │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│ 4. Store in DB                  │
│    - lessons table              │
│    - lesson_tags (many)         │
│    - lesson_contexts (many)     │
│    - lesson_embeddings          │
└─────────────────────────────────┘
```

### 3.2 Recall Flow

```
User/Agent provides query + filters
         │
         ▼
┌─────────────────────────────────┐
│ 1. Parse & expand query         │
│    - Resolve tag aliases        │
│    - Optional: LLM expansion    │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│ 2. Filter by metadata           │
│    - Tags (AND/OR logic)        │
│    - Contexts                   │
│    - Source types               │
│    - Confidence minimum         │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│ 3. Hybrid search                │
│    - Vector similarity (0.7)    │
│    - Keyword BM25 (0.3)         │
│    - Reciprocal rank fusion     │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│ 4. Rank & return                │
│    - Include confidence, source │
│    - Include contexts           │
│    - Limit results              │
└─────────────────────────────────┘
```

---

## 4. Flexibility Points & Failure Modes

This section identifies potential failure modes and how the current design accommodates future workarounds.

### 4.1 Confidence Mislabeling

**Failure mode:** High-confidence lessons that are actually wrong cause agents to repeat mistakes with false certainty.

**Current design accommodations:**
- `source` field separates confidence from evidence type
- `source_notes` captures reasoning for later audit
- `created_at` / `updated_at` enable temporal analysis
- Confidence is mutable (can be downgraded)

**Future workarounds:**

1. **Confidence decay**
   - Automatically lower confidence over time unless revalidated
   - Design support: timestamps already stored, add `last_validated_at` column

2. **Validation prompts**
   - Before using high-confidence lessons, prompt: "Is this still accurate?"
   - Agent updates confidence based on response
   - Design support: `update_lesson()` already supports confidence changes

3. **Confidence audit mode**
   - CLI command: `ai-lessons audit --confidence high --source inferred`
   - Review lessons matching criteria
   - Design support: all fields are queryable, source/confidence are separate

4. **Counter-evidence linking**
   - When a lesson proves wrong, link to new lesson with `contradicts` relation
   - Original stays (for history) but graph shows contradiction
   - Design support: edges table with flexible `relation` field

---

### 4.2 Tag Sprawl / Inconsistency

**Failure mode:** Tags become a mess of typos, synonyms, and inconsistent naming.

**Current design accommodations:**
- `tag_aliases` in config.yaml for automatic resolution
- `tag_relations` table for synonym/hierarchy relationships
- Tags stored normalized (lowercase, trimmed)
- CLI warns on unknown tags

**Future workarounds:**

1. **Periodic normalization**
   - `ai-lessons tags --review` shows all tags with counts
   - `ai-lessons tags --merge "javascript" "js"` consolidates
   - Design support: tag_relations table, merge function in core

2. **Semantic tag deduplication**
   - Embed tags themselves, cluster similar ones
   - Suggest merges: "These tags seem related: js, javascript, node"
   - Design support: can add tag_embeddings table, same embedding infrastructure

3. **Hierarchical tags**
   - `api.jira`, `api.github` with automatic parent matching
   - Search for `api` finds all children
   - Design support: tag_relations with `child_of` relation, query can traverse

---

### 4.3 Context Over/Under-Specificity

**Failure mode:** Contexts too specific ("updating HSP workflow on Tuesday") or too general ("programming") reduce usefulness.

**Current design accommodations:**
- Contexts stored as free-form strings (flexible)
- `applies` boolean distinguishes context vs anti-context
- Separate from tags (different semantic purpose)

**Future workarounds:**

1. **Context hierarchy**
   - Similar to tags: `team.shared-branch` implies `team`
   - Design support: can add context_relations table mirroring tag_relations

2. **Context suggestions**
   - When adding lesson, suggest contexts from similar lessons
   - "Lessons with similar tags use these contexts: ..."
   - Design support: search + metadata already enables this

3. **Promote contexts to graph nodes**
   - Full relationship modeling between contexts
   - Migration path documented in PLANNING.md
   - Design support: separate table makes migration straightforward

---

### 4.4 Semantic Search Inadequacy

**Failure mode:** Vector search misses relevant lessons or returns irrelevant ones.

**Current design accommodations:**
- Raw content stored alongside embeddings (not lossy)
- Hybrid search combines semantic + keyword
- Tag filtering narrows search space before vector comparison
- Configurable weights for hybrid search

**Future workarounds:**

1. **Adjust hybrid weights**
   - Config-driven, no code changes: `hybrid_weight_semantic: 0.5`
   - Design support: weights in config.yaml

2. **Query expansion**
   - Use LLM to generate related terms before search
   - "workflow error" → also search "transition failure", "status issue"
   - Design support: recall() can accept expanded terms, no schema change

3. **Different embedding model**
   - Swap sentence-transformers for OpenAI or code-specific model
   - Design support: embedding model in config, reembed_all() function exists

4. **Re-ranking with LLM**
   - Vector search returns top-20, LLM re-ranks to top-5
   - Design support: recall() returns scores, caller can re-rank

---

### 4.5 Source Type Insufficiency

**Failure mode:** Predefined source types don't capture new evidence patterns.

**Current design accommodations:**
- Reference table, not CHECK constraint (mutable)
- CLI auto-creates unknown sources with review flag
- `source_notes` captures nuance beyond type

**Future workarounds:**

1. **Dynamic creation**
   - Already supported: unknown source → prompt to create or suggest similar
   - Design support: _suggest_similar() function, reference table INSERT

2. **Source hierarchy**
   - "tested.unit" vs "tested.integration" vs "tested.manual"
   - Design support: can add parent column to source_types, or use naming convention

3. **Deprecate sources**
   - Mark sources as deprecated without breaking existing lessons
   - Design support: add `deprecated` boolean to source_types table

---

### 4.6 Scale Degradation

**Failure mode:** Thousands of lessons slow down search/traversal.

**Current design accommodations:**
- SQLite handles thousands of rows efficiently
- Indexes on common query paths (tags, timestamps, edges)
- Vector search is O(n) but fast for thousands

**Future workarounds:**

1. **Archive old lessons**
   - Move lessons older than X years to archive table
   - Still searchable with `--include-archived` flag
   - Design support: timestamps exist, can add `archived` boolean

2. **Partition by domain**
   - Separate databases per major tag domain (work, personal, project-X)
   - CLI/MCP searches across or within
   - Design support: single-file DB makes partitioning straightforward

3. **Approximate nearest neighbors**
   - Replace exact vector search with ANN (FAISS, Annoy)
   - Design support: embedding interface is abstracted, can swap implementation

---

### 4.7 Cross-Agent Inconsistency

**Failure mode:** Different agents (Claude, Gemini) create lessons with different styles, making search unreliable.

**Current design accommodations:**
- Same tools for all agents (no special-casing)
- Structured fields (confidence, source) enforce some consistency
- Tags and contexts are shared vocabulary

**Future workarounds:**

1. **Agent tagging**
   - Auto-add `agent:claude` or `agent:gemini` tag
   - Filter or weight by agent if needed
   - Design support: tags are free-form, no schema change

2. **Style guide in prompts**
   - MCP tool descriptions include formatting guidance
   - "Title should be imperative, content should explain why"
   - Design support: tool descriptions are editable

3. **Normalization on ingest**
   - Core library reformats content (title case, bullet points, etc.)
   - Design support: add_lesson() can preprocess before storing

---

### 4.8 Lesson Staleness

**Failure mode:** Old lessons become outdated but still appear in searches.

**Current design accommodations:**
- `created_at` and `updated_at` timestamps
- Confidence can be lowered over time
- Edges can link to superseding lessons

**Future workarounds:**

1. **Freshness weighting**
   - Recent lessons score higher in search
   - `score = semantic_score * freshness_factor(updated_at)`
   - Design support: timestamps available for scoring

2. **Supersedes relation**
   - Link new lesson to old with `supersedes` edge
   - Search deprioritizes superseded lessons
   - Design support: edges table with flexible relation

3. **Review queue**
   - `ai-lessons review --stale-days 365` surfaces old lessons for validation
   - Design support: timestamp queries already work

---

### 4.9 Graph Edge Chaos

**Failure mode:** Edges become meaningless spaghetti with inconsistent relation types.

**Current design accommodations:**
- `relation` field is free-form but core library can validate
- Edges are optional (lessons work without them)
- Bidirectional traversal supported

**Future workarounds:**

1. **Relation type reference table**
   - Like source_types: predefined relations with descriptions
   - Design support: can add `relation_types` table, FK on edges.relation

2. **Edge visualization**
   - Export graph to DOT/GraphML for visualization
   - Spot orphans, clusters, suspicious patterns
   - Design support: edges table is simple to export

3. **Prune weak edges**
   - `ai-lessons graph --prune --min-traversals 0` removes unused edges
   - Design support: can add `traversal_count` to edges table

---

### 4.10 Privacy Leaks

**Failure mode:** Sensitive information (API keys, client names) gets exposed through export or sync.

**Current design accommodations:**
- DB is local-only by default
- Tags can mark sensitivity (`sensitive`, `pii`, `internal`)
- Export can filter by tags

**Future workarounds:**

1. **Sensitive tag filtering**
   - `ai-lessons export --exclude-tags sensitive,pii`
   - Design support: tag filtering already in export

2. **Encryption at rest**
   - SQLite encryption extension (SQLCipher)
   - Design support: single-file DB, drop-in replacement

3. **Redaction on export**
   - Scan content for patterns (API keys, emails), redact before export
   - Design support: export goes through core library, can add preprocessing

---

## 5. Extension Points

### 5.1 Adding New Reference Tables

Pattern for any new enum-like field:

```sql
-- 1. Create reference table
CREATE TABLE priority_levels (
    name TEXT PRIMARY KEY,
    ordinal INTEGER,
    description TEXT
);

-- 2. Add column to lessons (nullable for migration)
ALTER TABLE lessons ADD COLUMN priority TEXT REFERENCES priority_levels(name);

-- 3. Update schema version
UPDATE meta SET value = '2' WHERE key = 'schema_version';
```

### 5.2 Adding New Edge Types

No schema change needed; just use new relation strings:

```python
link_lessons(lesson_a, lesson_b, "contradicts")
link_lessons(lesson_a, lesson_b, "supersedes")
link_lessons(lesson_a, lesson_b, "example_of")
```

To enforce valid relations, add `relation_types` reference table.

### 5.3 Custom Search Strategies

Core library supports strategy injection:

```python
def recall(query, strategy="hybrid", **filters):
    if strategy == "hybrid":
        return hybrid_search(query, **filters)
    elif strategy == "semantic":
        return vector_search(query, **filters)
    elif strategy == "keyword":
        return keyword_search(query, **filters)
    elif strategy == "graph":
        return graph_walk(query, **filters)
```

### 5.4 Alternative Embedding Models

Config-driven model selection:

```yaml
embedding:
  backend: sentence-transformers  # or: openai, cohere, local-llm
  model: all-MiniLM-L6-v2
  dimensions: 384
```

Core library loads appropriate backend:

```python
def get_embedder():
    config = load_config()
    if config.embedding.backend == "sentence-transformers":
        return SentenceTransformerEmbedder(config.embedding.model)
    elif config.embedding.backend == "openai":
        return OpenAIEmbedder(config.embedding.model)
```

---

## 6. Testing Strategy

### 6.1 Unit Tests

- Core library functions in isolation
- Mock database for speed
- Test edge cases (empty results, invalid input, reference mismatches)

### 6.2 Integration Tests

- Full flow: add → search → update → delete
- MCP server with mock client
- CLI with captured stdin/stdout

### 6.3 Property-Based Tests

- Fuzzy inputs to search
- Random tag combinations
- Graph traversal depth limits

### 6.4 Migration Tests

- Schema upgrades from each version
- Data preservation verification

---

## 7. Deployment Checklist

### Initial Setup

1. Create `~/.ai/lessons/` directory
2. Initialize SQLite database with schema
3. Seed reference tables (confidence_levels, source_types)
4. Create default config.yaml
5. Build initial (empty) vector index
6. Symlink CLI to PATH
7. Register MCP server with Claude Code

### Verification

```bash
# Check CLI
ai-lessons stats
ai-lessons tags
ai-lessons sources

# Check MCP (via Claude)
"List my tags using the ai-lessons MCP"

# Add test lesson
ai-lessons add --title "Test lesson" --content "Testing" --tags test --confidence low --source tested

# Verify search
ai-lessons search "test"

# Clean up
ai-lessons delete <lesson_id>
```

---

## 8. Glossary

| Term | Definition |
|------|------------|
| **Lesson** | A discrete piece of knowledge with title, content, and metadata |
| **Tag** | Free-form label for categorization |
| **Context** | Situation where a lesson applies (or doesn't) |
| **Edge** | Directional relationship between two lessons |
| **Relation** | Type of edge (e.g., "related_to", "contradicts") |
| **Source** | How knowledge was obtained (tested, inferred, etc.) |
| **Confidence** | Subjective certainty level (low, medium, high) |
| **Recall** | Searching for relevant lessons |
| **Hybrid search** | Combining semantic and keyword search |
