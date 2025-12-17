# AI Lessons v2 Specification

Technical specification for v2 extensions: resources, rules, and context-weighted search. For design rationale and alternatives considered, see [planning.md](planning.md).

## Overview

v2 extends ai-lessons with:
- **Resources** - Docs and scripts that complement lessons
- **Rules** - Prescriptive guidance with approval workflow
- **Context-weighted search** - Tag-based boosting for relevance

## Knowledge Types

| Type | Nature | Rationale | Approval | Surfacing |
|------|--------|-----------|----------|-----------|
| Lesson | Objective (causality) | N/A | None needed | On search |
| Rule | Subjective (prescription) | Required | Required | Proactive |
| Resource | Reference material | N/A | None needed | On search |

**Key distinction:** Lessons describe observed causality ("if X, then Y"). Rules describe desired outcomes with rationale ("do X to achieve Y, because [rationale]"). Rationale captures subjective human values and belongs only to rules.

## Resource Types

| Type | Source of Truth | Refresh Behavior | Executable |
|------|-----------------|------------------|------------|
| `doc` | DB (snapshot) | Explicit (`refresh-resource`) | No |
| `script` | Filesystem (path) | Lazy (on access if stale) | Yes |

**Rationale:** Different content types have different lifecycles. Docs are reference material (stable), scripts are living artifacts (evolving).

## Versioning

### Storage

Versions use a many-to-many relationship:

```sql
resource_versions:
  resource_id VARCHAR
  version VARCHAR  -- 'v2', 'v3', 'unversioned'
  PRIMARY KEY (resource_id, version)
```

A resource can have multiple versions (e.g., a script that works with both v2 and v3 APIs).

### Special Value: "unversioned"

Resources without version requirements use the literal string `"unversioned"` (not NULL).

**Rationale:** `"unversioned"` is an explicit state meaning "applies regardless of version," distinct from "version unknown."

### Version Match Scoring

When searching with `--version` filters:

| Relationship | Description | Score Modifier |
|--------------|-------------|----------------|
| Exact | `resource_versions = user_versions` | 1.0 |
| Superset | `resource_versions ⊃ user_versions` | 0.95 |
| Subset | `resource_versions ⊂ user_versions` | 0.85 |
| Partial overlap | Some intersection | 0.75 |
| Unversioned | Resource has `version = 'unversioned'` | 0.70 |
| Disjoint | No overlap | No match |

The version score multiplies into the search score for final ranking.

## Git Reference Tracking

When adding a resource from a file path:

1. Check if path is in a git repository
2. If yes, automatically capture current commit as `source_ref`
3. On refresh, warn if current HEAD differs from stored ref

**Rationale:** Automatic capture ensures provenance tracking without user effort.

## Filesystem Structure

```
~/.ai/reference/
├── {project}/
│   ├── docs/
│   │   ├── {version}/
│   │   │   └── *.md
│   │   ├── shared/           # Multi-version docs
│   │   └── unversioned/
│   └── scripts/
│       ├── {version}/        # Version-specific scripts
│       ├── shared/           # Multi-version scripts
│       └── unversioned/
```

**Rationale:** `shared/` directory makes multi-version resources explicit. Filesystem hierarchy serves as fallback when search fails.

## Database Schema

### resources

```sql
CREATE TABLE resources (
    id VARCHAR PRIMARY KEY,           -- ULID
    type VARCHAR NOT NULL,            -- 'doc', 'script'
    title VARCHAR NOT NULL,
    path VARCHAR,                     -- Filesystem path
    content BLOB,                     -- Stored for docs, cached for scripts
    content_hash VARCHAR,             -- For change detection
    source_ref VARCHAR,               -- Git ref (auto-captured)
    indexed_at TIMESTAMP,             -- When content was last indexed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_resources_type ON resources(type);
```

### resource_versions

```sql
CREATE TABLE resource_versions (
    resource_id VARCHAR NOT NULL,
    version VARCHAR NOT NULL,
    PRIMARY KEY (resource_id, version),
    FOREIGN KEY (resource_id) REFERENCES resources(id) ON DELETE CASCADE
);

CREATE INDEX idx_resource_versions_version ON resource_versions(version);
```

### resource_embeddings

```sql
CREATE VIRTUAL TABLE resource_embeddings USING vec0(
    resource_id TEXT PRIMARY KEY,
    embedding FLOAT[{dimensions}]
);
```

### resource_chunks (for large documents)

```sql
CREATE TABLE resource_chunks (
    id VARCHAR PRIMARY KEY,           -- ULID
    resource_id VARCHAR NOT NULL,     -- Parent resource
    chunk_index INTEGER NOT NULL,     -- Order within document
    title VARCHAR,                    -- Section title if applicable
    content TEXT NOT NULL,
    FOREIGN KEY (resource_id) REFERENCES resources(id) ON DELETE CASCADE
);

CREATE INDEX idx_resource_chunks_resource ON resource_chunks(resource_id);

CREATE VIRTUAL TABLE chunk_embeddings USING vec0(
    chunk_id TEXT PRIMARY KEY,
    embedding FLOAT[{dimensions}]
);
```

## CLI Commands

### Adding Resources

```bash
# Add a document (creates snapshot in DB)
ai-lessons contribute add-resource \
  --type doc \
  --path ~/.ai/reference/jira-api/docs/v3/WorkflowsApi.md \
  --title "Jira Workflows API" \
  --version v3

# Add a script (references filesystem path)
ai-lessons contribute add-resource \
  --type script \
  --path ~/.ai/reference/jira-api/scripts/shared/update-workflow.sh \
  --title "Update Jira Workflow" \
  --version v2 --version v3

# Add unversioned resource
ai-lessons contribute add-resource \
  --type script \
  --path ~/.ai/reference/utils/scripts/json-format.sh \
  --title "JSON Formatter" \
  --version unversioned
```

### Managing Resources

```bash
# Refresh doc from original path
ai-lessons contribute refresh-resource RESOURCE_ID

# Update metadata
ai-lessons contribute update-resource RESOURCE_ID --title "New Title"

# Delete resource
ai-lessons contribute delete-resource RESOURCE_ID
```

### Searching Resources

```bash
# Search all resources
ai-lessons recall search-resources "workflow transitions"

# Filter by type
ai-lessons recall search-resources "workflow" --type doc
ai-lessons recall search-resources "workflow" --type script

# Filter by version
ai-lessons recall search-resources "workflow" --version v3
ai-lessons recall search-resources "workflow" --version v2 --version v3

# Combined filters
ai-lessons recall search-resources "workflow" --type script --version v3 --limit 5
```

### Viewing and Running

```bash
# Show full resource content
ai-lessons recall show-resource RESOURCE_ID

# Run a script resource
ai-lessons recall run-resource RESOURCE_ID -- arg1 arg2
```

### Admin Commands

```bash
# Reindex all resources
ai-lessons admin reindex-resources

# Reindex specific resource
ai-lessons admin reindex-resource RESOURCE_ID

# List stale scripts (filesystem newer than index)
ai-lessons admin list-stale
```

## MCP Tools

### add_resource

```json
{
  "name": "add_resource",
  "description": "Add a doc or script resource",
  "parameters": {
    "type": {"type": "string", "enum": ["doc", "script"]},
    "path": {"type": "string", "description": "Filesystem path"},
    "title": {"type": "string"},
    "versions": {"type": "array", "items": {"type": "string"}}
  }
}
```

### search_resources

```json
{
  "name": "search_resources",
  "description": "Search docs and scripts with semantic search",
  "parameters": {
    "query": {"type": "string"},
    "type": {"type": "string", "enum": ["doc", "script"], "optional": true},
    "versions": {"type": "array", "items": {"type": "string"}, "optional": true},
    "limit": {"type": "integer", "default": 10}
  }
}
```

### get_resource

```json
{
  "name": "get_resource",
  "description": "Get full resource content by ID",
  "parameters": {
    "resource_id": {"type": "string"}
  }
}
```

### run_script

```json
{
  "name": "run_script",
  "description": "Execute a script resource",
  "parameters": {
    "resource_id": {"type": "string"},
    "args": {"type": "array", "items": {"type": "string"}, "optional": true}
  }
}
```

## Search Result Format

### Lightweight Results (from search)

```
[RESOURCE_ID] (score: 0.892) Jira Workflows API
  type: doc | versions: v3
  "The Workflows API allows you to create, update, and delete..."

[RESOURCE_ID] (score: 0.847) Update Jira Workflow Script
  type: script | versions: v2, v3
  path: ~/.ai/reference/jira-api/scripts/shared/update-workflow.sh
  "#!/bin/bash\n# Updates a Jira workflow with proper..."
```

### Full Content (from get_resource)

Complete content with all metadata, related resources, and navigation for chunked docs.

## Refresh Behavior

### Documents

- Content stored as blob at import time
- `refresh-resource` re-reads from `path` and updates blob
- Warns if `source_ref` doesn't match current git HEAD

### Scripts

- Content cached in DB for search
- On access: check if `mtime > indexed_at`
- If stale: re-read from `path`, update cache, regenerate embedding
- Manual: `admin reindex-resource` forces refresh

## Graph Edges

Resources can be linked to lessons, rules, and other resources:

| Relation | From | To | Meaning |
|----------|------|-----|---------|
| `has_script` | lesson/rule | script | Has implementing script |
| `has_doc` | lesson/rule | doc | References documentation |
| `related_to` | any | any | General relationship |
| `derived_from` | any | any | Knowledge derived from source |
| `proves` | script | lesson | Script validates the lesson |

---

## Rules

Rules are prescriptive guidance requiring human approval.

### Schema

```sql
CREATE TABLE rules (
    id VARCHAR PRIMARY KEY,              -- ULID
    title VARCHAR NOT NULL,
    content TEXT NOT NULL,
    rationale TEXT NOT NULL,             -- Why we want this outcome (required)
    approved BOOLEAN DEFAULT FALSE,      -- Must be approved to surface
    approved_at TIMESTAMP,
    approved_by VARCHAR,
    suggested_by VARCHAR,                -- Agent/session that suggested
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE rule_tags (
    rule_id VARCHAR NOT NULL,
    tag VARCHAR NOT NULL,
    PRIMARY KEY (rule_id, tag),
    FOREIGN KEY (rule_id) REFERENCES rules(id) ON DELETE CASCADE
);

CREATE TABLE rule_links (
    rule_id VARCHAR NOT NULL,
    target_id VARCHAR NOT NULL,          -- Lesson or resource ID
    target_type VARCHAR NOT NULL,        -- 'lesson', 'resource'
    PRIMARY KEY (rule_id, target_id),
    FOREIGN KEY (rule_id) REFERENCES rules(id) ON DELETE CASCADE
);

CREATE INDEX idx_rules_approved ON rules(approved);
CREATE INDEX idx_rule_tags_tag ON rule_tags(tag);
```

### Surfacing Logic

Rules only surface when:
1. `approved = TRUE`
2. AND at least one contextual overlap:
   - Tag overlap with search context
   - Direct link to a returned lesson/resource

**Rationale:** Prevents false positives. Rules about "Jira sandbox" only surface when searching in Jira context.

### CLI Commands

```bash
# Suggest a rule (creates with approved=false)
ai-lessons contribute suggest-rule \
  --title "Always GET before PUT on Jira workflows" \
  --rationale "PUT replaces entire resource; omitting items deletes them" \
  --tags jira-api,workflows \
  --link-lesson LESSON_ID \
  --link-script SCRIPT_ID

# List pending rules
ai-lessons admin pending-rules

# Review interactively
ai-lessons admin review-rules

# Approve specific rule
ai-lessons admin approve-rule RULE_ID

# Reject (delete) suggestion
ai-lessons admin reject-rule RULE_ID
```

### MCP Tools

```json
{
  "name": "suggest_rule",
  "description": "Suggest a rule for human approval",
  "parameters": {
    "title": {"type": "string"},
    "rationale": {"type": "string"},
    "tags": {"type": "array", "items": {"type": "string"}},
    "linked_lessons": {"type": "array", "items": {"type": "string"}, "optional": true},
    "linked_resources": {"type": "array", "items": {"type": "string"}, "optional": true}
  }
}
```

---

## Context-Weighted Search

### Syntax

```bash
# CLI
ai-lessons recall search "query" --context-tags "reviewer,jira-api=1.5,testing=1.3"

# MCP
{
  "query": "workflow transitions",
  "context_tags": {"reviewer": null, "jira-api": 1.5, "testing": 1.3}
}
```

### Weight Resolution

- Explicit weight: use as specified
- No weight (null): use average of explicit weights, or 1.5 if none specified

### Scoring

```
final_score = base_score × (1 + Σ(tag_weight × match_bonus))

where:
  match_bonus = 0.1 for each context tag that matches result tags
```

### MCP Tool Update

```json
{
  "name": "search",
  "description": "Search lessons, rules, and resources",
  "parameters": {
    "query": {"type": "string"},
    "context_tags": {
      "type": "object",
      "description": "Tag weights for context boosting",
      "additionalProperties": {"type": "number", "nullable": true}
    },
    "type": {"type": "string", "enum": ["lesson", "rule", "doc", "script"], "optional": true},
    "versions": {"type": "array", "items": {"type": "string"}, "optional": true},
    "limit": {"type": "integer", "default": 10}
  }
}
```

---

## Search Result Format (Updated)

### Unified Search Results

```
Rules (follow these):
  [R001] Always GET before PUT on Jira workflows
    applies to: jira-api, workflows
    rationale: "PUT replaces entire resource..."

Scripts (try these):
  [S001] (0.89) update-workflow.sh
    versions: v2, v3 | path: ~/.ai/reference/jira-api/scripts/shared/
    "Updates workflow with proper status preservation..."

Lessons (context):
  [L001] (0.88) PUT /workflows replaces entire resource
    confidence: high | source: tested

Docs (reference):
  [D001] (0.82) Jira Workflows API v3
    versions: v3

---
💡 Contribution prompts based on gaps (see agent-protocol.md)
```
