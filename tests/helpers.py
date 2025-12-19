"""Test helper utilities.

This module provides helper functions for writing tests, including:
- Assertion helpers for validating entities
- Factory helpers for creating test data
- Database helpers for inspecting state
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ai_lessons.config import Config


# -----------------------------------------------------------------------------
# Assertion Helpers
# -----------------------------------------------------------------------------


def assert_lesson_matches(lesson: Any, expected: dict[str, Any]) -> None:
    """Assert that a lesson matches expected values.

    Args:
        lesson: Lesson object to check (from core.get_lesson)
        expected: Dict of field name -> expected value

    Raises:
        AssertionError: If any field doesn't match

    Example:
        lesson = core.get_lesson(lesson_id, config=config)
        assert_lesson_matches(lesson, {
            "title": "My Lesson",
            "confidence": "high",
        })
    """
    assert lesson is not None, "Lesson is None"

    for field, value in expected.items():
        actual = getattr(lesson, field, None)
        if isinstance(value, set):
            # For sets, compare as sets
            actual_set = set(actual) if actual else set()
            assert actual_set == value, f"Lesson.{field}: expected {value}, got {actual_set}"
        elif isinstance(value, list):
            # For lists, compare contents (order-independent for tags)
            if field == "tags":
                assert set(actual or []) == set(value), f"Lesson.{field}: expected {value}, got {actual}"
            else:
                assert actual == value, f"Lesson.{field}: expected {value}, got {actual}"
        else:
            assert actual == value, f"Lesson.{field}: expected {value}, got {actual}"


def assert_resource_matches(resource: Any, expected: dict[str, Any]) -> None:
    """Assert that a resource matches expected values.

    Args:
        resource: Resource object to check (from core.get_resource)
        expected: Dict of field name -> expected value

    Raises:
        AssertionError: If any field doesn't match
    """
    assert resource is not None, "Resource is None"

    for field, value in expected.items():
        actual = getattr(resource, field, None)
        if field in ("tags", "versions"):
            # Compare as sets for order-independence
            assert set(actual or []) == set(value), f"Resource.{field}: expected {value}, got {actual}"
        else:
            assert actual == value, f"Resource.{field}: expected {value}, got {actual}"


def assert_rule_matches(rule: Any, expected: dict[str, Any]) -> None:
    """Assert that a rule matches expected values.

    Args:
        rule: Rule object to check (from core.get_rule)
        expected: Dict of field name -> expected value

    Raises:
        AssertionError: If any field doesn't match
    """
    assert rule is not None, "Rule is None"

    for field, value in expected.items():
        actual = getattr(rule, field, None)
        if field in ("tags", "linked_lessons", "linked_resources"):
            # Compare as sets for order-independence
            assert set(actual or []) == set(value), f"Rule.{field}: expected {value}, got {actual}"
        else:
            assert actual == value, f"Rule.{field}: expected {value}, got {actual}"


def assert_search_result_valid(result: Any) -> None:
    """Assert that a search result has valid structure.

    Checks:
    - Has required fields (id, title, content, score, result_type)
    - Score is between 0 and 1
    - result_type is valid

    Args:
        result: Search result object

    Raises:
        AssertionError: If result is invalid
    """
    assert result is not None, "Result is None"
    assert hasattr(result, "id"), "Result missing 'id'"
    assert hasattr(result, "title"), "Result missing 'title'"
    assert hasattr(result, "content"), "Result missing 'content'"
    assert hasattr(result, "score"), "Result missing 'score'"
    assert hasattr(result, "result_type"), "Result missing 'result_type'"

    assert 0.0 <= result.score <= 1.0, f"Score {result.score} not in [0, 1]"
    assert result.result_type in (
        "lesson", "resource", "chunk", "rule"
    ), f"Invalid result_type: {result.result_type}"


# -----------------------------------------------------------------------------
# Factory Helpers
# -----------------------------------------------------------------------------


def make_lesson(
    config: "Config",
    title: str = "Test Lesson",
    content: str = "Test content.",
    tags: list[str] | None = None,
    confidence: str = "medium",
    source: str = "tested",
    **kwargs: Any,
) -> str:
    """Create a lesson with sensible defaults.

    Args:
        config: Test configuration
        title: Lesson title (default: "Test Lesson")
        content: Lesson content (default: "Test content.")
        tags: List of tags (default: ["test"])
        confidence: Confidence level (default: "medium")
        source: Source type (default: "tested")
        **kwargs: Additional arguments passed to add_lesson

    Returns:
        The lesson ID

    Example:
        lesson_id = make_lesson(config, title="My Lesson", tags=["python"])
    """
    from ai_lessons import core

    if tags is None:
        tags = ["test"]

    return core.add_lesson(
        title=title,
        content=content,
        tags=tags,
        confidence=confidence,
        source=source,
        config=config,
        **kwargs,
    )


def make_resource(
    config: "Config",
    type: str = "doc",
    title: str = "Test Resource",
    content: str = "Test resource content.",
    versions: list[str] | None = None,
    tags: list[str] | None = None,
    **kwargs: Any,
) -> str:
    """Create a resource with sensible defaults.

    Args:
        config: Test configuration
        type: Resource type (default: "doc")
        title: Resource title (default: "Test Resource")
        content: Resource content (default: "Test resource content.")
        versions: List of versions (default: ["unversioned"])
        tags: List of tags (default: ["test"])
        **kwargs: Additional arguments passed to add_resource

    Returns:
        The resource ID
    """
    from ai_lessons import core

    if tags is None:
        tags = ["test"]

    return core.add_resource(
        type=type,
        title=title,
        content=content,
        versions=versions,
        tags=tags,
        config=config,
        **kwargs,
    )


def make_rule(
    config: "Config",
    title: str = "Test Rule",
    content: str = "Test rule content.",
    rationale: str = "Test rationale for the rule.",
    tags: list[str] | None = None,
    suggested_by: str = "test-helper",
    approved: bool = False,
    **kwargs: Any,
) -> str:
    """Create a rule with sensible defaults.

    Args:
        config: Test configuration
        title: Rule title (default: "Test Rule")
        content: Rule content (default: "Test rule content.")
        rationale: Rule rationale (default: "Test rationale for the rule.")
        tags: List of tags (default: ["test"])
        suggested_by: Who suggested the rule (default: "test-helper")
        approved: Whether to approve the rule (default: False)
        **kwargs: Additional arguments passed to suggest_rule

    Returns:
        The rule ID
    """
    from ai_lessons import core

    if tags is None:
        tags = ["test"]

    rule_id = core.suggest_rule(
        title=title,
        content=content,
        rationale=rationale,
        tags=tags,
        suggested_by=suggested_by,
        config=config,
        **kwargs,
    )

    if approved:
        core.approve_rule(rule_id, approved_by="test-helper", config=config)

    return rule_id


# -----------------------------------------------------------------------------
# Database Helpers
# -----------------------------------------------------------------------------


def count_rows(config: "Config", table: str) -> int:
    """Count rows in a database table.

    Args:
        config: Test configuration
        table: Table name

    Returns:
        Number of rows in the table

    Example:
        assert count_rows(config, "lessons") == 5
    """
    from ai_lessons.db import get_db

    with get_db(config) as conn:
        cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
        return cursor.fetchone()[0]


def get_all_ids(config: "Config", table: str, id_column: str = "id") -> list[str]:
    """Get all IDs from a database table.

    Args:
        config: Test configuration
        table: Table name
        id_column: Name of the ID column (default: "id")

    Returns:
        List of all IDs in the table

    Example:
        lesson_ids = get_all_ids(config, "lessons")
    """
    from ai_lessons.db import get_db

    with get_db(config) as conn:
        cursor = conn.execute(f"SELECT {id_column} FROM {table}")  # noqa: S608
        return [row[0] for row in cursor.fetchall()]


def clear_table(config: "Config", table: str) -> int:
    """Delete all rows from a database table.

    Args:
        config: Test configuration
        table: Table name

    Returns:
        Number of rows deleted

    Warning:
        This permanently deletes data. Only use in tests.

    Example:
        clear_table(config, "lessons")
        assert count_rows(config, "lessons") == 0
    """
    from ai_lessons.db import get_db

    with get_db(config) as conn:
        cursor = conn.execute(f"DELETE FROM {table}")  # noqa: S608
        conn.commit()
        return cursor.rowcount


def table_exists(config: "Config", table: str) -> bool:
    """Check if a database table exists.

    Args:
        config: Test configuration
        table: Table name

    Returns:
        True if table exists, False otherwise
    """
    from ai_lessons.db import get_db

    with get_db(config) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        return cursor.fetchone() is not None


def get_table_columns(config: "Config", table: str) -> list[str]:
    """Get column names for a database table.

    Args:
        config: Test configuration
        table: Table name

    Returns:
        List of column names
    """
    from ai_lessons.db import get_db

    with get_db(config) as conn:
        cursor = conn.execute(f"PRAGMA table_info({table})")  # noqa: S608
        return [row[1] for row in cursor.fetchall()]
