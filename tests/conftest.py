"""Centralized pytest fixtures and configuration.

This module provides shared fixtures for all tests, including:
- Database configuration with isolated temp directories
- Mock embedder to avoid loading ML models (fast tests)
- Pre-populated database fixtures for integration tests
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from ai_lessons.config import Config, EmbeddingConfig, SearchConfig
from ai_lessons.db import init_db

if TYPE_CHECKING:
    from collections.abc import Generator


# -----------------------------------------------------------------------------
# Mock Embedder Fixtures
# -----------------------------------------------------------------------------


class MockEmbedder:
    """Mock embedder that returns deterministic vectors without loading models.

    This dramatically speeds up tests by avoiding SentenceTransformers model loading.
    Vectors are deterministic based on input text hash for reproducibility.
    Implements the EmbeddingBackend interface (embed, embed_batch, dimensions).
    """

    def __init__(self, dimensions: int = 384) -> None:
        self._dimensions = dimensions
        self._call_count = 0

    @property
    def dimensions(self) -> int:
        """Return the embedding dimensions."""
        return self._dimensions

    def embed(self, text: str) -> list[float]:
        """Generate a deterministic mock embedding based on text hash."""
        self._call_count += 1
        # Use hash to get deterministic but varied vectors
        h = hash(text) & 0xFFFFFFFF
        # Generate vector with some variation based on hash
        return [
            ((h >> (i % 32)) & 1) * 0.1 + (i / self._dimensions) * 0.01
            for i in range(self._dimensions)
        ]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts."""
        return [self.embed(t) for t in texts]

    @property
    def call_count(self) -> int:
        """Number of times embed was called."""
        return self._call_count


@pytest.fixture
def mock_embedder() -> MockEmbedder:
    """Create a mock embedder instance.

    Use this when you need direct access to the mock embedder object
    (e.g., to check call counts or customize behavior).
    """
    return MockEmbedder()


@pytest.fixture
def patched_embedder() -> Generator[MockEmbedder, None, None]:
    """Patch the global embedder with a mock.

    This fixture patches the embedder at the module level so all code
    using get_embedder() will receive the mock instead of loading real models.
    """
    mock = MockEmbedder()

    with patch("ai_lessons.embeddings.get_embedder", return_value=mock), \
         patch("ai_lessons.embeddings._embedder", mock):
        yield mock


# -----------------------------------------------------------------------------
# Database Configuration Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files.

    The directory is automatically cleaned up after the test.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_config(temp_dir: Path) -> Generator[Config, None, None]:
    """Create a temporary configuration for testing.

    This is the standard fixture for tests that need database access.
    Uses real embedding models - consider using fast_config for speed.
    """
    config = Config(
        db_path=temp_dir / "test.db",
        embedding=EmbeddingConfig(
            backend="sentence-transformers",
            model="all-MiniLM-L6-v2",
        ),
        search=SearchConfig(),
    )
    init_db(config)
    yield config


@pytest.fixture
def fast_config(temp_dir: Path, patched_embedder: MockEmbedder) -> Generator[Config, None, None]:
    """Create a fast test configuration with mocked embeddings.

    Use this fixture for tests that don't specifically need real embeddings.
    Tests run significantly faster because no ML models are loaded.
    """
    config = Config(
        db_path=temp_dir / "test.db",
        embedding=EmbeddingConfig(
            backend="sentence-transformers",
            model="all-MiniLM-L6-v2",
            dimensions=384,
        ),
        search=SearchConfig(),
    )
    init_db(config)
    yield config


# -----------------------------------------------------------------------------
# Pre-populated Database Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sample_lessons(temp_config: Config) -> dict[str, str]:
    """Create sample lessons and return their IDs.

    Returns a dict mapping descriptive names to lesson IDs.
    """
    from ai_lessons import core

    lessons = {
        "python_debugging": core.add_lesson(
            title="Python Debugging Tips",
            content="Use pdb.set_trace() or breakpoint() for interactive debugging.",
            tags=["python", "debugging"],
            confidence="high",
            source="tested",
            config=temp_config,
        ),
        "jira_api": core.add_lesson(
            title="Jira API Gotchas",
            content="Always GET before PUT - PUT replaces the entire resource.",
            tags=["jira", "api", "gotcha"],
            confidence="high",
            source="tested",
            config=temp_config,
        ),
        "git_workflow": core.add_lesson(
            title="Git Rebase Best Practices",
            content="Never rebase shared branches. Use merge for public history.",
            tags=["git", "workflow"],
            confidence="medium",
            source="inferred",
            config=temp_config,
        ),
    }
    return lessons


@pytest.fixture
def sample_resources(temp_config: Config) -> dict[str, str]:
    """Create sample resources and return their IDs.

    Returns a dict mapping descriptive names to resource IDs.
    """
    from ai_lessons import core

    resources = {
        "api_docs": core.add_resource(
            type="doc",
            title="API Documentation",
            content="""# API Reference

## Authentication

All requests require an API key in the Authorization header.

## Endpoints

### GET /users

Returns a list of users.

### POST /users

Creates a new user.
""",
            versions=["v3"],
            tags=["api", "reference"],
            config=temp_config,
        ),
        "workflow_guide": core.add_resource(
            type="doc",
            title="Workflow Guide",
            content="""# Workflow Guide

## Getting Started

Follow these steps to set up your workflow.

## Best Practices

Always review before merging.
""",
            versions=["v2", "v3"],
            tags=["guide", "workflow"],
            config=temp_config,
        ),
    }
    return resources


@pytest.fixture
def sample_rules(temp_config: Config, sample_lessons: dict[str, str]) -> dict[str, str]:
    """Create sample rules and return their IDs.

    Returns a dict mapping descriptive names to rule IDs.
    Some rules are linked to sample_lessons.
    """
    from ai_lessons import core

    rules = {
        "get_before_put": core.suggest_rule(
            title="GET Before PUT",
            content="Always fetch current state before updating.",
            rationale="PUT operations replace the entire resource. GET ensures you have the latest state.",
            tags=["api", "best-practice"],
            suggested_by="test-fixture",
            linked_lessons=[sample_lessons["jira_api"]],
            config=temp_config,
        ),
        "no_rebase_shared": core.suggest_rule(
            title="No Rebase on Shared Branches",
            content="Never rebase branches that others are working on.",
            rationale="Rebasing rewrites history, causing conflicts for collaborators.",
            tags=["git", "workflow"],
            suggested_by="test-fixture",
            config=temp_config,
        ),
    }

    # Approve the first rule
    core.approve_rule(rules["get_before_put"], approved_by="test-admin", config=temp_config)

    return rules


@pytest.fixture
def populated_db(
    temp_config: Config,
    sample_lessons: dict[str, str],
    sample_resources: dict[str, str],
    sample_rules: dict[str, str],
) -> tuple[Config, dict[str, dict[str, str]]]:
    """Create a fully populated test database.

    Returns a tuple of (config, entities) where entities is a dict with:
    - lessons: dict of lesson name -> ID
    - resources: dict of resource name -> ID
    - rules: dict of rule name -> ID
    """
    from ai_lessons import core

    # Create some relationships
    core.link_lessons(
        sample_lessons["python_debugging"],
        sample_lessons["jira_api"],
        "related_to",
        config=temp_config,
    )

    core.link_lesson_to_resource(
        sample_lessons["jira_api"],
        sample_resources["api_docs"],
        config=temp_config,
    )

    entities = {
        "lessons": sample_lessons,
        "resources": sample_resources,
        "rules": sample_rules,
    }

    return temp_config, entities


# -----------------------------------------------------------------------------
# Fast Pre-populated Fixtures (with mocked embeddings)
# -----------------------------------------------------------------------------


@pytest.fixture
def fast_sample_lessons(fast_config: Config) -> dict[str, str]:
    """Create sample lessons with mocked embeddings (fast)."""
    from ai_lessons import core

    return {
        "python_debugging": core.add_lesson(
            title="Python Debugging Tips",
            content="Use pdb for debugging.",
            tags=["python"],
            config=fast_config,
        ),
        "jira_api": core.add_lesson(
            title="Jira API Gotchas",
            content="GET before PUT.",
            tags=["jira", "api"],
            config=fast_config,
        ),
    }


@pytest.fixture
def fast_populated_db(
    fast_config: Config,
    fast_sample_lessons: dict[str, str],
) -> tuple[Config, dict[str, str]]:
    """Create a populated test database with mocked embeddings (fast)."""
    return fast_config, fast_sample_lessons
