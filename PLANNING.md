# AI Memory System - Planning Document

This document captures all decisions, alternatives considered, and rationale from the initial design discussions.

---

## 1. Problem Statement

### Core Need
Create a system where AI agents (Claude, Gemini, custom CLI agents) can:
1. Save things they learn through debugging/problem-solving
2. Retrieve relevant knowledge in future sessions
3. Build connections between related concepts over time

### Trigger Conditions
An AI should save knowledge when:
- It didn't know how to solve a task initially
- It tried something and got an unexpected result
- It had to debug/iterate to find a solution

**Rationale**: These are the moments where hard-won knowledge is generated. Capturing them prevents re-learning the same lessons.

---

## 2. Storage Location

### Decision: `~/.ai/`

### Alternatives Considered
| Option | Pros | Cons |
|--------|------|------|
| `~/.claude/lessons/` | Fits existing Claude structure | Claude-specific, other agents excluded |
| `~/.ai/lessons/` | Generic, multi-agent | New top-level directory |
| Per-project `.ai/` | Project-scoped | Lessons not shared across projects |

**Rationale**: The system must work with multiple AI tools (Claude Code, custom CLI agent, Gemini). A generic `~/.ai/` location is tool-agnostic and allows all agents to share the same knowledge base.

### Project Scope Handling
- NOT a dedicated `project` attribute
- Projects are just another tag: `project:ai-lessons`, `project:jira-tools`

**Rationale**: `project` is an arbitrary scope. Other contexts (client, domain, language) are equally important. Hardcoding `project` as a first-class attribute creates artificial hierarchy. Tags are flexible enough for all contexts.

---

## 3. Data Structure: Hierarchy vs Tags vs Graph

### Decision: Tag-based with graph edges (no directory hierarchy)

### Alternatives Considered

#### Option A: Directory-based hierarchy
```
~/.ai/lessons/
├── jira/
│   └── workflows/
│       └── update-gotcha.md
├── python/
│   └── debugging/
```

**Discarded because**: Same knowledge often belongs in multiple places. "Jira API rate limiting" is both a Jira lesson and an API patterns lesson. Directories force single-parent hierarchy.

#### Option B: Flat files with frontmatter tags
```yaml
---
tags: [jira, api, gotcha]
---
Content here...
```

**Considered viable but**: Requires file parsing, harder to query, no relationship modeling.

#### Option C: Database with tags + graph edges
```
Lessons stored in DB with:
- Multiple tags (no hierarchy constraint)
- Edges to related lessons
- Semantic embeddings for search
```

**Rationale**: Tags provide the flexible categorization of a "web/mesh of interconnected nodes" that the user explicitly wanted. Graph edges model relationships between concepts. Neither imposes artificial hierarchy.

---

## 4. Database Selection

### Decision: SQLite with sqlite-vec extension

### Alternatives Considered

| Database | Pros | Cons | Verdict |
|----------|------|------|---------|
| **ChromaDB** | We know it, easy vector search, metadata filtering | Separate directory, Python-only, version issues | Viable but less portable |
| **SQLite + sqlite-vec** | Single file, portable, SQL power, vector search via extension | Newer vector support, more DIY | **Selected** |
| **LanceDB** | Single file, native vectors, fast, modern | Newer ecosystem, less mature | Strong alternative |
| **Postgres + pgvector** | Production-grade, SQL + vectors | Overkill for local, needs server | Over-engineered |
| **Neo4j** | True graph DB, excellent traversal | Heavy, separate server, learning curve | Too heavy |
| **Memgraph** | Lighter graph DB, vector support | Still needs server process | Too heavy |

**Rationale**:
1. **Single file** is critical - syncs with dotfiles, portable across machines
2. **<2-3GB RAM** constraint eliminates server-based solutions
3. SQLite is rock-solid, universally available, and sqlite-vec adds vector capabilities
4. The edges table provides "graph-like" traversal without graph DB overhead
5. If we outgrow it, the schema maps cleanly to a "real" graph DB later

---

## 5. Graph Capabilities: Why and How

### Decision: Graph-like edges in SQLite, not a dedicated graph DB

### What Graph DBs Actually Solve

Traditional DBs treat relationships as afterthoughts:
```sql
-- "What's related to this lesson?"
SELECT * FROM lessons WHERE id IN (
  SELECT related_id FROM relations WHERE lesson_id = 123
)
-- Multi-hop gets ugly fast
```

Graph DBs make relationships first-class:
```cypher
-- Same query, natural
MATCH (l:Lesson {id: 123})-[:RELATED_TO]->(related) RETURN related

-- Multi-hop is trivial
MATCH (l:Lesson {id: 123})-[:RELATED_TO*1..3]->(related) RETURN related
```

### Use Cases for Graph Traversal

| Need | Why Graph Helps |
|------|-----------------|
| "What's related to X?" | Direct edge traversal |
| "How does A connect to B?" | Path finding |
| "Show me the cluster around X" | Subgraph extraction |
| "Concepts bridging two domains" | Centrality analysis |

### Example: Why Edges Matter

Three lessons:
1. "Jira workflow updates delete missing statuses" (tags: jira, api, destructive)
2. "Always fetch before update to avoid data loss" (tags: pattern, api, safety)
3. "PUT vs PATCH semantics in REST" (tags: rest, api, concepts)

In pure vector search: 1↔2 might be close, but 2↔3 might be far apart semantically despite being deeply related *conceptually*.

With edges:
```
[Workflow gotcha] --learned_from--> [Fetch before update pattern]
                                            |
                                    --instance_of-->
                                            |
                                    [PUT vs PATCH semantics]
```

**Rationale**: Vector search finds "similar" content. Graph traversal finds "connected" concepts. Both are valuable. SQLite with an edges table gives us graph-like traversal (recursive CTEs) without the overhead of a graph DB server.

---

## 6. Vector Search: Hybrid Approach

### Decision: Vector search + keyword search + tag filtering

### The Problem with Pure Vector Search

Embeddings place text in semantic space where "similar" is relative to model training. Issues:
- Model may not understand *your* conceptual relationships
- Varied data can dilute embedding quality
- Exact matches sometimes better than semantic similarity

### Solutions Implemented/Planned

| Strategy | Implementation | Purpose |
|----------|---------------|---------|
| **Tag filtering first** | `WHERE tag IN (...)` before vector search | Narrow to relevant domain |
| **Hybrid retrieval** | BM25 keyword + vector similarity | Best of both worlds |
| **Focused chunks** | Each lesson = one concept | Better embeddings than 29k char docs |
| **Query expansion** | LLM suggests related terms | Broader recall |
| **Re-ranking** | LLM re-ranks top N results | Higher precision |

**Rationale**: The Jira API search taught us that pure semantic search often misses exact matches. Hybrid retrieval (what production RAG systems use) combines keyword exactness with semantic understanding.

### Does Varied Data Hurt Vector Quality?

**Yes, but manageable at our scale because:**
1. Each lesson is focused (not a massive API doc)
2. Single author = consistent voice/framing
3. Tags provide natural segmentation
4. Hundreds of entries, not millions

**Rationale**: Google solves varied data with scale, query understanding, multiple signals, and learned ranking. We solve it with focused content, good tagging, and hybrid search.

---

## 7. Tag Management

### Decision: Free-form tags with normalization tooling

### The Consistency Problem

Without controls, you get: `project` vs `projects` vs `proj`

### Approaches Considered

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| **Controlled vocabulary** | Strict consistency | Inflexible, requires upfront design | Partial use |
| **Tag aliases in config** | Handles variations | Reactive, not preventive | **Yes** |
| **Tag hierarchy** | Organized taxonomy | Still somewhat rigid | Optional |
| **Free-form + normalization** | Maximum flexibility | Requires periodic cleanup | **Yes** |
| **Tags as graph nodes** | Full relationship modeling | More complex | Future option |
| **Semantic tag deduplication** | Auto-groups similar tags | Magic but opaque | Future option |

### Chosen Approach
```yaml
# ~/.ai/config.yaml
known_tags:
  - jira
  - api
  - python
  - gotcha
  - pattern

tag_aliases:
  projects: project
  proj: project
  javascript: js
```

- Accept any tags (flexible)
- Warn on unknown tags (awareness)
- Auto-resolve aliases (consistency)
- Periodic review: "show all tags" → merge similar ones

**Rationale**: Strict vocabularies fail because you can't predict all future needs. Free-form with normalization gives flexibility while maintaining discoverability.

### Tags vs Types

Originally considered separate `type` field. Decided against.

**Rationale**: "Type" is just another tag. `type:gotcha` vs a dedicated type field - no meaningful difference, and tags are more flexible.

---

## 8. Confidence, Source, and Context

### The Problem

Not all knowledge is equal:
- "git push -f deletes history" is true, but context-dependent (fine on personal branch, dangerous on shared branch)
- An AI might infer something from debug logs with high confidence, but the inference could be wrong
- Knowledge from official docs differs from knowledge from trial-and-error

### Decision: Confidence + Source + Context fields

#### Confidence Level

**Values:** `very-low`, `low`, `medium`, `high`, `very-high` (no "verified")

**Rationale**: "Verified" sounds objective but isn't - someone can confidently "verify" a wrong conclusion. Confidence is always subjective, so the vocabulary should reflect that.

#### Source Type

| Source | Meaning | Typical Confidence |
|--------|---------|-------------------|
| `documented` | Official docs, specs | Medium-High (but may be outdated) |
| `tested` | Ran code, verified behavior | High |
| `observed` | Saw in logs/output | Medium (correlation ≠ causation) |
| `inferred` | Reasoned from evidence | Low-Medium (reasoning may be flawed) |
| `hearsay` | Someone said so | Low (unless verified independently) |

**Rationale**: Confidence level means nothing without knowing the source. A "high confidence" inference from misread logs is worse than a "medium confidence" tested result.

#### Source Notes

Free-form text explaining the source in detail.

**Example**: `"Accidentally deleted teammate's commits on project X, had to recover from reflog"`

#### Contexts and Anti-Contexts

**Contexts:** When does this lesson apply?
**Anti-contexts:** When does this lesson NOT apply?

**Example for "git push -f is dangerous":**
```yaml
contexts:
  - "shared team branch"
  - "after rebase"
  - "CI/CD pipelines watching branch"
anti_contexts:
  - "personal feature branch"
  - "solo project"
```

**Rationale**: Same knowledge can be helpful or harmful depending on situation. Capturing context prevents misapplication.

---

## 9. Schema Design

### Decision: Relational tables with edges + vector extension

```sql
-- Reference tables for enum-like fields
CREATE TABLE confidence_levels (
    name TEXT PRIMARY KEY,
    ordinal INTEGER  -- For sorting: 1-5
);
INSERT INTO confidence_levels VALUES
    ('very-low', 1),
    ('low', 2),
    ('medium', 3),
    ('high', 4),
    ('very-high', 5);

CREATE TABLE source_types (
    name TEXT PRIMARY KEY,
    description TEXT,
    typical_confidence TEXT  -- Hint, not enforcement
);
INSERT INTO source_types VALUES
    ('inferred', 'Reasoned from evidence', 'low-medium'),
    ('tested', 'Ran code, verified behavior', 'high'),
    ('documented', 'Official docs/specs', 'medium-high'),
    ('observed', 'Saw in logs/output', 'medium'),
    ('hearsay', 'Someone said so', 'low');

-- Core content
CREATE TABLE lessons (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,                               -- Keyword searchable
    content TEXT NOT NULL,                             -- Semantic search
    confidence TEXT REFERENCES confidence_levels(name),-- very-low to very-high
    source TEXT REFERENCES source_types(name),         -- How we know this
    source_notes TEXT,                                 -- Optional elaboration
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Tags (many-to-many, no constraints on values)
CREATE TABLE lesson_tags (
    lesson_id TEXT REFERENCES lessons(id),
    tag TEXT NOT NULL,
    PRIMARY KEY (lesson_id, tag)
);

-- Contexts (when does this lesson apply/not apply?)
CREATE TABLE lesson_contexts (
    lesson_id TEXT REFERENCES lessons(id),
    context TEXT NOT NULL,
    applies BOOLEAN DEFAULT TRUE,  -- TRUE = applies, FALSE = anti-context
    PRIMARY KEY (lesson_id, context, applies)
);

-- Graph edges between lessons
CREATE TABLE edges (
    from_id TEXT REFERENCES lessons(id),
    to_id TEXT REFERENCES lessons(id),
    relation TEXT NOT NULL,        -- "related_to", "derived_from", "contradicts"
    PRIMARY KEY (from_id, to_id, relation)
);

-- Tag relationships (aliases, hierarchy)
CREATE TABLE tag_relations (
    from_tag TEXT,
    to_tag TEXT,
    relation TEXT,                 -- "alias_of", "child_of", "related_to"
    PRIMARY KEY (from_tag, to_tag, relation)
);

-- Vector embeddings
CREATE VIRTUAL TABLE lesson_embeddings USING vec0(
    lesson_id TEXT PRIMARY KEY,
    embedding FLOAT[384]
);
```

**Rationale**:
- Separate tags table allows unlimited tags per lesson
- Edges table enables graph traversal via recursive CTEs
- Tag relations support aliases and optional hierarchy
- Vec0 virtual table integrates vector search into SQL queries

### Reference Tables vs CHECK Constraints

For enum-like fields (confidence, source), we use reference tables instead of CHECK constraints:

```sql
-- Reference tables (data, not schema)
CREATE TABLE confidence_levels (
    name TEXT PRIMARY KEY,
    ordinal INTEGER  -- For sorting: 1-5
);

CREATE TABLE source_types (
    name TEXT PRIMARY KEY,
    description TEXT,
    typical_confidence TEXT  -- Hint, not enforcement
);

-- Lessons reference them via FK
source TEXT REFERENCES source_types(name),
confidence TEXT REFERENCES confidence_levels(name),
```

**Tradeoffs:**

| | CHECK Constraint | Reference Table |
|---|------------------|-----------------|
| Add new value | Schema change (table rebuild in SQLite) | `INSERT` |
| Query valid values | Parse schema or hardcode | `SELECT * FROM source_types` |
| Store metadata (descriptions) | Not possible | Natural |
| Enforce validity | Always (DB level) | FK = strict, no FK = loose |
| Extra complexity | None | One more table, optional JOINs |
| Typo risk | None (rejected) | With FK = none, without FK = possible |
| Startup/migration | None | Must seed reference data |

**Decision:** Use FK-backed reference tables for `source_types` and `confidence_levels` (small, stable sets where consistency matters). Skip FK for free-form things like tags.

**Rationale:** Reference tables turn schema into data. Data is easy to change; schema is not. Adding a new source type becomes `INSERT INTO source_types VALUES (...)` rather than a migration.

### Handling Unknown Values at Runtime

The MCP/CLI interface handles unknown reference values gracefully:

**Interactive mode:**
```
User: learn --source "trial-and-error" ...

CLI: "trial-and-error" not found. Did you mean:
     - "tested" (Ran code, verified behavior)
     - "observed" (Saw in logs/output)
     Or create new? [t/o/new]: new

CLI: Creating source type "trial-and-error"
     Description: <user provides or AI generates>
     Typical confidence: <optional>
```

**Non-interactive mode (AI agents):**
- Accept the new value, auto-create the reference entry
- Flag for periodic review/consolidation
- Or: require exact matches, return error with suggestions

**Periodic cleanup:**
- `ai-lessons sources --review` shows all source types with usage counts
- Merge similar entries: `ai-lessons sources --merge "trial-and-error" "tested"`
- Same pattern works for any reference table

**Rationale:** The interface layer abstracts away the FK complexity. Users/agents don't need to know about reference tables - they just use values, and the system handles consistency.

---

## 10. Query Patterns

### Semantic Search with Tag Filter
```sql
SELECT l.* FROM lessons l
JOIN lesson_tags lt ON l.id = lt.lesson_id
JOIN lesson_embeddings le ON l.id = le.lesson_id
WHERE lt.tag IN ('jira', 'api')
ORDER BY vec_distance(le.embedding, ?)
LIMIT 10;
```

**Rationale**: Filter by tags first (fast), then rank by semantic similarity (accurate).

### Graph Traversal (N-hop related lessons)
```sql
WITH RECURSIVE related AS (
    SELECT to_id, 1 as depth FROM edges WHERE from_id = ?
    UNION
    SELECT e.to_id, r.depth + 1
    FROM edges e JOIN related r ON e.from_id = r.to_id
    WHERE r.depth < 2
)
SELECT * FROM lessons WHERE id IN (SELECT to_id FROM related);
```

**Rationale**: Recursive CTE gives us graph-like traversal without a graph DB.

### Tag Statistics
```sql
SELECT tag, COUNT(*) as count
FROM lesson_tags
GROUP BY tag
ORDER BY count DESC;
```

**Rationale**: Essential for tag management and discovering taxonomy.

---

## 11. Interface Design

### Decision: MCP server + CLI tool (same backend)

### MCP Server Tools
For Claude Code and MCP-compatible agents:
- `learn(title, content, tags[], keywords?)` - Add lesson, auto-embed
- `recall(query, tags?, limit?)` - Hybrid search
- `related(id, depth?)` - Graph traversal
- `link(from_id, to_id, relation)` - Create edge
- `get(id)` - Fetch specific lesson
- `update(id, ...)` - Modify lesson, re-embed
- `delete(id)` - Remove lesson
- `tags()` - List all tags with counts

### CLI Tool
For custom agents, Gemini, direct use:
```bash
ai-lessons add --title "..." --tags jira,api
ai-lessons search "query" --tags jira
ai-lessons related <id>
ai-lessons link <from> <to> --relation derived_from
ai-lessons show <id>
ai-lessons edit <id>
ai-lessons delete <id>
ai-lessons tags
```

**Rationale**: MCP for Claude Code integration. CLI for everything else. Same SQLite backend ensures consistency.

---

## 12. CLAUDE.md Integration

### Decision: Minimal instructions pointing to the system

```markdown
## Learning System

When you discover something non-obvious through debugging:
1. Use `learn` to save it with relevant tags
2. Check `recall` when stuck on similar problems

Use existing tags from `tags()` when possible.
```

**Rationale**: CLAUDE.md is for "immediate instructions all Claudes need." The learning system is a tool, not a detailed workflow. Keep instructions minimal; the MCP tool descriptions handle specifics.

---

## 13. Embedding Model Choice

### Decision: sentence-transformers (all-MiniLM-L6-v2) initially

### Alternatives
| Model | Pros | Cons |
|-------|------|------|
| all-MiniLM-L6-v2 | Fast, small, free | Generic, not code-optimized |
| CodeBERT | Code-aware | Larger, may not help for prose |
| OpenAI embeddings | High quality | Cost, API dependency |

**Rationale**: Start simple and free. The lessons are mostly prose with some code. Generic model is fine. Can switch later if precision suffers.

---

## 14. When Rebuild is Needed

### No rebuild needed for:
- Adding new entries
- Updating entry content (delete + re-add)
- Changing metadata/tags
- Deleting entries

### Rebuild needed for:
- Changing embedding model
- Major schema changes
- Index corruption

**Rationale**: Unlike the Jira docs (which had chunking complexity), each lesson = one chunk. No re-chunking logic, so updates are atomic.

---

## 15. Future Considerations

### Noted but Not Implemented

1. **Tags as graph nodes** - Full relationship modeling between tags themselves
2. **Semantic tag deduplication** - Embed tags, auto-merge similar ones
3. **Domain-specific embedding models** - Different models for different tag domains
4. **User feedback loop** - Learn from which results user selects
5. **LLM re-ranking** - Use LLM to re-rank top N results for precision
6. **Contexts as graph nodes** - See below

**Rationale**: Start simple. These are optimizations for when/if the simple approach proves insufficient.

### Contexts as Graph Nodes (Future)

Currently, contexts are stored as metadata (strings in a table). A future enhancement could promote contexts to first-class graph nodes:

```
Current:  [Lesson] --has_context--> "shared branch" (string)

Future:   [Lesson] --APPLIES_IN--> [Context: shared branch]
                                           |
                                --SUBSET_OF--> [Context: team environment]
                                           |
                                --IMPLIES--> [Context: requires communication]
```

**When to migrate:**
- If you find yourself wanting context hierarchies ("shared branch" is-subset-of "team environment")
- If you want to query contexts themselves ("what contexts exist?", "what contexts relate to X?")
- If contexts start having their own attributes (risk level, stakeholders, etc.)

**Migration path:**
1. Extract distinct context strings from `lesson_contexts` table
2. Create Context nodes for each
3. Convert string references to node edges
4. Add inter-context relationships as needed

**Rationale for deferring:** Start with metadata. It's simpler and handles "filter lessons by context" well. Promote to nodes only when you need to reason about context relationships themselves.

---

## 16. Operational Constraints

### Resource Limits

**Constraint:** <2-3GB RAM

This ruled out:
- Neo4j, Memgraph (graph DBs requiring server processes)
- Postgres + pgvector (overkill, needs server)
- Heavy embedding models

SQLite + sqlite-vec fits comfortably: ~100MB for extension, embeddings stored on disk.

### Multi-Agent Support

Multiple AI tools share the same knowledge base:
- Claude Code (via MCP server)
- Custom CLI agent (via CLI tool)
- Gemini (via CLI tool)
- Direct human use (via CLI tool)

**Rationale:** Knowledge should be tool-agnostic. A lesson learned in Claude should help Gemini.

### Sync and Portability

- Single SQLite file syncs with dotfiles across machines
- No server process = no port conflicts or startup dependencies
- Config in `~/.ai/config.yaml` also syncs

### Concurrency

SQLite handles concurrent reads well. For writes:
- WAL mode enables concurrent reads during writes
- CLI/MCP should use short transactions
- At expected scale (human-paced learning), conflicts are rare

If conflicts become an issue: add advisory locking or queue writes.

### Backup and Recovery

- Single file = trivial backup (`cp knowledge.db knowledge.db.bak`)
- Git-friendly (can version the DB if desired, though diffs aren't meaningful)
- Catastrophic recovery: re-embed from exported JSON/YAML

### Privacy Considerations

Lessons may contain:
- API keys, passwords (from debug sessions)
- Client names, project details
- Personal notes

**Mitigations:**
- DB stays local (not cloud-synced by default)
- Optional: encrypt sensitive lessons
- Optional: tag `sensitive` for filtering during export
- `.gitignore` the DB if syncing dotfiles publicly

### Performance Expectations

| Scale | Expected Performance |
|-------|---------------------|
| 100 lessons | Instant everything |
| 1,000 lessons | Instant search, fast traversal |
| 10,000 lessons | Sub-second search, may need index tuning |
| 100,000+ lessons | Unlikely to reach; revisit architecture if needed |

**Rationale:** This is personal/team knowledge, not web-scale data. Thousands of lessons is the realistic ceiling.

### Schema Migration

SQLite schema changes are awkward. Strategy:
1. **Add columns:** Easy (`ALTER TABLE ADD COLUMN`)
2. **Rename/remove columns:** Requires table rebuild
3. **Major changes:** Export to JSON, recreate DB, re-import

Store schema version in a `meta` table:
```sql
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
INSERT INTO meta VALUES ('schema_version', '1');
```

CLI/MCP checks version on startup, runs migrations if needed.

---

## 17. Example Workflows

### Learning from Debugging

```bash
# After spending an hour debugging a Jira API issue:

$ ai-lessons add \
  --title "Jira workflow updates delete missing statuses" \
  --content "When calling PUT /rest/api/3/workflows, you must include ALL
             existing statuses and transitions. Any omitted items are deleted,
             not preserved. Always GET the workflow first and merge changes." \
  --tags jira,api,gotcha,destructive \
  --context "updating existing workflows" \
  --anti-context "creating new workflows" \
  --source tested \
  --source-notes "Lost 3 statuses on HSP project, had to recreate manually" \
  --confidence high
```

### Recalling During Similar Task

```bash
# Later, about to update another workflow:

$ ai-lessons search "jira workflow update" --tags api

# Returns:
# 1. [high] Jira workflow updates delete missing statuses
#    Context: updating existing workflows
#    Source: tested
#    "When calling PUT /rest/api/3/workflows..."

# AI now knows to GET first, then merge
```

### MCP Server Flow

```
Claude: I need to update this Jira workflow...

[Claude calls MCP recall tool: "jira workflow update"]

MCP returns: Found 1 relevant lesson:
  - "Jira workflow updates delete missing statuses" (confidence: high)
  - Context: updating existing workflows
  - Warning: Always GET workflow first and merge changes

Claude: I'll fetch the existing workflow before making changes...
```

---

## 18. Connection to Goal-Tracking Project

A separate project tracks:
- Project state over time
- Goal states (even simple ones like "prints text right-to-left")
- How each change moves toward/away from goals
- Derived rules: "if goal X and state Y, then do Z not W"

**Relationship to ai-lessons:**
- Goal-tracking is more structured (state machines, causal graphs)
- ai-lessons is more free-form (prose lessons, tagged knowledge)
- Goal-tracking could *feed into* ai-lessons: "I learned X because experiment Y showed change Z improved goal W"
- But ai-lessons doesn't implement goal-tracking itself

**Possible integration:**
```sql
-- Optional field linking lesson to an experiment
CREATE TABLE lessons (
    ...
    derived_from_experiment TEXT,  -- Reference to goal-tracking system
    ...
);
```

**Rationale:** Keep ai-lessons focused on knowledge storage/retrieval. Goal-tracking is a separate system with different data models. They can reference each other without tight coupling.

### Rationale as a Bridge (Future)

Rationale can be framed as: **rule** + (**desired state** || **value**)

- Desired state and value are arguably equivalent (e.g., "honesty" as a value = "desired state of alignment with principles")
- Rationale describes *why* a rule exists relative to goals/values

**Where rationale fits:**
- ai-lessons captures **lessons** (facts, observations, gotchas)
- State-tracking captures **changes** and their **impact on goals**
- Rationale would **caption the link** between a lesson and the state change(s) that produced it

**Example:**
```
Lesson: "Workflow updates delete missing statuses"
    ↑
    | rationale: "Discovered while pursuing goal 'reliable workflow updates';
    |             state change 'removed status X from payload' caused
    |             unintended deletion, violating goal"
    ↓
State Change: { removed: "status X", result: "status deleted from workflow" }
```

**Decision:** Defer rationale to the integration point between ai-lessons and state-tracking. When combined:
- ai-lessons is the "dumping ground" for lessons learned from reviewing the state-change graph
- Rationale provides the causal narrative linking lessons to state changes
- This keeps ai-lessons simple now while leaving room for richer integration later

---

## 19. File Structure

```
~/.ai/                        # Shared AI tools directory
├── lessons/                  # This project (ai-lessons)
│   ├── knowledge.db          # SQLite: lessons, tags, edges, embeddings
│   ├── config.yaml           # Tag aliases, settings
│   └── mcp-server/
│       ├── server.py
│       └── requirements.txt
├── <other-project>/          # Future AI tools live alongside
└── ...

~/bin/ (or ~/.local/bin/)     # CLI tools on PATH
└── ai-lessons                # Symlink or wrapper to ai-lessons CLI
```

**Rationale**:
- `~/.ai/` is a shared namespace for AI-related tools, not just ai-lessons
- Each project gets its own subdirectory
- CLI tools go on PATH for easy access (symlinked from project dir)
- Keeps ai-lessons self-contained while allowing expansion

---

## Appendix: Key Insights from Jira MCP Server

Building the Jira API search taught us:

1. **Lightweight search results** - Return summaries, not full content. Let agent fetch what it needs.
2. **Deterministic lookups alongside semantic** - `get_chunk(id)` for exact retrieval.
3. **Hybrid retrieval** - Pure semantic search misses exact matches.
4. **Summaries help but don't capture gotchas** - Haiku summarizes docs, but experiential knowledge must be added manually.
5. **Focused chunks embed better** - 29k char docs = diluted embeddings.

These lessons directly informed the ai-lessons architecture.
