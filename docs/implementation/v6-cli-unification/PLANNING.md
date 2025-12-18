# v6-cli-unification: Planning Document

**Created**: 2025-12-18
**Status**: Implementation Ready

This document captures all ideas discussed during planning, including those we accepted, discarded, and deferred.

---

## Ideas Discussed

### 1. Type-Prefixed IDs

Use 3-character prefixes on all entity IDs: `LSN` (lesson), `RES` (resource), `RUL` (rule). Chunks inherit from resources: `RES01KCP....0`.

**Status**: Accepted

**Rationale**: Instant type detection from the ID string without database lookups. Eliminates ambiguity. Self-documenting in logs and output. Simplifies the logic for unified commands.

---

### 2. Scripts as Separate Entity Type

Treat scripts as a completely separate entity type with their own table, ID prefix (`SCR`), and dedicated commands.

**Status**: Discarded

**Rationale**: Scripts ARE resources - they're stored in the resources table with `type='script'`. Using `--resource-type script` to filter keeps the logic simpler and matches the existing data structure. No schema changes needed.

---

### 3. Namespaced Options

Instead of showing/hiding options based on `--type`, always show all options with type prefixes: `--lesson-confidence-min`, `--resource-version`, `--rule-pending`.

**Status**: Accepted

**Rationale**: Avoids conditional logic in Click (which doesn't handle dynamic options well) and allows us to retain simpler unified commands. If you use `--type script --lesson-confidence-min high`, the lesson filter just applies to an empty set - no special handling needed.

---

### 4. --type Flag for Filtering

Add `--type lesson|resource|chunk|rule` to unified commands to filter results to specific entity types.

**Status**: Accepted

**Rationale**: Cleaner than having 4x more subcommands. Provides flexibility to search one type or multiple types with a single command.

---

### 5. Any-to-Any Linking

Allow any entity type to link to any other entity type via the `edges` table (lesson↔lesson, lesson↔resource, rule↔chunk, etc.).

**Status**: Accepted

**Rationale**: The `edges` table schema already supports arbitrary `from_type`/`to_type` combinations. Just needs CLI exposure via unified `link` command. Enables rich knowledge graphs without artificial restrictions.

---

### 6. Unified Commands vs Type-Specific Subcommands

Use single commands like `search`, `show`, `list`, `delete` instead of `search-lesson`, `search-resource`, `show-rule`, etc.

**Status**: Accepted

**Rationale**: Having 4x more subcommands feels messy. It becomes visually difficult - at least for humans - to filter out the commands you want. Overwhelming when there are many similar commands. Unified commands with `--type` filtering is cleaner.

---

### 7. Type-Specific Subcommands (search-lesson, search-resource, etc.)

Keep separate subcommands for each entity type with their own specific options.

**Status**: Discarded

**Rationale**: See above - too many similar commands becomes overwhelming. Unified approach with namespaced options is cleaner.

---

### 8. Backwards Compatibility / Hidden Aliases

Keep old command names as hidden aliases that emit deprecation warnings.

**Status**: Discarded

**Rationale**: We're in rapid iteration stage. No users yet. No deployed implementation to remain compatible with. Clean break is simpler.

---

### 9. Complex Migration for Type-Prefixed IDs

Write migration code to update all existing IDs in all tables, handling foreign keys, vector tables, etc.

**Status**: Discarded

**Rationale**: Rapid iteration. No users with data to preserve. The complexity of migrating 13+ tables with FK constraints isn't worth it when we can just recreate the database. Note: There is still a cost associated with re-importing resources and regenerating summaries (API cost), but marginal API cost is acceptable for rapid iteration.

---

### 10. Clean Slate Migration

v12 migration simply refuses to migrate and instructs user to delete and recreate database.

**Status**: Accepted

**Rationale**: See above. Simple, no migration bugs, clean break. "I'm sorry Dave, I can't do that."

---

### 11. Keep Separate add-* Commands

Keep `add-lesson`, `add-resource`, `suggest-rule` as separate commands rather than unifying into `add --type`.

**Status**: Deferred

**Rationale**: We have a solid plan, and continuing to rework it was becoming exhausting. The options for each type differ significantly (lesson has contexts/confidence/source, resource has paths/chunking/versions, rule has rationale). Easy to revisit later. Note: `suggest-rule` remains separate regardless because it requires human approval - it cannot be "added" by the agent, only suggested.

---

### 12. Unified add Command

Single `add` command with `--type` flag and all options from all types.

**Status**: Deferred

**Rationale**: See above. Want to revisit this in the future, but deferred to avoid further planning churn.

---

### 13. Type-Dependent Option Visibility in Click

Dynamically show/hide options based on `--type` value (e.g., only show `--confidence-min` when `--type lesson`).

**Status**: Discarded

**Rationale**: Click doesn't handle this elegantly - options are defined at decoration time, not runtime. Would require complex workarounds. Namespaced options solve this more cleanly.

---

### 14. Display Formatter Truncation [:12] → [:15]

Update ID truncation in display functions from 12 to 15 characters to accommodate 3-character prefix while keeping the same number of visible ULID characters.

**Status**: Accepted

**Rationale**: Made sense to keep the displayed ULID characters the same as in the current working iteration. The truncation approach itself is a bit questionable but it's working, so no reason to change it.

---

### 15. Fix edges Table CHECK Constraint

Current schema is missing 'rule' in the CHECK constraint for `from_type` and `to_type`.

**Status**: Accepted

**Rationale**: It's a bug. Fixing bugs that are conducive to our end goal is good.

---

### 16. Unified list --type chunk (requiring --chunk-parent)

Use `list --type chunk --chunk-parent RES...` instead of keeping `list-chunks` as a separate command.

**Status**: Accepted

**Rationale**: Consistency with other unified commands. The agent suggested keeping it separate because it's "awkward" needing a parent ID, but it's not actually awkward - chunks inherently belong to a resource, so requiring the parent is logical.

---

### 17. Helper Functions (list_lessons, list_rules, update_resource)

Add new core functions to support unified commands.

**Status**: Accepted

**Rationale**: Simplifies the logic and makes the code cleaner. Keeping functions under ~50 lines makes the logic easier to read and follow.

---

### 18. Smart Error Messages

When operations don't apply to a type, show helpful guidance instead of generic errors. E.g., "Chunks are updated via their parent resource. Use `refresh RES...`"

**Status**: Accepted

**Rationale**: More data/context is often helpful, especially when things go wrong. Errors benefit from verbosity - not to the point of being overwhelming and pollutive, but enough to guide the user toward the right action.

---

### 19. Conceptual Command Groupings (Create, Update, Discovery)

Organize commands into conceptual groups:
- **Create**: add-lesson, add-resource, suggest-rule
- **Update**: update, refresh, delete, link, unlink
- **Discovery**: search, show, list, related

**Status**: Accepted (loosely)

**Rationale**: A way of thinking about the commands to see if it shines a light on patterns that might help simplify implementation logic. If the groupings don't aid in simplifying logic, not pressed about keeping the conceptualization - but it might be nice to group them that way in help output if it aids in finding the right subcommand.

---

### 20. update_rule() Core Function

Add a core function to update rule metadata (title, content, rationale, tags).

**Status**: Accepted

**Rationale**: Needed for unified `update` command. The function exists conceptually but wasn't exposed in CLI.

---

## Summary

| Idea | Status |
|------|--------|
| Type-prefixed IDs | Accepted |
| Scripts as separate entity | Discarded |
| Namespaced options | Accepted |
| --type flag for filtering | Accepted |
| Any-to-any linking | Accepted |
| Unified commands | Accepted |
| Type-specific subcommands | Discarded |
| Backwards compatibility | Discarded |
| Complex migration | Discarded |
| Clean slate migration | Accepted |
| Keep separate add-* | Deferred |
| Unified add command | Deferred |
| Type-dependent option visibility | Discarded |
| Display truncation [:15] | Accepted |
| Fix edges CHECK constraint | Accepted |
| Unified list --type chunk | Accepted |
| Helper functions | Accepted |
| Smart error messages | Accepted |
| Conceptual groupings | Accepted (loosely) |
| update_rule() function | Accepted |
