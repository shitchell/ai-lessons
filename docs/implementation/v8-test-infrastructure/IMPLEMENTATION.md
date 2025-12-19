# v8-test-infrastructure: Test Suite Improvements

Based on test coverage analysis findings. Focus on test infrastructure, not comprehensive test coverage.

**Scope:**
- Centralized fixtures in conftest.py
- Test helpers module
- Pre-populated database fixtures
- Mock embedder for fast tests
- Pytest markers configuration
- Migration test placeholder (deferred until v1.0.0)

**Excluded from this effort:**
- Comprehensive test coverage for all modules
- CLI command tests
- Integration/E2E test suites
- Performance benchmarks

---

## Chunk 1: Centralized Fixtures (conftest.py)

**Estimated tokens:** ~20k

1. **Create `tests/conftest.py`** with:
   - `MockEmbedder` class - deterministic vectors without loading models
   - `mock_embedder` fixture - direct access to mock
   - `patched_embedder` fixture - patches global embedder
   - `temp_dir` fixture - isolated temp directory
   - `temp_config` fixture - standard config (real embeddings)
   - `fast_config` fixture - config with mocked embeddings

2. **Pre-populated fixtures:**
   - `sample_lessons` - 3 lessons with varied tags/confidence
   - `sample_resources` - 2 resources (doc type)
   - `sample_rules` - 2 rules (1 approved, 1 pending)
   - `populated_db` - combines all with relationships
   - `fast_*` variants using mocked embeddings

**Verification:** `pytest tests/conftest.py --collect-only` (ensure fixtures are discovered)

---

## Chunk 2: Test Helpers Module

**Estimated tokens:** ~15k

1. **Create `tests/helpers.py`** with:
   ```python
   # Assertion helpers
   def assert_lesson_matches(lesson, expected: dict) -> None
   def assert_resource_matches(resource, expected: dict) -> None
   def assert_search_result_valid(result) -> None

   # Factory helpers
   def make_lesson(config, **overrides) -> str
   def make_resource(config, **overrides) -> str
   def make_rule(config, **overrides) -> str

   # Database helpers
   def count_rows(config, table: str) -> int
   def get_all_ids(config, table: str) -> list[str]
   def clear_table(config, table: str) -> None
   ```

2. **Document usage patterns** in docstrings

**Verification:** Import helpers in Python REPL

---

## Chunk 3: Pytest Configuration

**Estimated tokens:** ~10k

1. **Update `pyproject.toml`** pytest section:
   ```toml
   [tool.pytest.ini_options]
   testpaths = ["tests"]
   asyncio_mode = "auto"
   markers = [
       "unit: Unit tests (fast, isolated)",
       "integration: Integration tests (may use real DB)",
       "slow: Tests that load ML models or make API calls",
       "embeddings: Tests that require real embedding models",
   ]
   filterwarnings = [
       "ignore::pytest.PytestConfigWarning",
   ]
   ```

2. **Add `pytest-cov` to dev dependencies** (optional)

**Verification:** `pytest --markers` shows custom markers

---

## Chunk 4: Migration Test Placeholder

**Estimated tokens:** ~5k

1. **Create `tests/test_db.py`** with placeholder:
   ```python
   """Database tests including migration testing.

   Migration tests are deferred until v1.0.0 to avoid premature
   optimization of the migration path.
   """

   import pytest
   from importlib.metadata import version
   from packaging.version import Version


   class TestMigrations:
       """Placeholder for database migration tests."""

       def test_migration_tests_needed_after_v1(self):
           """Fail if version >= 1.0.0 to remind us to implement migration tests."""
           current = Version(version("ai-lessons"))
           if current >= Version("1.0.0"):
               pytest.fail(
                   "Version >= 1.0.0 detected. "
                   "Please implement actual database migration tests now. "
                   "See docs/implementation/v8-test-infrastructure/IMPLEMENTATION.md"
               )
   ```

2. **Add `packaging` to dev dependencies** if not present

**Verification:** `pytest tests/test_db.py -v`

---

## Chunk 5: Remove Duplicate Fixtures

**Estimated tokens:** ~15k

1. **Update `tests/test_core.py`:**
   - Remove local `temp_config` fixture (now in conftest.py)
   - Imports should just work via pytest discovery

2. **Update `tests/test_edges.py`:**
   - Remove local `temp_config` fixture
   - Ensure tests still pass

3. **Update `tests/test_search.py`:**
   - Check for any local fixtures to consolidate

4. **Update `tests/test_chunking.py`:**
   - Check for any local fixtures to consolidate

**Verification:** `pytest tests/ -v` - all tests pass

---

## Chunk 6: Documentation

**Estimated tokens:** ~10k

1. **Create `tests/README.md`** with:
   - Overview of test structure
   - Available fixtures and when to use each
   - How to run fast vs full tests
   - Marker usage examples
   - Guidelines for writing new tests

**Verification:** Manual review

---

## Final Verification

After all chunks complete:
1. Run full test suite: `pytest tests/ -v`
2. Run with markers: `pytest tests/ -m "not slow" -v`
3. Verify fixture discovery: `pytest --fixtures tests/`
4. Check no duplicate fixtures remain
5. Review git diff for unintended changes

---

**STOP**: Before continuing work after a compactification, DO NOT mark re-reading this document as complete. Repeat, DO NOT mark the "READ .../IMPLEMENTATION.md BEFORE DOING ANYTHING ELSE" item as complete. That todo item is intended to help ensure that this document is re-read across compactifications until this cleanup process is complete. DO NOT mark that todo item as complete until this implementation is complete.

When the system prompts you to create a summary for the next session, include a **STRONG instruction** to RE-READ THIS DOCUMENT (`docs/implementation/v8-test-infrastructure/IMPLEMENTATION.md`) before doing anything else.

---

**WORK UNTIL COMPLETE**: Do NOT prompt the user for feedback, questions, or input until ALL chunks have been completed and ALL todo items are marked done. Work autonomously through each chunk in order, running verification tests after each chunk, and only engage the user once the final verification is complete.
