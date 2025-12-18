# Code Review Report

Generated: 2025-12-17

## Executive Summary

The ai-lessons project is a well-architected knowledge management system with thoughtful design decisions documented in extensive planning materials. The implementation is generally solid with good separation of concerns, but there are several areas where consolidation, DRY violations, and schema/relationship complexity could be improved. The codebase has grown organically through multiple versions (v1-v8 schema) and would benefit from strategic refactoring.

**Codebase Size**: 8,604 lines of Python across 12 modules.

---

## 1. Critical Issues & Architectural Concerns

### 1.1 - Schema Complexity: Excessive Entity Types and Duplication (HIGH PRIORITY)

**Location**: `schema.py` (255 lines), `core.py` (2664 lines)

**Issue**: The system now manages 5 distinct entity types (Lessons, Resources, Chunks, Rules, ResourceLinks) with partially overlapping concerns:

- **Lessons** (v1): Factual observations with tags, contexts, confidence, source
- **Resources** (v2): Docs/scripts with versions and tags
- **ResourceChunks** (v2): Chunks of resources with breadcrumbs, sections
- **Rules** (v2): Prescriptive guidance with rationale and approval workflow
- **ResourceLinks** (v3): Extracted markdown links between resources

**Problem**:
1. Multiple similar operations are duplicated across entity types:
   - Tag handling: `lesson_tags`, `resource_tags`, `rule_tags` (3 separate tables)
   - Search results: `SearchResult` dataclass handles 4 result types with 20+ optional fields
   - Linking: `edges` (lesson→lesson), `lesson_links` (lesson→resource), `resource_links` (resource→resource)

2. **Tag handling duplication** (Lines in core.py):
   - Lessons: Lines 229-230, 248-252, 410-416
   - Resources: Lines 1325-1326, 1354-1358
   - Rules: Lines 1956-1957, 1972-1976

   **Recommendation**: Extract tag normalization/storage to a generic `_save_tags(conn, entity_id, entity_type, tags)` helper function instead of inline SQL in each CRUD operation.

3. **Embedding handling duplication**:
   - Lessons: Lines 232-235, 436-446
   - Resources: Lines 1334-1335, 1361-1364, 1422-1425
   - Chunks: Lines 1075-1091

   **Recommendation**: Create `_embed_and_store(conn, entity_id, entity_type, text, config)` function.

### 1.2 - SearchResult Dataclass Over-Complexity (HIGH PRIORITY)

**Location**: `search.py`, lines 14-56

**Issue**: `SearchResult` is a god object with 25+ fields, many optional, trying to represent 4 different result types:

```python
@dataclass
class SearchResult:
    # Base (for all types)
    id: str
    title: str
    content: str
    score: float
    result_type: str
    tags: list[str]

    # Lesson-specific (5 fields)
    confidence: Optional[str]
    source: Optional[str]
    source_notes: Optional[str]
    contexts: list[str]
    anti_contexts: list[str]

    # Resource-specific (3 fields)
    resource_type: Optional[str]
    versions: list[str]
    path: Optional[str]

    # Chunk-specific (6 fields)
    chunk_id: Optional[str]
    chunk_index: Optional[int]
    chunk_breadcrumb: Optional[str]
    resource_id: Optional[str]
    resource_title: Optional[str]
    summary: Optional[str]
    sections: list[str]

    # Rule-specific (2 fields)
    rationale: Optional[str]
    approved: Optional[bool]
```

**Recommendation**: Use inheritance or composition instead:

```python
@dataclass
class BaseSearchResult:
    id: str
    title: str
    content: str
    score: float
    tags: list[str]

@dataclass
class LessonResult(BaseSearchResult):
    confidence: Optional[str]
    source: Optional[str]
    source_notes: Optional[str]
    contexts: list[str]
    anti_contexts: list[str]

# Similarly for ResourceResult, ChunkResult, RuleResult
```

### 1.3 - Resource Versioning Model Inconsistency (MEDIUM PRIORITY)

**Location**: `schema.py` lines 95-100, `core.py` lines 1348-1351

**Issue**: Resources have a many-to-many relationship with versions via a separate table:

```sql
CREATE TABLE resource_versions (
    resource_id TEXT NOT NULL,
    version TEXT NOT NULL,
    PRIMARY KEY (resource_id, version)
);
```

But this creates odd operational patterns:
- Default version is hardcoded to `'unversioned'` (Line 1322 in core.py)
- Version filtering in search is complex (search.py lines 501-548 with set logic)
- Versions aren't first-class - no description, no hierarchy

**Recommendation**: Consider whether versions truly belong on resources, or if they're actually a search context. If kept:
- Add version descriptions to a `versions` reference table
- Consider marking a "preferred" or "latest" version
- Document the semantics clearly (intersection vs. union logic)

---

## 2. DRY Violations & Consolidation Opportunities

### 2.1 - Repeated Filter Building Logic

**Location**: `search.py` lines 342-380 (`_execute_vector_search`), lines 394-431 (`_get_filtered_lessons`)

Both functions build nearly identical filter clauses for tags, contexts, confidence, and source.

**Recommendation**: Extract to helper:

```python
def _build_tag_filter_clause(tag_filter: Optional[list[str]]) -> tuple[str, list]:
    """Return (SQL clause, params) for tag filtering."""
    if not tag_filter:
        return ("", [])
    placeholders = ",".join("?" * len(tag_filter))
    return (
        f"l.id IN (SELECT lesson_id FROM lesson_tags WHERE tag IN ({placeholders}))",
        tag_filter
    )
```

### 2.2 - Repeated Resource Row Processing

**Location**: `search.py` lines 676-724 (`_process_resource_row`) and lines 727-797 (`_process_chunk_row`)

Both functions fetch versions and tags from database identically.

**Recommendation**: Extract common parts:

```python
def _fetch_resource_metadata(conn: sqlite3.Connection, resource_id: str) -> tuple[set[str], list[str]]:
    """Fetch versions and tags for a resource."""
    # ...
```

### 2.3 - Lesson Property Fetching Duplication

**Location**: `core.py` lines 304-322 and `search.py` lines 453-470

Both `get_lesson()` and `_row_to_result()` fetch tags and contexts from the database with identical code.

**Recommendation**: Extract to helper:

```python
def _fetch_lesson_properties(conn: sqlite3.Connection, lesson_id: str) -> tuple[list[str], list[str], list[str]]:
    """Fetch tags, contexts, and anti_contexts for a lesson."""
```

---

## 3. Schema & Relationship Management Issues

### 3.1 - Link Management Fragmentation

**Location**: Schema (lines 53-59 for edges, 158-164 for lesson_links, 186-195 for resource_links)

There are now **3 separate link tables** with different semantics:

| Table | From | To | Relation | Purpose |
|-------|------|----|---------| ---------|
| `edges` | lesson | lesson | Free-form (related_to, derived_from, contradicts) | Lesson graph |
| `lesson_links` | lesson | resource | Fixed (related_to) | Cross-entity linking |
| `resource_links` | resource → chunk | resource → chunk | Markdown links | Extracted references |

**Problem**:
1. No unified query pattern - three different tables mean three different query patterns
2. Relation types are inconsistent
3. Traversal is fragmented: Getting "everything related to lesson X" requires querying all 3 tables separately

**Recommendation**: Consider unified link model:

```sql
CREATE TABLE links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id TEXT NOT NULL,
    from_type TEXT NOT NULL CHECK (from_type IN ('lesson', 'resource', 'chunk')),
    to_id TEXT NOT NULL,
    to_type TEXT NOT NULL CHECK (to_type IN ('lesson', 'resource', 'chunk')),
    relation TEXT NOT NULL,
    metadata TEXT,  -- JSON for optional data like markdown link text
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(from_id, from_type, to_id, to_type, relation)
);
```

This is a **breaking schema change**, so defer to a future major version.

### 3.2 - Lesson Contexts Modeling Confusion

**Location**: `schema.py` lines 44-50

Contexts are stored as free-form strings with no normalization (unlike tags).

**Problems**:
1. "shared branch" vs "shared-branch" vs "Shared Branch" are different entries
2. No deduplication or normalization
3. Hard to query "what contexts exist?"

**Recommendation**:
1. **Immediate**: Normalize contexts like tags (lowercase, trim, deduplicate in code)
2. **Long-term**: Move contexts to a reference table

### 3.3 - Bidirectional Link Tracking Missing

**Issue**: No utility to find incoming links to an entity or detect orphaned resources.

**Recommendation**: Add helper functions:

```python
def get_incoming_links(entity_id: str, entity_type: str, config: Optional[Config] = None) -> list[tuple[str, str, str]]:
    """Get all incoming links. Returns list of (from_id, from_type, relation)."""

def get_orphaned_resources(min_incoming: int = 0, config: Optional[Config] = None) -> list[str]:
    """Get resources with fewer than min_incoming links."""
```

---

## 4. Logical Gaps & Incomplete Features

### 4.1 - Search Result Link Boosting Logic Unclear

**Location**: `search.py` lines 971-1026 (`_apply_link_boosting`)

Link boosting only applies if the linked resource appears in current search results. This is a design choice but should be documented.

### 4.2 - Rule Search Requires Tag Overlap

**Location**: `search.py` lines 893-968 (`search_rules`)

Rules only appear if they have tag overlap. A generic rule ("Always validate input") won't surface without context tags.

**Recommendation**: Add a rule property (e.g., `is_global: bool`) to distinguish context-specific vs. global rules.

### 4.3 - Incomplete Feedback/Monitoring System

Feedback table exists but:
1. No trending analysis
2. No alerting when search quality degrades
3. No comparison with version data

---

## 5. Code Quality & Maintainability

### 5.1 - CLI Module Size & Complexity

**Location**: `cli.py` (1811 lines)

**Recommendation**: Split into:
- `cli.py`: Command routing and argument parsing
- `cli_display.py`: Result formatting and table rendering
- `cli_interactive.py`: Interactive prompts and validation

### 5.2 - Exception Handling Too Permissive

**Location**: `core.py` lines 622-632 (`link_lessons`), etc.

```python
except Exception:  # TOO BROAD
    return False
```

**Recommendation**: Catch specific exceptions like `sqlite3.IntegrityError`.

### 5.3 - Type Hints Incomplete

Many functions have partial type hints. Add `from __future__ import annotations` and complete type hints.

### 5.4 - Magic Numbers and Unexplained Constants

**Location**: `search.py` lines 98-114 (sigmoid parameters), lines 190-196 (scoring weights)

**Recommendation**: Extract to documented constants:

```python
SIGMOID_K = 6.0  # Steepness of sigmoid curve
SIGMOID_CENTER = 1.15  # Distance that maps to 0.5 score
KEYWORD_BOOST_MAX = 0.15  # Maximum keyword boost
```

---

## 6. Missing Features & Loose Ends

### 6.1 - No Rule Editing After Creation

Missing: `update_rule()`, `unlink_from_rule()`

### 6.2 - No Batch Operations for Performance

Adding 100 lessons requires 100 separate connections.

**Recommendation**: Add `add_lessons_batch()`.

### 6.3 - No Lesson Versioning or History

Updates replace content with no history tracking.

---

## 7. Test Coverage Gaps

Only `test_core.py` and `test_chunking.py` exist. No tests for:
- Search functionality
- MCP server endpoints
- Link resolution and traversal
- Migration logic
- Feedback system

---

## 8. Documentation Gaps

### Missing:
- `OPERATIONS.md`: Backup, restore, monitoring
- `TROUBLESHOOTING.md`: Common issues and solutions
- `MIGRATION.md`: Upgrading between versions

---

## 9. Recommendations by Priority

### HIGHEST PRIORITY (Do First)

1. **Extract tag handling to generic helper** - 30 min, saves 50+ lines
2. **Break down SearchResult dataclass** - 2-3 hours
3. **Extract filter building logic** - 45 min, saves 40+ lines
4. **Add specific exception handling** - 1 hour

### HIGH PRIORITY (Do Soon)

5. **Unify link model** - Planning phase, breaking change for next major version
6. **Add batch operations** - 1-2 hours
7. **Normalize contexts** - 1 hour
8. **Add missing rule operations** - 1 hour

### MEDIUM PRIORITY (Do Eventually)

9. Split `cli.py` into modules - 2-3 hours
10. Add comprehensive tests - 4-6 hours
11. Add operational documentation - 2-3 hours

---

## 10. Good Practices Observed

1. **Consistent configuration pattern** - All modules use `get_config()` singleton
2. **Schema versioning** - Migrations are tracked and applied systematically
3. **Embedding abstraction** - Clean backend selection pattern in `embeddings.py`
4. **Separate concerns** - Search, chunking, links are modular
5. **Planning documentation** - Excellent decision records in docs/

---

## Conclusion

The project demonstrates strong architectural thinking and planning. Key opportunities:

1. **Consolidate** duplicate tag/link/embedding handling into shared helpers
2. **Simplify** SearchResult through inheritance
3. **Unify** the fragmented link model
4. **Normalize** contexts like tags
5. **Test** the search and link resolution logic thoroughly

These changes would improve maintainability without breaking the thoughtful core design.
