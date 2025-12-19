# Test Suite

This directory contains the test suite for ai-lessons.

## Quick Start

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_core.py

# Run tests matching a pattern
pytest -k "test_add_lesson"
```

## Test Structure

```
tests/
├── conftest.py       # Shared fixtures (temp_config, mock_embedder, etc.)
├── helpers.py        # Test helper utilities
├── test_core.py      # Core CRUD and search tests
├── test_edges.py     # Graph relationship tests
├── test_search.py    # Search scoring tests
├── test_chunking.py  # Document chunking tests
├── test_chunk_ids.py # Chunk ID generation/parsing tests
└── test_db.py        # Database tests (migration placeholder)
```

## Fixtures

All fixtures are defined in `conftest.py` and automatically available to all tests.

### Database Fixtures

| Fixture | Description | Speed |
|---------|-------------|-------|
| `temp_config` | Fresh database with real embeddings | Slow |
| `fast_config` | Fresh database with mock embeddings | Fast |
| `temp_dir` | Isolated temporary directory | Fast |

### Pre-populated Fixtures

| Fixture | Description | Dependencies |
|---------|-------------|--------------|
| `sample_lessons` | 3 lessons with varied tags | `temp_config` |
| `sample_resources` | 2 doc resources | `temp_config` |
| `sample_rules` | 2 rules (1 approved) | `temp_config`, `sample_lessons` |
| `populated_db` | All of the above with relationships | All above |
| `fast_sample_lessons` | 2 lessons with mock embeddings | `fast_config` |
| `fast_populated_db` | Fast version of populated_db | `fast_config` |

### Mock Fixtures

| Fixture | Description |
|---------|-------------|
| `mock_embedder` | MockEmbedder instance (direct access) |
| `patched_embedder` | Patches global embedder with mock |

## Helpers

Import helpers from `tests.helpers`:

```python
from tests.helpers import (
    # Assertion helpers
    assert_lesson_matches,
    assert_resource_matches,
    assert_rule_matches,
    assert_search_result_valid,

    # Factory helpers
    make_lesson,
    make_resource,
    make_rule,

    # Database helpers
    count_rows,
    get_all_ids,
    clear_table,
    table_exists,
    get_table_columns,
)
```

### Assertion Helpers

```python
def test_example(temp_config):
    lesson_id = make_lesson(temp_config, title="My Lesson")
    lesson = core.get_lesson(lesson_id, config=temp_config)

    assert_lesson_matches(lesson, {
        "title": "My Lesson",
        "confidence": "medium",  # default from make_lesson
    })
```

### Factory Helpers

```python
def test_with_defaults(temp_config):
    # Uses sensible defaults
    lesson_id = make_lesson(temp_config)

    # Override specific fields
    resource_id = make_resource(
        temp_config,
        title="Custom Title",
        versions=["v3"],
    )

    # Create approved rule
    rule_id = make_rule(temp_config, approved=True)
```

### Database Helpers

```python
def test_database_state(temp_config):
    make_lesson(temp_config)
    make_lesson(temp_config)

    assert count_rows(temp_config, "lessons") == 2

    ids = get_all_ids(temp_config, "lessons")
    assert len(ids) == 2
```

## Markers

Custom pytest markers are defined in `pyproject.toml`:

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Skip slow tests
pytest -m "not slow"

# Skip tests requiring real embeddings
pytest -m "not embeddings"
```

### Available Markers

| Marker | Description |
|--------|-------------|
| `@pytest.mark.unit` | Fast, isolated unit tests |
| `@pytest.mark.integration` | Tests using real database |
| `@pytest.mark.slow` | Tests that load ML models or call APIs |
| `@pytest.mark.embeddings` | Tests requiring real embedding models |

## Writing Tests

### Use Fast Fixtures When Possible

```python
# Slow - loads real embedding model
def test_something(temp_config):
    ...

# Fast - uses mock embeddings
def test_something(fast_config):
    ...
```

### Use Pre-populated Fixtures for Complex Tests

```python
def test_relationships(populated_db):
    config, entities = populated_db
    lesson_id = entities["lessons"]["jira_api"]

    # Test with pre-existing data and relationships
    related = core.get_related(lesson_id, config=config)
    ...
```

### Use Helpers to Reduce Boilerplate

```python
# Instead of this:
def test_verbose(temp_config):
    lesson_id = core.add_lesson(
        title="Test",
        content="Content",
        tags=["test"],
        confidence="medium",
        source="tested",
        config=temp_config,
    )

# Do this:
def test_concise(temp_config):
    lesson_id = make_lesson(temp_config)
```

## Migration Tests

Database migration tests are intentionally deferred until v1.0.0. The placeholder in `test_db.py` will fail once the version reaches 1.0.0 as a reminder to implement proper migration tests.

See the placeholder test for details on what migration tests should cover.
