# AI Lessons v2 - Resources Design Overview

High-level architecture map for the resources system extension. For detailed specifications, see [specs.md](specs.md). For design rationale and alternatives, see [planning.md](planning.md).

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interfaces                         │
├─────────────────────────────┬───────────────────────────────┤
│      CLI (cli.py)           │      MCP Server               │
│      ai-lessons command     │      (mcp_server.py)          │
└──────────────┬──────────────┴──────────────┬────────────────┘
               │                             │
               └──────────────┬──────────────┘
                              ▼
               ┌──────────────────────────────┐
               │     Core Library (core.py)   │
               │     - Lesson CRUD            │
               │     - Resource CRUD          │
               │     - Unified search         │
               │     - Graph traversal        │
               └──────────────┬───────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   db.py         │  │   search.py     │  │  embeddings.py  │
│   SQLite ops    │  │   Hybrid search │  │  Backend loader │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                   SQLite + sqlite-vec                        │
│                   ~/.ai/lessons/knowledge.db                 │
└─────────────────────────────────────────────────────────────┘
```

## Entity Model

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│    lessons      │    │     rules       │    │   resources     │
│                 │    │                 │    │                 │
│ - title         │    │ - title         │    │ - title         │
│ - content       │    │ - content       │    │ - content       │
│ - confidence    │    │ - rationale     │    │ - type          │
│ - source        │    │ - approved      │    │ - path          │
│ - tags          │    │ - approved_by   │    │ - versions      │
│ - contexts      │    │ - suggested_by  │    │ - source_ref    │
│                 │    │ - tags          │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                     │                      │
         │                     │      edges           │
         └─────────────────────┼──────────────────────┘
                               │
                    ┌──────────┴──────────┐
                    │  related_to         │
                    │  derived_from       │
                    │  has_script         │
                    │  has_doc            │
                    │  proves             │
                    │  contradicts        │
                    │  supersedes         │
                    └─────────────────────┘
```

### Knowledge Type Differences

| Type | Nature | Rationale | Approval | Surfacing |
|------|--------|-----------|----------|-----------|
| Lesson | Objective (causality) | N/A | None needed | On search |
| Rule | Subjective (prescription) | Required | Required | Proactive + tag overlap |
| Resource | Reference material | N/A | None needed | On search |

## Resource Types

| Type | Source of Truth | Refresh | Executable |
|------|-----------------|---------|------------|
| `doc` | DB (snapshot) | Explicit | No |
| `script` | Filesystem | Lazy | Yes |

## Data Flow

### Adding a Document

```
CLI/MCP → core.add_resource(type=doc)
                    │
                    ├─→ Read file content
                    ├─→ Auto-capture git ref
                    ├─→ Store content blob
                    ├─→ Generate embedding
                    └─→ Store versions
```

### Adding a Script

```
CLI/MCP → core.add_resource(type=script)
                    │
                    ├─→ Verify file exists
                    ├─→ Auto-capture git ref
                    ├─→ Cache content for search
                    ├─→ Generate embedding
                    └─→ Store versions
```

### Searching

```
CLI/MCP → core.search(query, versions, type)
                    │
                    ├─→ Check script freshness (lazy reindex if stale)
                    ├─→ Run hybrid search
                    ├─→ Calculate version_score
                    ├─→ final_score = search_score × version_score
                    └─→ Return lightweight results
                              │
                              ▼
                    get_resource(id) → full content
```

## Version Matching

```
User query: --version v2 --version v3

┌─────────────────────┬────────────────┬──────────────┐
│ Resource Versions   │ Relationship   │ Score        │
├─────────────────────┼────────────────┼──────────────┤
│ [v2, v3]            │ Exact          │ × 1.00       │
│ [v2, v3, v4]        │ Superset       │ × 0.95       │
│ [v3]                │ Subset         │ × 0.85       │
│ [v2, v4]            │ Partial        │ × 0.75       │
│ [unversioned]       │ Unversioned    │ × 0.70       │
│ [v4, v5]            │ Disjoint       │ No match     │
└─────────────────────┴────────────────┴──────────────┘
```

## Filesystem Layout

```
~/.ai/reference/
├── {project}/
│   ├── docs/
│   │   ├── {version}/
│   │   ├── shared/
│   │   └── unversioned/
│   └── scripts/
│       ├── {version}/
│       ├── shared/
│       └── unversioned/
```

## Database Schema

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   resources     │     │resource_versions│     │     rules       │
├─────────────────┤     ├─────────────────┤     ├─────────────────┤
│ id (PK)         │◄────│ resource_id(FK) │     │ id (PK)         │
│ type            │     │ version         │     │ title           │
│ title           │     └─────────────────┘     │ content         │
│ path            │                             │ rationale       │
│ content         │     ┌─────────────────┐     │ approved        │
│ content_hash    │     │resource_chunks  │     │ approved_at     │
│ source_ref      │     ├─────────────────┤     │ approved_by     │
│ indexed_at      │     │ id (PK)         │     │ suggested_by    │
│ created_at      │◄────│ resource_id(FK) │     │ created_at      │
│ updated_at      │     │ chunk_index     │     │ updated_at      │
└────────┬────────┘     │ title           │     └────────┬────────┘
         │              │ content         │              │
         ▼              └─────────────────┘              │
┌─────────────────┐                             ┌───────┴─────────┐
│resource_        │     ┌─────────────────┐     │   rule_tags     │
│embeddings       │     │chunk_embeddings │     ├─────────────────┤
│ (vec0)          │     │ (vec0)          │     │ rule_id (FK)    │
├─────────────────┤     ├─────────────────┤     │ tag             │
│ resource_id(PK) │     │ chunk_id (PK)   │     └─────────────────┘
│ embedding       │     │ embedding       │
└─────────────────┘     └─────────────────┘     ┌─────────────────┐
                                                │   rule_links    │
                                                ├─────────────────┤
                                                │ rule_id (FK)    │
                                                │ target_id       │
                                                │ target_type     │
                                                └─────────────────┘
```

## Two-Tier Retrieval

```
┌─────────────────────────────────────────────────────────┐
│ Tier 1: Search (lightweight)                            │
│                                                         │
│ [ID] (0.89) Jira Workflows API                          │
│   type: doc | versions: v3                              │
│   "The Workflows API allows you to..."                  │
│                                                         │
│ [ID] (0.84) update-workflow.sh                          │
│   type: script | versions: v2, v3                       │
│   "#!/bin/bash\n# Updates a Jira..."                    │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ Tier 2: get_resource(id) → full content                 │
└─────────────────────────────────────────────────────────┘
```

**Rationale:** Minimizes context pollution for AI agents with limited context windows.
