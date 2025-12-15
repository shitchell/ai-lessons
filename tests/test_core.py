"""Tests for ai-lessons core functionality."""

import tempfile
from pathlib import Path

import pytest

from ai_lessons.config import Config, EmbeddingConfig, SearchConfig
from ai_lessons.db import init_db
from ai_lessons import core


@pytest.fixture
def temp_config():
    """Create a temporary configuration for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        config = Config(
            db_path=db_path,
            embedding=EmbeddingConfig(
                backend="sentence-transformers",
                model="all-MiniLM-L6-v2",
            ),
            search=SearchConfig(),
        )
        init_db(config)
        yield config


class TestCRUD:
    """Test CRUD operations."""

    def test_add_lesson(self, temp_config):
        """Test adding a lesson."""
        lesson_id = core.add_lesson(
            title="Test Lesson",
            content="This is a test lesson content.",
            tags=["test", "example"],
            confidence="medium",
            source="tested",
            config=temp_config,
        )

        assert lesson_id is not None
        assert len(lesson_id) > 0

    def test_get_lesson(self, temp_config):
        """Test getting a lesson by ID."""
        lesson_id = core.add_lesson(
            title="Get Test",
            content="Content for get test.",
            tags=["get", "test"],
            confidence="high",
            config=temp_config,
        )

        lesson = core.get_lesson(lesson_id, config=temp_config)

        assert lesson is not None
        assert lesson.id == lesson_id
        assert lesson.title == "Get Test"
        assert lesson.content == "Content for get test."
        assert "get" in lesson.tags
        assert "test" in lesson.tags
        assert lesson.confidence == "high"

    def test_get_nonexistent_lesson(self, temp_config):
        """Test getting a lesson that doesn't exist."""
        lesson = core.get_lesson("nonexistent-id", config=temp_config)
        assert lesson is None

    def test_update_lesson(self, temp_config):
        """Test updating a lesson."""
        lesson_id = core.add_lesson(
            title="Original Title",
            content="Original content.",
            tags=["original"],
            config=temp_config,
        )

        success = core.update_lesson(
            lesson_id=lesson_id,
            title="Updated Title",
            tags=["updated"],
            config=temp_config,
        )

        assert success is True

        lesson = core.get_lesson(lesson_id, config=temp_config)
        assert lesson.title == "Updated Title"
        assert "updated" in lesson.tags
        assert "original" not in lesson.tags

    def test_delete_lesson(self, temp_config):
        """Test deleting a lesson."""
        lesson_id = core.add_lesson(
            title="To Delete",
            content="This will be deleted.",
            config=temp_config,
        )

        success = core.delete_lesson(lesson_id, config=temp_config)
        assert success is True

        lesson = core.get_lesson(lesson_id, config=temp_config)
        assert lesson is None


class TestSearch:
    """Test search functionality."""

    def test_recall_finds_lesson(self, temp_config):
        """Test that recall can find a lesson."""
        core.add_lesson(
            title="Jira workflow updates delete missing statuses",
            content="When calling PUT to update workflows, any missing statuses are deleted.",
            tags=["jira", "api", "gotcha"],
            confidence="high",
            source="tested",
            config=temp_config,
        )

        results = core.recall(
            query="jira workflow update",
            config=temp_config,
        )

        assert len(results) > 0
        assert "jira" in results[0].title.lower() or "workflow" in results[0].title.lower()

    def test_recall_with_tag_filter(self, temp_config):
        """Test recall with tag filtering."""
        core.add_lesson(
            title="Python debugging tip",
            content="Use pdb.set_trace() for debugging.",
            tags=["python", "debugging"],
            config=temp_config,
        )

        core.add_lesson(
            title="JavaScript debugging tip",
            content="Use console.log() for debugging.",
            tags=["javascript", "debugging"],
            config=temp_config,
        )

        results = core.recall(
            query="debugging",
            tags=["python"],
            config=temp_config,
        )

        assert len(results) > 0
        assert "python" in results[0].tags


class TestGraph:
    """Test graph operations."""

    def test_link_lessons(self, temp_config):
        """Test linking two lessons."""
        id1 = core.add_lesson(
            title="Lesson 1",
            content="First lesson.",
            config=temp_config,
        )

        id2 = core.add_lesson(
            title="Lesson 2",
            content="Second lesson.",
            config=temp_config,
        )

        success = core.link_lessons(id1, id2, "related_to", config=temp_config)
        assert success is True

    def test_get_related(self, temp_config):
        """Test getting related lessons."""
        id1 = core.add_lesson(
            title="Parent Lesson",
            content="This is the parent.",
            config=temp_config,
        )

        id2 = core.add_lesson(
            title="Child Lesson",
            content="This is the child.",
            config=temp_config,
        )

        core.link_lessons(id1, id2, "related_to", config=temp_config)

        related = core.get_related(id1, config=temp_config)

        assert len(related) == 1
        assert related[0].id == id2


class TestReferenceTables:
    """Test reference table operations."""

    def test_list_sources(self, temp_config):
        """Test listing source types."""
        sources = core.list_sources(config=temp_config)

        assert len(sources) == 5
        source_names = [s.name for s in sources]
        assert "tested" in source_names
        assert "inferred" in source_names

    def test_list_confidence_levels(self, temp_config):
        """Test listing confidence levels."""
        levels = core.list_confidence_levels(config=temp_config)

        assert len(levels) == 5
        assert levels[0].name == "very-low"
        assert levels[4].name == "very-high"

    def test_list_tags(self, temp_config):
        """Test listing tags."""
        core.add_lesson(
            title="Tagged Lesson",
            content="Has tags.",
            tags=["alpha", "beta"],
            config=temp_config,
        )

        tags = core.list_tags(with_counts=True, config=temp_config)

        assert len(tags) == 2
        tag_names = [t.name for t in tags]
        assert "alpha" in tag_names
        assert "beta" in tag_names
