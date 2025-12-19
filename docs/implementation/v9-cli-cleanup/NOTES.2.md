# v9.1: Info Command Group

## Overview

Add new top-level `info` command group for schema/discovery commands. Consolidates scattered discovery commands and adds new capabilities.

## New Command Structure

```
ai-lessons info
├── tags          # List tags with usage info
├── confidence    # List confidence levels
├── lesson-sources # List source types (lesson-specific)
├── relations     # List edge relation types
└── stats         # Database statistics (moved from admin)
```

## Command Details

### `info tags`

List all tags across entities with usage counts and alias info.

**Options:**
| Option | Description |
|--------|-------------|
| `--counts` | Show usage counts per entity type |
| `--type lesson\|resource\|rule` | Filter by entity type |
| `--pattern TEXT` | Filter tags by substring |
| `--unused` | Show only tags in tag_relations with zero usage |
| `--sort name\|count` | Sort order (default: name) |

**Output Structure:**
```
Active tags:
  api (5 lessons, 12 resources, 0 rules)
  jira (3 lessons, 8 resources, 1 rule)
  ...

Tag aliases:
  js → javascript
  k8s → kubernetes
  ...
```

### `info confidence`

List confidence levels with optional usage counts.

**Options:**
| Option | Description |
|--------|-------------|
| `--counts` | Show how many lessons at each level |

**Output:**
```
Confidence levels:
  1. very-low (2 lessons)
  2. low (5 lessons)
  3. medium (12 lessons)
  4. high (8 lessons)
  5. very-high (3 lessons)
```

### `info lesson-sources`

List source types (lesson-specific for now).

**Options:**
| Option | Description |
|--------|-------------|
| `--counts` | Show how many lessons use each |
| `--verbose` | Show descriptions + typical confidence |

**Output (verbose):**
```
Source types:
  inferred    - Reasoned from evidence (typical: low-medium)     [5 lessons]
  tested      - Ran code, verified behavior (typical: high)      [12 lessons]
  documented  - Official docs/specs (typical: medium-high)       [8 lessons]
  observed    - Saw in logs/output (typical: medium)             [3 lessons]
  hearsay     - Someone said so (typical: low)                   [1 lesson]
```

### `info relations`

List edge relation types used in the graph.

**Options:**
| Option | Description |
|--------|-------------|
| `--counts` | Show edge counts per relation type |
| `--type lesson\|resource\|rule` | Filter by from/to entity types |

**Output:**
```
Edge relations:
  related_to (45 edges)
  derived_from (12 edges)
  prerequisite_of (3 edges)
  documents (8 edges)
```

### `info stats`

Database statistics (moved from `admin stats`).

**Options:**
| Option | Description |
|--------|-------------|
| `--json` | Machine-readable output |
| `--verbose` | Detailed breakdown |

**Notes:**
- Keep `admin stats` as alias for backwards compat? Or just remove?
- Consider adding `--json` to other info commands later

## Migration

### Commands to Move
- `recall tags` → `info tags`
- `recall confidence` → `info confidence`
- `recall sources` → `info lesson-sources`
- `admin stats` → `info stats`

### New Commands
- `info relations` (new)

### Deprecation Strategy
- Add deprecation warnings to old locations
- Or just remove since we're pre-1.0?

## Schema Notes

**Tag storage:**
- `lesson_tags(lesson_id, tag)` - junction table
- `resource_tags(resource_id, tag)` - junction table
- `rule_tags(rule_id, tag)` - junction table
- `tag_relations(from_tag, to_tag, relation)` - aliases/hierarchy

**Source/Confidence:**
- Lesson-only: `lessons.confidence`, `lessons.source`
- Reference tables: `confidence_levels`, `source_types`

**Relations:**
- Stored in `edges.relation` column
- No predefined list - derived from actual usage

## Open Questions

1. Keep old command locations with deprecation warnings, or remove entirely?
2. Add `--json` output format to all info commands?
3. `admin stats` - keep as alias or remove?
