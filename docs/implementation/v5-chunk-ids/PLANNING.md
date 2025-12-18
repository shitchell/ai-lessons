# v5-chunk-ids: Planning Document

**Created**: 2025-12-17
**Status**: Planning Complete
**Schema Version**: v11 (from current v10)

---

## Table of Contents

1. [Overview](#overview)
2. [Design Questions](#design-questions)
3. [Option 1: Chunk ID Format](#option-1-chunk-id-format)
4. [Option 2: Terminology](#option-2-terminology)
5. [Option 3: Minimum Chunks per Resource](#option-3-minimum-chunks-per-resource)
6. [Option 4: Script Chunking](#option-4-script-chunking)
7. [Option 5: Search Result Display](#option-5-search-result-display)
8. [Option 6: Resource-level Match Inclusion](#option-6-resource-level-match-inclusion)
9. [Option 7: Show Command Structure](#option-7-show-command-structure)
10. [Option 8: Chunk ID Storage vs Display](#option-8-chunk-id-storage-vs-display)
11. [Decisions Summary](#decisions-summary)

---

## Overview

This planning document captures all options discussed for improving chunk identification and search UX in ai-lessons. Each option includes its status (Kept/Discarded/Deferred) and rationale.

### Problem Statement

The current chunk system has several UX issues:
- Chunk IDs are independent ULIDs with no visible relationship to their parent resource
- Small documents have 0 chunks, creating inconsistent behavior
- Scripts are not chunked, missing search opportunities
- Search results show a flat list without grouping by resource
- Users need separate commands for resources vs chunks

---

## Design Questions

Before designing solutions, we discussed philosophical questions about the codebase:

### Q: How do we prioritize resources vs chunks?

**Answer**: Resources are the *management* unit (add/remove/tag/version), while chunks are the *retrieval* unit (search/read). This means:
- Resources are what users add, tag, and manage
- Chunks are what search returns and what provides specific answers
- Both need IDs, but chunks should clearly indicate their parent

### Q: What audience is this for?

**Answer**: AI agents and occasional human admins. Technical terminology is acceptable.

---

## Option 1: Chunk ID Format

### 1A: Keep ULID Format (Current)

**Description**: Each chunk gets an independent ULID like `01KCPN9VWAZNSKYVHPCWVPXA2C`

**Status**: Discarded

**Rationale**: No visible relationship to parent resource. When search returns a chunk, users can't tell which resource it came from without a database lookup. The resource_id column exists but isn't surfaced in the ID itself.

---

### 1B: Use `<resource_id>.<chunk_index>` Format

**Description**: Chunk IDs combine parent resource ID with chunk index, e.g., `01KCPN9VWAZNSKYVHPCWVPXA2C.5`

**Status**: Kept

**Rationale**:
- Parent relationship is structural and visible
- Uniqueness guaranteed: if resource ULID is unique and each resource has only one chunk N, then `<resource_id>.<N>` is unique
- Easy to parse programmatically
- Human-readable at a glance
- Enables unified `show` command (see Option 7)

---

## Option 2: Terminology

### 2A: Keep "chunks" Terminology

**Description**: Continue calling document subdivisions "chunks"

**Status**: Kept

**Rationale**: Target audience is AI agents and technical users. "Chunk" is standard terminology in the vector database and RAG ecosystem. No benefit to changing it.

---

### 2B: Use "sections" or "passages"

**Description**: Rename chunks to more user-friendly terminology

**Status**: Discarded

**Rationale**: Would require significant codebase changes for no real benefit given technical audience. "Chunks" accurately describes what they are in the context of document chunking for embeddings.

---

## Option 3: Minimum Chunks per Resource

### 3A: Only Chunk Large Documents (Current)

**Description**: Documents smaller than `min_chunk_size * 2` tokens get 0 chunks (strategy="none")

**Status**: Discarded

**Rationale**: Creates inconsistent behavior:
- Large docs: searchable via chunk embeddings
- Small docs: only searchable via resource-level embedding
- Requires special-case handling throughout search code
- 0-chunk resources can't have fragment links resolved

---

### 3B: Always Create At Least 1 Chunk

**Description**: All resources (regardless of size) get at least 1 chunk. Small docs get strategy="single" with full content as chunk 0.

**Status**: Kept

**Rationale**:
- Consistent behavior: all resources have chunks
- All content searchable via chunk embeddings
- Simplifies deduplication logic (always dedupe by resource via chunks)
- Fragment links can always resolve to a chunk
- Single-source-of-truth for searchable content

---

## Option 4: Script Chunking

### 4A: Scripts Not Chunked (Current)

**Description**: Only `type='doc'` resources get chunked; scripts are resource-level only

**Status**: Discarded

**Rationale**: Scripts are valuable examples that should be searchable at the same granularity as docs. Treating them differently creates artificial limitations.

---

### 4B: Scripts Chunked Like Docs

**Description**: Scripts are first-class citizens, chunked with the same logic as docs

**Status**: Kept

**Rationale**:
- Scripts provide lessons through tested, validated examples
- Should be as searchable as docs
- Consistent behavior across resource types
- Future option: script-specific chunking (e.g., by function) can be added later

---

## Option 5: Search Result Display

### 5A: Flat List (Current)

**Description**: Search returns a flat list of results, deduplicating to show only the best-scoring chunk per resource

**Status**: Discarded

**Rationale**: Loses information about other relevant chunks in the same resource. User might want to see all relevant sections, not just the top one.

---

### 5B: Grouped Resources with Ranked Chunks

**Description**: Search returns:
1. Top matches summary (e.g., `README.md.58 (0.87), AnnouncementBannerApi.md.1 (0.75)`)
2. Resources grouped with all their matching chunks ranked by score

**Status**: Kept

**Rationale**:
- Shows all relevant content, not just top match per resource
- Resources ranked by their best chunk score
- Top matches summary enables quick navigation
- Maintains context: "this chunk is from that resource"

**Example Output**:
```
Top matches: README.md.58 (0.87), AnnouncementBannerApi.md.1 (0.75)

README.md (v3) [jira, api]
  .58 (0.87) Authorization > OAuth2
  .62 (0.81) basicAuth

AnnouncementBannerApi.md (v3) [jira, api]
  .1  (0.75) getBanner
  .3  (0.68) setBanner
```

---

## Option 6: Resource-level Match Inclusion

### 6A: Only Show Resources with Chunk Matches

**Description**: If no specific chunk scored highly, don't show the resource

**Status**: Discarded

**Rationale**: Misses resources that are broadly relevant but don't have a single standout chunk. A resource about "authentication" might be very relevant to an "OAuth" query even if no single chunk dominates.

---

### 6B: Include Resource-level Matches

**Description**: Resources with strong resource-level embedding match but no specific chunk match are still shown (with empty chunks list or a note)

**Status**: Kept

**Rationale**:
- Captures broadly relevant resources
- Resource-level embedding represents overall document topic
- User sees "this document is relevant" even if no single section stands out
- Can indicate "(no specific section)" or similar

---

## Option 7: Show Command Structure

### 7A: Separate Commands (Current)

**Description**: `show-resource <id>` and `show-chunk <id>` as distinct commands

**Status**: Discarded (kept as aliases)

**Rationale**: With new chunk ID format (`<resource>.<N>`), the ID itself indicates the entity type. No need for separate commands.

---

### 7B: Unified `show` Command

**Description**: Single `show <id>` command that auto-detects entity type from ID format:
- No `.N` suffix → resource
- `.N` suffix → chunk

**Status**: Kept

**Rationale**:
- Simpler UX: one command to learn
- ID format self-documenting
- Old commands kept as aliases for backwards compatibility

---

## Option 8: Chunk ID Storage vs Display

### 8A: Display-only Format

**Description**: Store chunk IDs as ULIDs internally, display as `<resource>.<N>` in output only

**Status**: Discarded

**Rationale**:
- Requires translation layer everywhere IDs are shown
- Copy-paste from output wouldn't work for lookups
- Adds complexity without benefit

---

### 8B: Actual Storage Format

**Description**: Store chunk IDs in `<resource_id>.<chunk_index>` format in the database

**Status**: Kept

**Rationale**:
- What you see is what you get
- Copy-paste from output works directly
- Simpler codebase: no translation needed
- Requires one-time migration (v11) but that's a fair tradeoff

---

## Decisions Summary

| Decision | Option Chosen | Key Rationale |
|----------|---------------|---------------|
| Chunk ID Format | `<resource_id>.<N>` | Parent relationship visible, parseable |
| Terminology | Keep "chunks" | Technical audience, standard RAG terminology |
| Minimum Chunks | Always 1+ | Consistent behavior, all content searchable |
| Script Chunking | First-class | Scripts are valuable searchable content |
| Search Display | Grouped + top matches | Shows all relevant content with context |
| Resource-level Matches | Include | Captures broadly relevant resources |
| Show Command | Unified with aliases | Simpler UX, self-documenting IDs |
| ID Storage | Actual format | No translation layer needed |

---

## Implementation Reference

See `SPECS.md` for detailed implementation specifications including:
- Code changes per file
- Migration logic
- Test requirements
- Verification steps
