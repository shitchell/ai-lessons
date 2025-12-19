# v9-cli-cleanup: Remove Redundant CLI Commands

## Recall Commands to Remove

### Pure Aliases (redundant with unified `show`)
- [ ] `show-resource` - auto-detected by `show` via ID prefix
- [ ] `show-chunk` - auto-detected by `show` via ID prefix
- [ ] `show-rule` - auto-detected by `show` via ID prefix

### Redundant with unified `related`
- [ ] `related-lesson` - same as `related` with lesson ID

### Convenience Shortcuts (redundant with unified commands)
- [ ] `search-lesson` - use `search --type lesson` instead
- [ ] `search-resources` - use `search --type resource` instead
- [ ] `list-resources` - use `list --type resource` instead

## Contribute Commands to Remove

### Pure Aliases (redundant with unified commands)
- [ ] `delete-lesson` - auto-detected by `delete` via ID prefix
- [ ] `delete-resource` - auto-detected by `delete` via ID prefix
- [ ] `refresh-resource` - identical to `refresh`

### Redundant with unified `link`/`unlink`
- [ ] `link-lesson` - same as `link` with two lesson IDs
- [ ] `link-resource` - same as `link` with lesson+resource IDs
- [ ] `unlink-lesson` - same as `unlink` with two lesson IDs
- [ ] `unlink-resource` - same as `unlink` with lesson+resource IDs

### Convenience Shortcuts
- [ ] `update-lesson` - use `update LSN...` with `--lesson-*` options

## Root Help Cleanup

- [ ] Remove duplicate command listing in `ai-lessons --help` (listed in docstring AND auto-generated Commands section)

## Help Formatting

- [ ] Fix mangled examples in help output (Click's text wrapper breaks them)
  - Option 1: Use `\b` marker in docstrings to preserve formatting
  - Option 2: Custom help formatter class
  - Option 3: Move examples to bottom (epilog-style) - Click doesn't have native epilog but can fake it

## Database Cleanup (Required First)

### Migrate rule linking from `rule_links` to `edges` table
**Problem:** Rule linking inconsistently uses both `rule_links` and `edges` tables
- `get_rule()` reads from BOTH tables
- `suggest_rule()` writes to `rule_links`
- `link_to_rule()` / `unlink_from_rule()` use `rule_links`

**Solution:** Migrate fully to `edges` table (consistent with lesson/resource linking)
- [ ] Update `suggest_rule()` to write links to `edges` instead of `rule_links`
- [ ] Update `link_to_rule()` to use `edges`
- [ ] Update `unlink_from_rule()` to use `edges`
- [ ] Update `get_rule()` to read ONLY from `edges` (remove `rule_links` reads)
- [ ] Remove `rule_links` table from schema (or leave as dead code for now)

**Note:** No migration needed - we're pre-1.0, no users, can rebuild DB from scratch.

## Admin Commands to Remove/Simplify

### Resource-specific commands to generalize
- [ ] `clear-resources` → `clear` (with `--type` filter, or auto-detect from filters)
- [ ] `reindex-resources` → `reindex` (only resources have embeddings anyway)

---

## Commands to Unify (DECISIONS MADE)

### `add-lesson` / `suggest-rule` → `add --type lesson|rule`
### `add-resource` → `import`
**Decision:**
- Unify `add-lesson` + `suggest-rule` into `add --type lesson|rule`
- Rename `add-resource` to `import` (semantically different - takes file paths, has chunking, etc.)
- For rules: notify user at end that it needs admin review/approval

Commands to change:
- [ ] `add-lesson` → `contribute add --type lesson`
- [ ] `suggest-rule` → `contribute add --type rule`
- [ ] `add-resource` → `contribute import` (rename, not unify)

### `related-resource` → unified `related` with bidirectional flag
**Decision:** Add `--bidirectional/--no-bidirectional` flag, default to bidirectional=True

Commands to remove:
- [ ] `related-resource` - unified `related` now supports bidirectional

Example to add to help:
```
# Directional: show only outgoing links from source
ai-lessons recall related LSN... --no-bidirectional

# Bidirectional (default): show links in either direction
ai-lessons recall related LSN...
```

### `list-chunks` → already supported
**Decision:** Delete. `list --type chunk --chunk-parent RES...` already works.

Commands to remove:
- [ ] `list-chunks` - use `recall list --type chunk --chunk-parent <id>`

---

## Implementation Plan

### Phase 1: Database Migration (rule_links → edges)
**Files:** core.py, schema.py

| Function | Lines | Change |
|----------|-------|--------|
| `suggest_rule()` | 2662 (SQL at 2724, 2731) | rule_links INSERT → edges INSERT |
| `get_rule()` | 2806 (SQL at 2840, 2847) | rule_links SELECT → edges SELECT |
| `link_to_rule()` | 2949 (SQL at 2977) | rule_links INSERT → edges INSERT |
| `unlink_from_rule()` | 2987 (SQL at 3012, 3017) | rule_links DELETE → edges DELETE |
| schema.py | 156-161, 208 | Comment out rule_links table + index |

**SQL Changes:**
```sql
-- Before (rule_links)
INSERT INTO rule_links (rule_id, target_id, target_type) VALUES (?, ?, ?)
SELECT target_id FROM rule_links WHERE rule_id = ? AND target_type = ?
DELETE FROM rule_links WHERE rule_id = ? AND target_id = ?

-- After (edges)
INSERT INTO edges (from_id, from_type, to_id, to_type, relation) VALUES (?, 'rule', ?, ?, 'related_to')
SELECT to_id FROM edges WHERE from_id = ? AND from_type = 'rule' AND to_type = ?
DELETE FROM edges WHERE from_id = ? AND from_type = 'rule' AND to_id = ?
```

### Phase 2: CLI - Implement New Features
**Files:** recall.py, contribute.py

1. **Add `--bidirectional/--no-bidirectional` to `related` command** (recall.py line 321)
   - Default: bidirectional=True
   - Current: lessons only show outgoing edges via `core.get_related()`
   - Need to also query `WHERE to_id=entity_id` when bidirectional=True

2. **Rename `add-resource` → `import`** (contribute.py line 418)
   - Change decorator from `@contribute.command("add-resource")` to `@contribute.command("import")`

3. **Unify `add-lesson` + `suggest-rule` → `add --type lesson|rule`**
   - Current `add-lesson` at line 23, `suggest-rule` at line 631
   - **Gotcha:** Current code has `def add()` for add-lesson - rename to `def add_lesson()` first
   - Create new unified `def add()` with `--type` option (choices: lesson, rule)
   - For `--type rule`: print "Rule submitted for admin review/approval"
   - Use type-prefixed options: `--lesson-*` and `--rule-*`

### Phase 3: CLI - Remove Redundant Commands
**File:** recall.py (9 deletions)
| Line | Command | Function |
|------|---------|----------|
| 198 | search-lesson | `search_lesson()` |
| 499 | search-resources | `search_resources_cmd()` |
| 553 | show-resource | `show_resource()` |
| 562 | show-chunk | `show_chunk()` |
| 435 | related-lesson | `related_lesson()` |
| 571 | related-resource | `related_resource()` |
| 761 | list-resources | `list_resources_cmd()` |
| 811 | list-chunks | `list_chunks_cmd()` |
| 894 | show-rule | `show_rule()` |

**File:** contribute.py (8 deletions)
| Line | Command | Function |
|------|---------|----------|
| 82 | update-lesson | `update_lesson()` |
| 217 | delete-lesson | `delete_lesson()` |
| 291 | link-lesson | `link_lesson()` |
| 307 | unlink-lesson | `unlink_lesson()` |
| 318 | link-resource | `link_resource()` |
| 350 | unlink-resource | `unlink_resource()` |
| 599 | refresh-resource | `refresh_resource()` |
| 613 | delete-resource | `delete_resource()` |

All have `warn_deprecation()` calls - safe to delete.

### Phase 4: Admin Commands
**File:** admin.py
- `reindex-resources` (line 182) → `reindex`
- `clear-resources` (line 393) → `clear`

### Phase 5: Help Cleanup
- ~~Fix root help duplicate listing~~ Already fine (has `\b` marker)
- ~~Add `\b` markers to preserve example formatting~~ Already present where needed
- **Actually needed:** Just verify examples render correctly after changes

---

## Verification Checklist

- [ ] All rule linking uses `edges` table
- [ ] `ai-lessons recall --help` - no deprecated commands
- [ ] `ai-lessons contribute --help` - no deprecated commands
- [ ] `ai-lessons contribute add --type lesson` works
- [ ] `ai-lessons contribute add --type rule` works + shows approval message
- [ ] `ai-lessons contribute import` works (was add-resource)
- [ ] `ai-lessons recall related LSN... --no-bidirectional` works
- [ ] All tests pass
