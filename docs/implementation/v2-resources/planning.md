# AI Lessons v2 - Resources Planning Discussion

This document captures the complete design discussion for adding a resources system to ai-lessons, including all considered options, discarded approaches, and decision rationale.

## Context

v2 extends ai-lessons to support **resources** (docs and scripts) alongside lessons. This enables the system to replace specialized MCP servers (like jira-docs) with a unified knowledge + reference system.

### Goals

1. Store reference documentation with semantic search
2. Store scripts that implement solutions, linked to lessons
3. Support versioning (e.g., Jira API v2 vs v3)
4. Unify the schema so docs and scripts share structure
5. Enable chunking large documents for efficient retrieval

---

## Decision 1: Resource Types

**Question:** Should docs and scripts be fundamentally different entities or variations of the same thing?

### Options Considered

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. Separate tables | `documents` and `scripts` tables | Clear separation | Duplicated schema, separate search logic |
| B. Unified with type field | Single `resources` table with `type` column | Shared schema, single search | Behavioral differences hidden in code |
| C. Inheritance pattern | Base `resources` table with type-specific extensions | Clean OO model | More complex queries |

### Decision

**Option B - Unified with type field**

### Rationale

Docs and scripts share 90% of their structure (title, content, path, versions, embeddings). The only differences are:
- Source of truth (DB vs filesystem)
- Refresh behavior (explicit vs lazy)
- Executability

These behavioral differences are better handled in application code than schema design. A single `resources` table simplifies search and avoids duplication.

---

## Decision 2: Source of Truth

**Question:** Where does the canonical content live - database or filesystem?

### Context

- Scripts need to be editable with normal tools (vim, IDE)
- Scripts need to be executable
- The edit → debug → fix cycle shouldn't require database operations
- Docs are more static but may need updates

### Options Considered

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. Always DB | Store all content as blobs | Single source of truth, portable | Scripts hard to edit/run |
| B. Always filesystem | Store paths, read on demand | Easy to edit | No portability, search requires re-reading |
| C. Hybrid by type | Docs in DB, scripts in filesystem | Best of both | Two mental models |
| D. Hybrid with caching | Filesystem is truth, DB caches for search | Single source, searchable | Sync complexity |

### Decision

**Option C - Hybrid by type**

### Rationale

- **Docs** are reference material - they don't change often, and when they do, it's intentional. Snapshot storage in DB makes sense.
- **Scripts** are living artifacts - they evolve during debugging, need normal tooling. Filesystem as source of truth, DB caches content for search with lazy re-indexing.

### Discarded: Always-Blob Storage for Scripts (Option A)

**Idea:** Store scripts as blobs like docs, with extract/edit/reattach workflow.

**Rationale for rejection:** High friction for the debug cycle. Scripts are living artifacts that need normal tooling. The reattach step would frequently be missed, causing sync drift.

### Discarded: Hybrid with Caching (Option D)

**Idea:** Filesystem is always truth, DB caches everything.

**Rationale for rejection:** For docs, we actually want DB to be the source of truth to avoid the branch-switching problem (see Decision 6). Different content types have different lifecycles.

---

## Decision 3: Versioning Model

**Question:** How should we handle versioned resources (e.g., Jira API v2 vs v3)?

### Context

- Same API/project may have multiple versions
- A single script might work across multiple versions
- User may want to search within a specific version
- "Unversioned" is a valid state (not everything has versions)

### Options Considered

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. Single version field | `version VARCHAR` on resources | Simple | Can't represent multi-version resources |
| B. Version in path only | Derive from filesystem path | No schema change | Parsing complexity, not explicit |
| C. Version as list/array | `versions JSON` field | Flexible | JSON queries are awkward in SQLite |
| D. Many-to-many table | `resource_versions` join table | Proper relational model | Extra table, joins |

### Decision

**Option D - Many-to-many table**

### Rationale

- A script that uses both v2 and v3 APIs shouldn't require duplication
- Join table allows proper set operations (intersection, superset, etc.)
- Matches existing pattern (`lesson_tags`, `lesson_contexts`)
- SQLite handles joins efficiently for this scale

### Discarded: Derive Version from Filesystem Path (Option B)

**Idea:** Parse `/v3/` from path to determine version automatically.

**Rationale for rejection:** Too fragile. Paths aren't always structured predictably. Explicit version specification is more reliable.

### Discarded: Single Version Field with Comma-Separated Values

**Idea:** `version VARCHAR` containing `"v2,v3"`.

**Rationale for rejection:** Violates 1NF, makes queries awkward. Proper many-to-many is cleaner.

---

## Decision 4: Version Matching in Search

**Question:** When user specifies `--version v2 --version v3`, how should resources be matched and ranked?

### Options Considered

| Option | Description |
|--------|-------------|
| A. Exact match only | Resource must have exactly the specified versions |
| B. Superset match | Resource must have at least the specified versions |
| C. Any overlap | Resource matches if any version overlaps |
| D. Scored matching | All overlaps match, but ranked by match quality |

### Decision

**Option D - Scored matching**

### Rationale

Strict matching would exclude potentially useful resources. A v3-only script might still help when working on v2+v3, just with caveats. Scoring surfaces the best matches while not hiding partial matches.

### Discarded: Exact Match Only (Option A)

**Idea:** Only return resources that have exactly the specified versions.

**Rationale for rejection:** Too restrictive. A `[v2, v3, v4]` resource is still relevant when searching for `v2, v3`. Would require users to know exact version sets.

### Discarded: Superset Match Only (Option B)

**Idea:** Resource must have ALL specified versions (but can have more).

**Rationale for rejection:** Would exclude subset matches. A `[v3]` script might still be useful when working on `v2, v3` - it just doesn't cover everything.

---

## Decision 5: Unversioned Resource Handling

**Question:** How should resources without version information be represented and searched?

### Options Considered

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. NULL version | Use `NULL` in join table | SQL standard for "no value" | Semantically ambiguous |
| B. Empty set | No rows in `resource_versions` | Clean absence | Harder to query |
| C. Literal "unversioned" | Store string `"unversioned"` | Explicit, queryable | Not a real version |

### Decision

**Option C - Literal "unversioned" string**

### Rationale

- `NULL` means "unknown/not set" semantically
- `"unversioned"` means "this applies regardless of version" - an explicit state
- Allows queries like `WHERE version = 'unversioned'`
- Clear distinction from "we forgot to set the version"

### Discarded: NULL for Unversioned Resources (Option A)

**Idea:** Use `NULL` in version field for unversioned resources.

**Rationale for rejection:** `NULL` semantically means "unknown/not set." "Unversioned" is an explicit state meaning "this applies regardless of version." Using the literal string is clearer.

---

## Decision 6: Git Reference Tracking

**Question:** Should we track git commit information for resources?

### Context

- Resources may come from git repositories
- Knowing which commit a doc was imported from helps with updates
- Branch switching can silently change file contents

### Options Considered

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. No tracking | Don't store git info | Simple | No provenance |
| B. Manual flag | `--track-git` flag required | User control | Easy to forget |
| C. Auto-capture | Automatically detect and store | No extra effort | Slight overhead |

### Decision

**Option C - Auto-capture git ref on resource add**

### Rationale

This is cheap to capture and valuable for auditing. No user action required - just automatic metadata. When adding a resource from a path:
- Check if path is in a git repo
- If yes, automatically store `source_ref` (e.g., `abc1234`)
- On refresh, optionally warn if current HEAD differs from stored ref

---

## Decision 7: Filesystem Directory Structure

**Question:** How should resources be organized on the filesystem?

### Context

- Users need to find/edit scripts manually sometimes
- If search fails, filesystem serves as fallback for LLM exploration
- Version organization should be intuitive
- Multi-version scripts need a home

### Options Considered

| Option | Structure | Pros | Cons |
|--------|-----------|------|------|
| A. Flat | `~/.ai/reference/{project}/*` | Simple | No version organization |
| B. Version first | `~/.ai/reference/{project}/{version}/*` | Clear versioning | Where do multi-version scripts go? |
| C. Type then version | `~/.ai/reference/{project}/docs/{version}/` | Separates docs/scripts | Deep nesting |
| D. Version for docs, flat for scripts | Docs versioned, scripts at project level | Scripts version in DB only | Inconsistent |
| E. Shared directory | `~/.ai/reference/{project}/{type}/{version,shared}/` | Explicit multi-version | Extra directory |

### Decision

**Option E - Shared directory for multi-version resources**

### Rationale

- `shared/` directory makes multi-version resources explicit on filesystem
- Docs and scripts both support versioning consistently
- `unversioned/` for projects without version tracking
- Filesystem serves as fallback when search fails - having full files in a centralized place aids LLM exploration

### Discarded: Symlinks for Multi-Version Scripts

**Idea:** Store script once, symlink into each version directory.

**Rationale for rejection:** Extra maintenance burden. Symlinks can be missed when adding new versions. Database tracking of versions is more reliable.

### Discarded: Scripts Flat at Project Level (Option D)

**Idea:** Only docs get version subdirectories, scripts live at project level with version only in DB.

**Rationale for rejection:** Inconsistent mental model. If docs have `v2/`, `v3/` directories, scripts should too. The `shared/` directory handles the multi-version case cleanly.

---

## Decision 8: Refresh Behavior

**Question:** How should content be refreshed/re-indexed?

### Options Considered

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. Manual only | User runs reindex command | Full control | Easy to forget, stale data |
| B. Eager/watch | Filesystem watcher auto-reindexes | Always fresh | Complexity, resource usage |
| C. Lazy on access | Check freshness on search, reindex if stale | Fresh when needed | Slight latency on first access |
| D. Scheduled | Cron job reindexes periodically | Predictable | May be stale between runs |

### Decision

**Option C - Lazy on access (for scripts)**

**Explicit refresh (for docs)**

### Rationale

- **Scripts:** Lazy re-indexing fits the "filesystem is source of truth" model. On search/access, check if `mtime > indexed_at`. If stale, re-read and reindex.
- **Docs:** Explicit refresh via `refresh-resource` command. Docs are snapshots - we don't want them changing unexpectedly.

### Discarded: Eager Filesystem Watching (Option B)

**Idea:** Use inotify/fswatch to auto-reindex on file changes.

**Rationale for rejection:** Overkill for this use case. Adds complexity and resource usage. Lazy reindexing achieves freshness without the overhead.

---

## Decision 9: Context Pollution vs Batch Retrieval

**Question:** Should search return full content or lightweight summaries?

### Context

Discussion about token costs led to clarification: the concern is not monetary cost, but **context pollution**. An agent with 200k context window loses effective capacity if 50k is irrelevant search results.

### Options Considered

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. Full content always | Return complete content in search | One round trip | Context pollution |
| B. Summaries + fetch | Lightweight results, explicit fetch for full | Minimal pollution | Extra round trip |
| C. Configurable | Flag to choose full vs summary | Flexibility | Complexity |

### Decision

**Option B - Two-tier retrieval (summaries + fetch)**

### Rationale

For AI agents with limited context windows, avoiding irrelevant content is more valuable than saving a round trip. Search returns:
- ID, score, title, type, versions
- First ~150 chars as snippet
- "Use `get_resource(id)` for full content"

Full content fetched only for items worth reading.

---

## Decision 10: Rules as Separate Entity

**Question:** How should prescriptive knowledge ("always do X") be represented?

### Context

Lessons are objective observations: "If X, then Y happens."
But we also need prescriptive guidance: "Always do X to achieve Y."

The distinction:
- **Lessons**: Objective, describe causality
- **Rules**: Subjective, prescribe desired outcomes with rationale

### Options Considered

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. Rules as tagged lessons | Add `type: rule` to lessons table | Simple, unified | Different required fields, different surfacing |
| B. Separate rules table | Dedicated table for rules | Clean separation, different fields | Another table |
| C. Rules as resources | Treat rules like docs | Unified with resources | Wrong abstraction |

### Decision

**Option B - Separate rules table**

### Rationale

Rules and lessons share emergence from experience but differ fundamentally:
- Lessons are objective (causality), rules are subjective (prescriptions)
- Rules require rationale (why we want this outcome), lessons don't
- Rules surface proactively, lessons surface on search
- Rules need approval workflow, lessons don't

In code, they share a base class/interface but are distinct entities.

---

## Decision 11: Rationale Field

**Question:** Should knowledge items explain "why"?

### Context

Rules need rationale: "Always GET before PUT" → "Because PUT replaces entire resource."
Do lessons also benefit from rationale?

### Decision

- **Rules**: `rationale` required - explains what effect we're prioritizing and why
- **Lessons**: No rationale - lessons are objective observations of causality

### Rationale

Rules are subjective prescriptions - they express desired outcomes based on human values. Rationale captures those values and helps agents make judgment calls in novel situations.

Lessons are objective observations: "If X, then Y happens." They describe causality without subjective judgment. Any "why" for a lesson would itself be another lesson (the cause of the cause), not a rationale expressing human values.

---

## Decision 12: Rule Approval Workflow

**Question:** Should agent-suggested rules require human approval?

### Context

- Lessons are objective observations - an agent saw X happen
- Rules are subjective prescriptions - "always do Y"
- Subjective guidance should require human judgment

### Options Considered

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. Auto-approve | Rules added directly | Fast | Agents may suggest bad rules |
| B. Prompt user | Agent asks human in real-time | Immediate review | Interrupts workflow, sub-agent bubbling |
| C. Approval queue | Rules added with `approved=false` | Non-blocking, batch review | Delay before rule is active |

### Decision

**Option C - Approval queue with `approved` field**

### Rationale

- Agent can suggest rules without blocking workflow
- Human reviews at convenient time (e.g., session start hook)
- Unapproved rules never surface in search
- Clean audit trail of who approved what

Schema addition:
```sql
rules:
  approved BOOLEAN DEFAULT FALSE
  approved_at TIMESTAMP
  approved_by VARCHAR
  suggested_by VARCHAR
```

---

## Decision 13: Tag-Weighted Context Search

**Question:** How should an agent's current context influence search results?

### Context

An agent working as "reviewer" on "jira-api" should see relevant lessons/rules boosted.
MCP is stateless, so context must be passed per-request.

### Options Considered

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. Stateful context | `ai-lessons context set role:reviewer` | Persistent | Doesn't work for MCP |
| B. Per-request tags | `--context-tags reviewer,jira-api` | Stateless, MCP-friendly | Must pass each time |
| C. Tag weights | `--context-tags reviewer=1.5,jira-api` | Fine control | Complex |

### Decision

**Options B + C combined - Per-request with optional weights**

### Rationale

Syntax: `--context-tags "reviewer,jira-api=1.5,testing=1.3"`
- Unweighted tags get default weight (average of explicit weights, or 1.5 if none)
- Works for both CLI and MCP
- Agents can optionally specify importance

---

## Decision 14: Rule Surfacing via Tag Overlap

**Question:** How should rules surface in search results?

### Context

Rules should surface proactively when entering a domain, not just when searched.
But we don't want "API rules" surfacing on every API search.

### Decision

**Rules require contextual overlap to surface:**
```
Rule surfaces IF:
  (semantic_similarity > threshold)
  AND
  (at least one of: tag overlap, project match, direct link)
```

### Rationale

Prevents false positives. A rule about "Jira sandbox" only surfaces when:
- Searching with `jira` tag, OR
- Searching in `jira-api` project, OR
- Result includes a resource directly linked to that rule

---

## Decision 15: Contribution Trigger

**Question:** When should an agent contribute new knowledge?

### Decision

**Iteration = trigger for contribution**

```
IF attempts > 1 OR encountered_errors:
    MUST add lesson (what was learned)
    MUST add script (proof/validation)
    CONSIDER suggesting rule (if generalizable)
```

### Rationale

If an agent succeeded on first try, nothing notable was learned.
If an agent had to iterate/debug, that knowledge is worth capturing.
Scripts are proof - they validate the lesson and help future agents.

---

## Open Questions (Deferred)

### Document Chunking Strategy

**Question:** How should large documents be chunked for search?

**Options to explore:**
- Chunk by markdown headers
- Chunk by line count with overlap
- Chunk by semantic boundaries
- Hybrid approaches

**Status:** Deferred to implementation. Schema supports chunking via `resource_chunks` table.

### Unified Search Default

**Question:** Should `ai-lessons recall search` search BOTH lessons and resources by default?

**Tentative answer:** Yes, with `--type` filter available.

**Status:** To be finalized during implementation.

### Graph Edge Types

**Question:** What relationship types should connect lessons and resources?

**Tentative list:**
- `has_script` - Lesson has implementing script
- `has_doc` - Lesson references documentation
- `derived_from` - Standard lesson relationship
- `related_to` - General relationship

**Status:** To be finalized during implementation.

---

## Timeline

| Date | Discussion |
|------|------------|
| 2024-12 | Initial design discussion |
| 2024-12 | Resource type unification decided |
| 2024-12 | Version matching scoring finalized |
| 2024-12 | Filesystem structure with `shared/` decided |
| TBD | Implementation |
