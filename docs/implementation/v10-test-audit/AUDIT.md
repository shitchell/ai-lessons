# Test Infrastructure Audit Report

## Executive Summary

The test infrastructure has several critical issues stemming from the recently fixed `fast_config` fixtures. Many tests are using `temp_config` (slow, with real embeddings) when they should be using `fast_config` (fast, with mocked embeddings). The fast fixtures (`fast_sample_lessons`, `fast_populated_db`) are **completely unused** across all test files.

## 1. Fixture Usage Analysis

### Current State

| Test File | Uses `temp_config` | Uses `fast_config` | Total Tests |
|-----------|-------------------|-------------------|-------------|
| `test_core.py` | 38 tests | 0 tests | 38 |
| `test_edges.py` | 17 tests | 0 tests | 17 |
| `test_info.py` | 19 tests | 6 tests | 25 |
| `test_search.py` | 0 tests | 0 tests | 38 (uses manual config) |
| `test_chunking.py` | 0 tests | 0 tests | 39 (no DB needed) |
| `test_chunk_ids.py` | 0 tests | 0 tests | 8 (no DB needed) |
| `test_db.py` | 0 tests | 0 tests | 2 (version checks) |

### Fast Fixture Usage

**CRITICAL**: The following fixtures in `conftest.py` are **NEVER USED**:
- `fast_sample_lessons` (lines 321-338)
- `fast_populated_db` (lines 342-347)

The `fast_config` fixture is used only in `test_info.py` (19/25 tests).

### Slow Fixture Usage

**PERFORMANCE ISSUE**: 55+ tests use `temp_config` when they could use `fast_config`:
- `test_core.py`: All 38 tests use `temp_config`
- `test_edges.py`: All 17 tests use `temp_config`
- `test_info.py`: 6 tests still use `temp_config`

### test_search.py Special Case

**INCONSISTENCY**: `test_search.py` manually creates its own config instead of using fixtures:

```python
# Lines 5-11
def _temp_config():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = Config(
            db_path=Path(tmpdir) / "test.db",
            embedding=EmbeddingConfig(...),
            search=SearchConfig(),
        )
        init_db(config)
        yield config
```

This pattern bypasses the conftest fixtures entirely, meaning it **always uses real embeddings** and is slow.

## 2. Consistency Issues

### Import Patterns

**MOSTLY CONSISTENT**: All test files use the same import pattern:
```python
from ai_lessons import core
```

No inconsistencies found here.

### Fixture Patterns

**INCONSISTENT**:
- `test_info.py`: Uses `fast_config` correctly (lines 18-339)
- `test_core.py`, `test_edges.py`: Use `temp_config` (slow)
- `test_search.py`: Uses manual config creation (also slow)

### Patching Patterns

**GOOD**: `test_info.py` shows the correct pattern for CLI tests:
```python
def test_tags_empty(self, fast_config, monkeypatch):
    monkeypatch.setattr("ai_lessons.core.get_config", lambda: fast_config)
```

This is consistent across all CLI tests in that file.

## 3. Robustness Analysis

### Tests That Might Pass for Wrong Reasons

**test_core.py**:
1. Line 48-51: `test_get_nonexistent_lesson` - Could be improved with explicit assertion message
2. Line 311-312: `test_get_nonexistent_resource` - Same as above
3. Line 407-408: `test_get_nonexistent_rule` - Same as above

### Weak Assertions

**test_core.py**:
1. Line 25-26: `test_add_lesson` - Only checks ID is not None and has length
   ```python
   assert lesson_id is not None
   assert len(lesson_id) > 0
   ```
   **Better**: Actually retrieve the lesson and verify fields

2. Line 111: `test_recall_finds_lesson` - Weak match check
   ```python
   assert "jira" in results[0].title.lower() or "workflow" in results[0].title.lower()
   ```
   **Better**: Check specific expected title or use helpers

### Missing Assertions

**test_edges.py**:
1. Line 214: `test_delete_lesson_cascades_edges` - Has a comment noting edges may persist
   ```python
   # Edges table doesn't have FK CASCADE, so edges may persist
   # This is acceptable as orphan edges don't affect functionality
   ```
   **Issue**: Test doesn't actually assert anything about edge cleanup

## 4. Conftest Fixture Analysis

### Fixtures Actually Used

| Fixture | Used By | Status |
|---------|---------|--------|
| `temp_dir` | `temp_config`, `fast_config` | ✅ Used (indirectly) |
| `temp_config` | `test_core.py`, `test_edges.py`, `test_info.py` | ✅ Used (55+ tests) |
| `fast_config` | `test_info.py` | ✅ Used (19 tests) |
| `mock_embedder` | - | ❌ Never used directly |
| `patched_embedder` | `fast_config` | ✅ Used (indirectly) |
| `sample_lessons` | `populated_db` | ✅ Used (indirectly) |
| `sample_resources` | `populated_db` | ✅ Used (indirectly) |
| `sample_rules` | `populated_db` | ✅ Used (indirectly) |
| `populated_db` | - | ❌ Never used |
| `fast_sample_lessons` | `fast_populated_db` | ❌ Never used |
| `fast_populated_db` | - | ❌ Never used |

### Fixtures That Should Exist But Don't

Based on the README documentation (lines 46-56), the following fixtures are documented but analyzed:
- All documented fixtures exist
- However, the "fast" versions are completely unused

### Fixture Hierarchy Issues

The hierarchy makes sense, but there's a disconnect:
```
temp_dir
├── temp_config (real embeddings)
│   ├── sample_lessons
│   ├── sample_resources
│   ├── sample_rules
│   └── populated_db
└── fast_config (mock embeddings)
    ├── fast_sample_lessons
    └── fast_populated_db
```

**ISSUE**: Tests using `populated_db` will be slow because it depends on `temp_config`, but there's a `fast_populated_db` that nobody uses.

## 5. Specific Improvements Needed

### CRITICAL Priority

1. **Convert test_core.py to use fast_config** (38 tests)
   - All tests in this file could use `fast_config`
   - Would dramatically speed up test suite
   - Tests don't require real embeddings for CRUD operations

2. **Convert test_edges.py to use fast_config** (17 tests)
   - Graph operations don't need real embeddings
   - All tests can be converted

3. **Fix test_search.py to use fixtures** (38 tests)
   - Currently manually creates config
   - Should use `fast_config` for non-embedding tests
   - Some tests genuinely test search scoring and might need real embeddings

4. **Remove or use fast_populated_db fixture**
   - Either delete it (if not needed) or write tests that use it
   - Same for `fast_sample_lessons`

### IMPORTANT Priority

5. **Convert remaining test_info.py tests to fast_config** (6 tests)
   - Lines 174-183: `test_tags_empty` uses `fast_config` ✅
   - Lines 221-230: `test_confidence_levels` uses `fast_config` (should be fast_config)
   - Other info tests should be converted

6. **Improve assertion specificity**
   - Use `assert_lesson_matches` helper from `helpers.py`
   - Use `assert_resource_matches` helper
   - Use `assert_rule_matches` helper

7. **Fix test_edges.py cascade test**
   - Line 185-214: `test_delete_lesson_cascades_edges`
   - Actually assert edge cleanup behavior

### NICE-TO-HAVE Priority

8. **Add markers to slow tests**
   - Mark tests that genuinely need real embeddings with `@pytest.mark.embeddings`
   - Mark slow tests with `@pytest.mark.slow`

9. **Use helper factories more**
   - Replace manual `core.add_lesson()` calls with `make_lesson()`
   - Replace manual `core.add_resource()` calls with `make_resource()`
   - Replace manual `core.suggest_rule()` calls with `make_rule()`

10. **Add integration tests using populated_db**
    - Or remove the fixture if it's not needed
    - Document why fast vs slow populated fixtures exist

## 6. Anti-Patterns Identified

### ❌ Manual config creation
```python
# test_search.py
@pytest.fixture
def _temp_config():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = Config(...)
        init_db(config)
        yield config
```
**FIX**: Use `fast_config` from conftest

### ❌ Weak ID assertions
```python
assert lesson_id is not None
assert len(lesson_id) > 0
```
**FIX**: Actually fetch and verify the entity

### ❌ Using temp_config for non-embedding tests
```python
def test_link_lessons(self, temp_config):  # Doesn't need real embeddings!
    id1 = core.add_lesson(...)
    id2 = core.add_lesson(...)
    core.link_lessons(id1, id2, "related_to", config=temp_config)
```
**FIX**: Use `fast_config` instead

## 7. Recommendations by File

### test_core.py (38 tests)
- **Switch all tests to `fast_config`** - None require real embeddings
- Use helper functions (`make_lesson`, `assert_lesson_matches`)
- Improve weak ID assertions in lines 25-26, 235-236, 357-358

**Estimated speedup**: 10-30x faster

### test_edges.py (17 tests)
- **Switch all tests to `fast_config`** - Graph operations don't need embeddings
- Fix cascade test (line 185-214) to actually assert behavior
- Consider using helper factories

**Estimated speedup**: 10-30x faster

### test_info.py (25 tests)
- **Switch remaining 6 tests to `fast_config`**
- Already mostly using fast_config correctly ✅
- Good example for other test files to follow

### test_search.py (38 tests)
- **Replace manual config creation with `fast_config`**
- **ANALYZE**: Some tests might genuinely need real embeddings for search scoring
- Consider splitting into:
  - Fast tests (keyword matching, version scoring, etc.)
  - Slow tests (actual semantic search with real embeddings)

**Estimated speedup**: 10-30x for most tests

### conftest.py
- **Document or remove unused fixtures**: `fast_sample_lessons`, `fast_populated_db`, `populated_db`
- Consider adding a `@pytest.fixture` for `fast_temp_config` alias if naming is confusing
- Document which tests should use which fixture in docstrings

## 8. Priority Action Items

### Week 1 (Critical)
1. Convert `test_core.py` to use `fast_config` (38 tests → 10-30x speedup)
2. Convert `test_edges.py` to use `fast_config` (17 tests → 10-30x speedup)
3. Fix `test_search.py` manual config creation

### Week 2 (Important)
4. Convert remaining `test_info.py` tests to `fast_config`
5. Add `@pytest.mark.embeddings` to tests that truly need real embeddings
6. Decide on unused fixtures (remove or use)

### Week 3 (Nice-to-have)
7. Replace manual entity creation with helper factories
8. Improve weak assertions using helper functions
9. Fix cascade edge test in `test_edges.py`

## 9. Estimated Performance Impact

**Current state**: ~70 tests using real embeddings unnecessarily

**After fixes**: ~5-10 tests using real embeddings (only where needed)

**Estimated total speedup**: 5-10x faster test suite
- CRUD operations: 30x faster
- Graph operations: 30x faster
- Info/metadata operations: 30x faster
- Search operations: 2-3x faster (some need real embeddings)

## 10. Summary Statistics

- **Total test files**: 7
- **Total tests**: ~167
- **Tests using slow config unnecessarily**: ~55
- **Tests using fast config correctly**: 19
- **Unused fixtures**: 3 (fast_sample_lessons, fast_populated_db, populated_db)
- **Anti-patterns found**: 3 (manual config, weak assertions, wrong fixture)
- **Files needing major updates**: 3 (test_core, test_edges, test_search)
