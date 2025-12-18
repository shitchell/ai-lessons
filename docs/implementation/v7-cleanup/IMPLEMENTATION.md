# v7-cleanup: Code Review Fixes

Based on CODE_REVIEW_GENERAL.md and CODE_REVIEW_TAILORED.md findings.

**Excluded from this cleanup:**
- Migration logic changes
- God object refactoring (core.py split, search.py split, Config split)
- Test suite creation (separate effort)

---

## Pre-Implementation: Discussion Items (RESOLVED)

### A. ID Class Design ✅

**Decision:** Option 3 - Full ID class

Implementation will include:
- `__repr__` / `__str__` for display (truncated vs full)
- `type` property (extracts LSN/RES/RUL prefix)
- `generate()` class method (consolidates generation logic)
- `parse()` for validation
- Map of type prefixes

### B. Duplicated Embedding Logic ✅

**Decision:** Option 3 - Generic EntityTableMap

Implementation will unify embedding + tag table mappings:
```python
ENTITY_TABLE_MAP = {
    'lesson': {
        'table': 'lessons',
        'embeddings': ('lesson_embeddings', 'lesson_id'),
        'tags': ('lesson_tags', 'lesson_id'),
    },
    'resource': {...},
    'rule': {...},
}
```

This addresses both DRY violations (embedding tables + tag tables) in one contiguous structure.

---

## Chunk 1: Quick Fixes (Constants & Naming)

**Estimated tokens:** ~15k

1. Add `CHARS_PER_TOKEN_CONSERVATIVE = 3.5` constant (core.py:396)
2. Remove duplicate `update_rule` function (core.py:2707 vs 2991)
3. Fix abbreviated names in search.py:
   - `kw_boost` → `keyword_boost`
   - `kw_raw` → `keyword_raw`
4. Fix generic loop variable names in db.py:373-413:
   - `row` in nested loops → `chunk_row`, `edge_row`, etc.
5. Fix single-letter parameter in search.py:335:
   - `k` → `steepness`
6. Fix float comparison in search.py:857-859:
   - `if version_score == 0.0` → `if math.isclose(version_score, 0.0)`
7. Add None check to `_truncate_for_embedding` (core.py:396-424)

**Verification:** `python -c "from ai_lessons import core, search, db; print('imports ok')"`

---

## Chunk 2: State Awareness Fixes

**Estimated tokens:** ~20k

1. **db.py dimension check** (lines 109-135):
   - If `row` is None (no dimensions in meta), raise explicit error instead of silent return
   - Message: "Vector table exists but dimensions not in meta - database may be corrupted. Use init_db(force=True) to recreate."

2. **chunking.py oversized handling** (lines 412-450):
   - After `_chunk_by_characters` fallback, check if still oversized
   - If so, add `"failed_to_split"` to chunk.warnings
   - Log warning with chunk index and size

**Verification:** Manual test with edge cases

---

## Chunk 3: DRY - Table Mappings

**Estimated tokens:** ~25k

1. Extract `EMBEDDING_TABLE_MAP` to module constant (pending discussion decision)
2. Extract `TAG_TABLE_MAP` to module constant:
   ```python
   TAG_TABLE_MAP = {
       'lesson': ('lesson_tags', 'lesson_id'),
       'resource': ('resource_tags', 'resource_id'),
       'rule': ('rule_tags', 'rule_id'),
   }
   ```
3. Update `_save_tags`, `_delete_tags`, `_get_tags` to use constant
4. Update `_store_embedding`, `_delete_embedding` to use constant

**Verification:** Run existing functionality, ensure tags/embeddings still work

---

## Chunk 4: DRY - Search Logic

**Estimated tokens:** ~30k

1. **Consolidate keyword scoring:**
   - Merge `_keyword_score()` and `_keyword_score_with_tags()` into single function
   - Add optional `tags` parameter with default `None`

2. **Extract common filter building:**
   - Create `_build_common_filter_clauses()` for shared logic between lesson/resource filters

3. **Extract common row processing:**
   - Create `_process_row_common()` for shared version scoring and metadata fetching

**Verification:** Run search tests, verify scoring unchanged

---

## Chunk 5: Error Handling

**Estimated tokens:** ~30k

1. **Summary generation** (summaries.py:189-199):
   - Replace `print()` with proper `logging.warning()`
   - Use more specific exception handling (not bare `Exception`)

2. **Input validation for public APIs** (core.py):
   - `add_lesson()`: Validate title/content not empty
   - `add_resource()`: Validate path exists (for file resources)
   - `suggest_rule()`: Validate required fields

3. **Links error context** (links.py:116-128):
   - Return `Optional[Tuple[str, str]]` or raise specific `LinkResolutionError`
   - Distinguish "not found" from "error occurred"

4. **Import error standardization** (embeddings.py, summaries.py):
   - Standardize on `ImportError` with helpful message for all optional dependencies

**Verification:** Test error paths manually

---

## Chunk 6: API Key Validation

**Estimated tokens:** ~20k

1. **OpenAI backend** (embeddings.py):
   - Add `_validate_api_key()` method
   - Test against models endpoint or similar 0-token/0-cost endpoint
   - Call during `__init__` or first use
   - Raise clear error if invalid

2. **Anthropic backend** (summaries.py if applicable):
   - Same pattern

**Verification:** Test with valid key, invalid key, missing key

---

## Chunk 7: Performance & Safety

**Estimated tokens:** ~35k

1. **N+1 query fix** (search.py:620-664):
   - Batch fetch tags/contexts for all results in one query
   - Use `WHERE lesson_id IN (?, ?, ...)` pattern

2. **Embedder thread safety** (embeddings.py:144-154):
   - Add `threading.Lock` around global `_embedder` initialization
   - Or use `threading.local()` for thread-local storage

3. **Max recursion depth for chunking** (chunking.py:412-450):
   - Add `max_depth` parameter to `_handle_oversized()`
   - Default to 3 levels
   - Raise or warn if exceeded

4. **Rate limiting for LLM calls** (summaries.py):
   - Add simple rate limiter (e.g., max N calls per minute)
   - Or add `time.sleep()` between calls

**Verification:** Performance test with larger datasets

---

## Chunk 8: Documentation

**Estimated tokens:** ~20k

1. **Add docstrings:**
   - `core.py:260-262` - `_generate_id()`
   - `db.py:30-41` - `_get_connection()`
   - Other key helper functions

2. **Document scoring rationales** (search.py:22-44):
   - Add comments explaining WHY each constant has its value
   - E.g., "SIGMOID_STEEPNESS=6.0 chosen to give scores 0.7-0.95 for distances < 1.0"

3. **Add API key warning to docs:**
   - In README or config docs, warn against storing plain API keys
   - Recommend `${ENV_VAR}` syntax

4. **Standardize docstring style:**
   - Use Google-style throughout

**Verification:** Manual review

---

## Chunk 9: Dataclass Validation

**Estimated tokens:** ~15k

1. Add `__post_init__` validation to dataclasses:
   - `SearchResult`: Validate `0.0 <= score <= 1.0`
   - `Chunk`: Validate `token_count >= 0`
   - `ChunkingConfig`: Validate `min_chunk_size < max_chunk_size`

**Verification:** Test with invalid values, ensure errors raised

---

## Final Verification

After all chunks complete:
1. Run full import test
2. Run any existing tests
3. Manual smoke test of CLI commands
4. Review git diff for unintended changes

---

**STOP**: Before continuing work after a compactification, DO NOT mark re-reading this document as complete. Repeat, DO NOT mark the "READ .../IMPLEMENTATION.md BEFORE DOING ANYTHING ELSE" item as complete. That todo item is intended to help ensure that this document is re-read across compactifications until this cleanup process is complete. DO NOT mark that todo item as complete until this implementation is complete.

When the system prompts you to create a summary for the next session, include a **STRONG instruction** to RE-READ THIS DOCUMENT (`docs/implementation/v7-cleanup/IMPLEMENTATION.md`) before doing anything else.

---

**WORK UNTIL COMPLETE**: Do NOT prompt the user for feedback, questions, or input until ALL chunks have been completed and ALL todo items are marked done. Work autonomously through each chunk in order, running verification tests after each chunk, and only engage the user once the final verification is complete.
