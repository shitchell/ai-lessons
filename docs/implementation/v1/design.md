# AI Lessons v1 - Design Overview

This document provides a high-level map of the codebase. Use it to quickly orient yourself and find where to make changes.

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
               │     - CRUD operations        │
               │     - Search orchestration   │
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

## Module Index

| Module | Purpose | When to Modify |
|--------|---------|----------------|
| `core.py` | Main API, orchestrates everything | Adding new operations, changing business logic |
| `cli.py` | Click-based CLI | Adding/changing CLI commands |
| `mcp_server.py` | MCP server for Claude Code | Adding/changing MCP tools |
| `db.py` | Database connection and operations | Changing DB behavior, migrations |
| `schema.py` | Table definitions and seed data | Schema changes, new reference data |
| `search.py` | Hybrid search implementation | Tuning search, new search strategies |
| `embeddings.py` | Embedding backend abstraction | Adding new embedding providers |
| `config.py` | Configuration loading | New config options |

## Data Flow

### Adding a Lesson
```
CLI/MCP → core.add_lesson() → embeddings.embed_text() → db.get_db()
                                      │                      │
                                      ▼                      ▼
                              Generate embedding      Store in SQLite
                                      │                      │
                                      └──────────┬───────────┘
                                                 ▼
                                    lesson_embeddings (vec0 table)
```

### Searching
```
CLI/MCP → core.recall() → search.hybrid_search()
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
        vector_search()     keyword_search()      Tag filtering
              │                    │                    │
              └────────────────────┼────────────────────┘
                                   ▼
                         Reciprocal Rank Fusion
                                   │
                                   ▼
                           Ranked results
```

## Database Schema

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ confidence_     │     │    lessons      │     │  source_types   │
│ levels          │     │                 │     │                 │
├─────────────────┤     ├─────────────────┤     ├─────────────────┤
│ name (PK)       │◄────│ confidence (FK) │     │ name (PK)       │
│ ordinal         │     │ source (FK)─────│────►│ description     │
└─────────────────┘     │ id (PK)         │     │ typical_conf    │
                        │ title           │     └─────────────────┘
                        │ content         │
                        │ source_notes    │
                        │ created_at      │
                        │ updated_at      │
                        └────────┬────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  lesson_tags    │     │ lesson_contexts │     │     edges       │
├─────────────────┤     ├─────────────────┤     ├─────────────────┤
│ lesson_id (FK)  │     │ lesson_id (FK)  │     │ from_id (FK)    │
│ tag             │     │ context         │     │ to_id (FK)      │
└─────────────────┘     │ applies (bool)  │     │ relation        │
                        └─────────────────┘     └─────────────────┘

┌─────────────────┐     ┌─────────────────┐
│lesson_embeddings│     │  tag_relations  │
│ (vec0 virtual)  │     ├─────────────────┤
├─────────────────┤     │ from_tag        │
│ lesson_id (PK)  │     │ to_tag          │
│ embedding       │     │ relation        │
└─────────────────┘     └─────────────────┘
```

## Key Design Decisions

| Decision | Rationale | See Also |
|----------|-----------|----------|
| SQLite + sqlite-vec | Single file, portable, <2GB RAM | specs.md §Database |
| Hybrid search | Pure semantic misses exact matches | specs.md §Search |
| Reference tables vs CHECK | Can add values at runtime | specs.md §Schema |
| Tags over hierarchy | Same knowledge can belong in multiple places | specs.md §Organization |
| Configurable embeddings | Free (sentence-transformers) or quality (OpenAI) | specs.md §Embeddings |

## Common Modifications

### Add a new CLI command
1. Open `cli.py`
2. Find the appropriate group (`admin`, `learn`, or `recall`)
3. Add new `@group.command()` decorated function
4. If it needs new core logic, add to `core.py`

### Add a new MCP tool
1. Open `mcp_server.py`
2. Add tool definition in `list_tools()`
3. Add handler in `call_tool()`

### Add a new embedding backend
1. Open `embeddings.py`
2. Create new class inheriting from `EmbeddingBackend`
3. Add case in `get_embedder()`
4. Update `config.py` with any new config options

### Add a new source type
```bash
ai-lessons admin add-source NAME --description "..."
```
Or directly in `schema.py` SEED_SOURCE_TYPES.

### Change schema
1. Modify `schema.py`
2. Increment `SCHEMA_VERSION`
3. Add migration logic in `db.py` `init_db()`

## File Locations

| What | Where |
|------|-------|
| Source code | `src/ai_lessons/` |
| Tests | `tests/` |
| User database | `~/.ai/lessons/knowledge.db` |
| User config | `~/.ai/lessons/config.yaml` |
| Planning docs | `PLANNING.md`, `TECHNICAL.md` |
| Detailed specs | `docs/implementation/v1/specs.md` |

## Testing

```bash
pytest tests/ -v              # Run all tests
pytest tests/ -k "search"     # Run tests matching "search"
pytest tests/ --tb=short      # Shorter tracebacks
```

Tests use temporary databases with sentence-transformers (CPU-only).

## Philosophy

1. **Simple over clever** - SQLite over Postgres, hybrid search over ML re-ranking
2. **Flexible over prescriptive** - Free-form tags, optional fields, extensible
3. **Local-first** - Single file database, no server process, syncs with dotfiles
4. **Multi-agent** - Same backend serves CLI, MCP, and any future interfaces
