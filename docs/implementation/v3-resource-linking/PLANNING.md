# Resource Linking & Section Hints - Planning Document

This document captures all ideas discussed during the design phase, including those that were discarded. Each idea includes rationale for why it was adopted or rejected.

## Problem Statement

When searching documentation, users benefit from:
1. Understanding what's *inside* a chunk before fetching it (section hints)
2. Navigating between related documents (link extraction and resolution)
3. Stable identifiers that survive file moves/renames

The jira-docs MCP server demonstrated these features effectively, and we want to bring similar UX to ai-lessons.

---

## Ideas Explored

### 1. Section Hints in Search Results

**Status**: ADOPTED

Display the headers contained within a chunk in search results, giving users a preview of what's inside before they fetch the full content.

**Example:**
```
[chunk] addVote (score: 0.54)
  sections: Parameters, Return type, Authorization
  > The addVote function allows users to vote...
```

**Rationale**: The jira-docs MCP shows section hints like "addVote, Parameters, Return type, Authorization" which tells you what information is available in that chunk. This is distinct from breadcrumbs (path TO the chunk) - sections show what's IN the chunk. Low implementation cost, high UX value.

---

### 2. Resource Linking via Markdown Link Extraction

**Status**: ADOPTED

Extract `[text](path)` patterns from document content, resolve paths, and create relationships between resources.

**Rationale**: Documentation often references other docs (e.g., an API endpoint links to its model definition). Automatically extracting and resolving these links creates a navigable graph without manual curation. The jira-docs MCP has a dedicated `get_model()` function; we can achieve similar discoverability through automatic link resolution.

---

### 3. Semantic IDs (e.g., `v3/IssueVotesApi/addVote`)

**Status**: DEFERRED (Priority: Low - Future)

Replace ULIDs with human-readable, hierarchical identifiers derived from file structure or content.

**Rationale (for deferral)**: While semantic IDs are nice for human readability (the jira-docs MCP uses them), they require:
- Consistent naming conventions across all imported docs
- Handling of name collisions
- Migration of existing resources

With summaries now showing in search results, ULIDs are less problematic - users see the title and summary, not just the ID. The cognitive load is manageable. Revisit if users report confusion.

---

### 4. Namespace Approach for Stable Identifiers

**Status**: DISCARDED

Require users to provide a namespace (e.g., `--namespace jira-api/v3`) when importing resources, creating stable identifiers independent of filesystem paths.

**Rationale (for rejection)**: The cognitive burden of remembering and consistently using namespaces is high. Users would need to recall what namespace they used previously, and typos would create duplicates. We explored AI-assisted namespace suggestion (search existing resources by content similarity), but this added complexity without guaranteeing consistency. The simpler path-based approach with an escape hatch (`update-paths`) covers the common case better.

---

### 5. Git Repository + Relative Path as Canonical ID

**Status**: DISCARDED

For git-tracked docs, use `git_remote + relative_path` as a stable identifier (e.g., `github.com/user/repo:v3/Apis/File.md`).

**Example:**
```python
git_remote = "https://github.com/shitchell/jira-cloud-rest-api"
git_path = "v3/Apis/IssueVotesApi.md"
canonical_id = "github.com/shitchell/jira-cloud-rest-api:v3/Apis/IssueVotesApi.md"
```

**Rationale (for rejection)**: Not all documentation lives in git repositories. We wanted a consistent solution that works for all files. Additionally, determining git remote requires shell calls and handling edge cases (multiple remotes, detached HEAD, etc.). The complexity wasn't justified when absolute paths + `update-paths` covers the use case.

---

### 6. Content Hash for Resource Identity

**Status**: PARTIALLY USED (not for primary identity)

Use the content hash (already stored) to detect when a file has moved (different path, same content).

**Rationale**: Content hash is useful for detecting "this file moved" scenarios, but it changes when content changes - which is the whole point of updating docs. It can't be the primary identifier. We keep it for integrity checking and potential future move detection prompts ("This looks like X moved from Y, link them?").

---

### 7. Filesystem Identifiers (inode, Windows File ID)

**Status**: DISCARDED

Use OS-level file identifiers that persist across renames.

| Identifier | Survives rename? | Survives copy? | Survives git checkout? |
|------------|------------------|----------------|------------------------|
| inode | Yes (same FS) | No | No |
| Windows File ID | Yes (same volume) | No | No |

**Rationale (for rejection)**: Git operations create new files constantly (checkout, pull, merge all create new inodes). Since most documentation is version-controlled, inodes are useless for our use case.

---

### 8. Embedded Links Table (Indirection Layer)

**Status**: DISCARDED

Replace absolute paths in stored content with placeholder IDs that resolve via a lookup table.

**Schema:**
```sql
CREATE TABLE embedded_links (
    id TEXT PRIMARY KEY,
    filepath TEXT
);
```

**Content transformation:**
```markdown
# Before storage
See [Filter](/docs/v3/Models/Filter.md)

# After storage
See [Filter]({{link:abc123}})

# At display time
Resolve {{link:abc123}} → /docs/v3/Models/Filter.md
```

**Rationale (for rejection)**: The goal was to make path updates cheap (update lookup table, not content). However, this adds complexity to every read operation. More importantly, we realized we can keep content pristine AND avoid re-embedding by storing links in a separate table and appending resolved links at display time. The simpler approach wins.

---

### 9. Copying Resources to ~/.ai/ Directory

**Status**: DISCARDED

On import, copy all resources to a managed directory (e.g., `~/.ai/resources/`), then track from there.

**Rationale (for rejection)**: This doesn't solve the rename/reorganization problem - it just moves it. Users would still need to map "project X was renamed to project Y" somehow. It also doubles storage and creates sync issues if the source file is updated. Keeping references to original paths is simpler.

---

### 10. Group ID for Batch Imports

**Status**: DISCARDED

Assign a group ID to resources imported together, allowing batch operations and relationship inference.

**Rationale (for rejection)**: This was proposed as a way to link resources from the same import session. However, explicit markdown link extraction is more accurate (links exist in the content) and doesn't require users to import related files in the same session. The `resource_links` table achieves the goal better.

---

### 11. Absolute Paths + update-paths Command

**Status**: ADOPTED

Use absolute filesystem paths as the primary identifier, with an admin command to bulk-update paths when files move.

```bash
ai-lessons admin update-paths --from /old/root --to /new/root
```

**Rationale**: This is the simplest approach that covers 95% of use cases. Files rarely move, and when they do, a single command fixes everything. No cognitive burden on import, no complex identity schemes. YAGNI principle applied.

---

### 12. Preserve Original Content (No Path Rewriting)

**Status**: ADOPTED

Store original document content verbatim. Don't rewrite relative links to absolute paths in stored content.

**Rationale**: If we embed absolute paths in content, then path changes require content changes, which require re-embedding (expensive). By keeping content pristine and storing resolved links in a separate table (`resource_links`), path updates only touch the links table - no re-indexing needed. Embeddings remain stable.

---

### 13. Two-Phase Link Resolution

**Status**: ADOPTED

Phase 1: Chunk document, extract sections for each chunk.
Phase 2: Extract links, determine which chunk each link is in, resolve to target chunks.

**Rationale**: We need to know all chunks and their sections before we can resolve intra-document fragment links (e.g., `[text](#parameters)`). A same-file fragment link needs to find which chunk contains that section header. The two-phase approach ensures all data is available before resolution.

---

### 14. Fragment Support in Links

**Status**: ADOPTED

Store the `#fragment` portion of links separately, enabling resolution to specific chunks.

**Schema:**
```sql
to_path TEXT,      -- /docs/v3/Models/Filter.md
to_fragment TEXT,  -- parameters (nullable)
```

**Rationale**: Many docs link to specific sections (`[see Parameters](#parameters)`). Storing fragments allows us to resolve these to the specific chunk containing that section, not just the parent resource. This enables precise navigation.

---

### 15. Self-Link Detection and Skipping

**Status**: ADOPTED

When a fragment link resolves to the same chunk it's in, don't create an edge.

**Rationale**: A table of contents within a chunk might link to `#section-name` where that section is in the same chunk. Creating an edge from a chunk to itself is meaningless and clutters the graph.

---

### 16. Extract Links from All File Types

**Status**: ADOPTED

Apply the markdown link regex (`[text](path)`) to all imported files, not just `.md` files.

**Rationale**: Markdown-style links appear in docstrings, comments, and other contexts. The regex is cheap, and false positives are unlikely (the `[text](path)` pattern is fairly specific). We might catch useful links in scripts or config files.

---

### 17. Re-import Behavior (Delete + Rebuild)

**Status**: ADOPTED

When importing a resource with a path that already exists:
1. Keep the same resource ID (preserves external references)
2. Delete old chunks, links, edges
3. Re-chunk, re-extract links, rebuild edges

**Rationale**: We explicitly don't want to maintain versioned history of resources - it pollutes search results. Clean slate on re-import ensures the database reflects current state. Keeping the same resource ID means any external references (from other docs, manual edges) remain valid.

---

### 18. related Command

**Status**: ADOPTED

New CLI command to show resources linked to/from a given resource.

```bash
ai-lessons recall related <resource_id>
```

**Rationale**: Once we have link data, users need a way to explore it. This command surfaces both outgoing links (resources this doc references) and incoming links (resources that reference this doc), enabling documentation navigation.

---

## Summary

| Idea | Status | One-line Rationale |
|------|--------|-------------------|
| Section hints | ADOPTED | High UX value, low cost |
| Markdown link extraction | ADOPTED | Automatic relationship discovery |
| Semantic IDs | DEFERRED | Summaries reduce need; complexity not justified yet |
| Namespace identifiers | DISCARDED | Cognitive burden too high |
| Git repo + path | DISCARDED | Not all docs in git; wanted consistency |
| Content hash identity | PARTIAL | Good for integrity, not primary ID |
| Filesystem IDs (inode) | DISCARDED | Don't survive git operations |
| Embedded links table | DISCARDED | Simpler to keep content pristine |
| Copy to ~/.ai/ | DISCARDED | Doesn't solve the problem |
| Group ID for imports | DISCARDED | Explicit links more accurate |
| Absolute paths + update-paths | ADOPTED | Simplest solution, covers 95% |
| Preserve original content | ADOPTED | Avoids re-embedding on path changes |
| Two-phase resolution | ADOPTED | Needed for fragment resolution |
| Fragment support | ADOPTED | Enables precise chunk linking |
| Self-link detection | ADOPTED | Avoids meaningless edges |
| Extract from all files | ADOPTED | Cheap, might catch extra links |
| Re-import = delete + rebuild | ADOPTED | Clean slate, no version pollution |
| related command | ADOPTED | Surface the link graph to users |
