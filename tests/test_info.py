"""Tests for info CLI commands and related core functions."""

import json

import pytest
from click.testing import CliRunner

from ai_lessons import core
from ai_lessons.cli import main


# Use fast_config from conftest.py for speed


class TestListTagsDetailed:
    """Test list_tags_detailed core function."""

    def test_empty_database(self, fast_config):
        """No tags in empty database."""
        tags = core.list_tags_detailed(config=fast_config)
        assert tags == []

    def test_lesson_tags(self, fast_sample_lessons, fast_config):
        """Tags from lessons are listed with counts."""
        tags = core.list_tags_detailed(config=fast_config)

        # Sample lessons have tags: python, jira, api
        tag_names = [t.name for t in tags]
        assert "python" in tag_names
        assert "jira" in tag_names
        assert "api" in tag_names

        # Check counts
        python_tag = next(t for t in tags if t.name == "python")
        assert python_tag.lesson_count >= 1
        assert python_tag.resource_count == 0
        assert python_tag.rule_count == 0

    def test_filter_by_pattern(self, fast_sample_lessons, fast_config):
        """Filter tags by pattern substring."""
        tags = core.list_tags_detailed(pattern="py", config=fast_config)
        assert len(tags) >= 1
        assert all("py" in t.name.lower() for t in tags)

    def test_filter_by_entity_type(self, fast_config):
        """Filter tags by entity type."""
        # Add a lesson with a unique tag
        core.add_lesson(
            title="Test",
            content="Content",
            tags=["lesson-only-tag"],
            config=fast_config,
        )

        # Filter to lesson tags only
        tags = core.list_tags_detailed(entity_type="lesson", config=fast_config)
        tag_names = [t.name for t in tags]
        assert "lesson-only-tag" in tag_names


class TestListTagAliases:
    """Test list_tag_aliases core function."""

    def test_empty_database(self, fast_config):
        """No aliases in empty database."""
        aliases = core.list_tag_aliases(config=fast_config)
        assert aliases == []


class TestListRelations:
    """Test list_relations core function."""

    def test_empty_database(self, fast_config):
        """No relations in empty database."""
        relations = core.list_relations(config=fast_config)
        assert relations == []

    def test_with_edges(self, fast_config):
        """Relations are counted from edges."""
        # Create lessons and link them
        id1 = core.add_lesson(title="L1", content="C1", config=fast_config)
        id2 = core.add_lesson(title="L2", content="C2", config=fast_config)
        core.link_lessons(id1, id2, "related_to", config=fast_config)

        relations = core.list_relations(config=fast_config)
        assert len(relations) >= 1

        relation_names = [r.name for r in relations]
        assert "related_to" in relation_names

        related_to = next(r for r in relations if r.name == "related_to")
        assert related_to.count >= 1


class TestListSourcesWithCounts:
    """Test list_sources with_counts parameter."""

    def test_without_counts(self, fast_config):
        """Sources listed without counts by default."""
        sources = core.list_sources(config=fast_config)
        assert len(sources) > 0  # Schema seeds some sources
        # Without counts, count should be 0
        assert all(s.count == 0 for s in sources)

    def test_with_counts(self, fast_config):
        """Sources listed with counts when requested."""
        # Add a lesson with a specific source
        core.add_lesson(
            title="Test",
            content="Content",
            source="tested",
            config=fast_config,
        )

        sources = core.list_sources(with_counts=True, config=fast_config)
        tested_source = next((s for s in sources if s.name == "tested"), None)
        assert tested_source is not None
        assert tested_source.count >= 1


class TestListConfidenceLevelsWithCounts:
    """Test list_confidence_levels with_counts parameter."""

    def test_without_counts(self, fast_config):
        """Confidence levels listed without counts by default."""
        levels = core.list_confidence_levels(config=fast_config)
        assert len(levels) > 0  # Schema seeds confidence levels
        assert all(l.count == 0 for l in levels)

    def test_with_counts(self, fast_config):
        """Confidence levels listed with counts when requested."""
        # Add a lesson with a specific confidence
        core.add_lesson(
            title="Test",
            content="Content",
            confidence="high",
            config=fast_config,
        )

        levels = core.list_confidence_levels(with_counts=True, config=fast_config)
        high_level = next((l for l in levels if l.name == "high"), None)
        assert high_level is not None
        assert high_level.count >= 1


class TestGetDatabaseStats:
    """Test get_database_stats core function."""

    def test_empty_database(self, fast_config):
        """Stats for empty database."""
        stats = core.get_database_stats(config=fast_config)

        assert "lessons" in stats
        assert "resources" in stats
        assert "rules" in stats
        assert "edges" in stats
        assert "tags" in stats

        assert stats["lessons"]["count"] == 0
        assert stats["resources"]["count"] == 0
        assert stats["rules"]["count"] == 0

    def test_populated_database(self, fast_sample_lessons, fast_config):
        """Stats reflect database contents."""
        stats = core.get_database_stats(config=fast_config)

        assert stats["lessons"]["count"] >= 2  # from fast_sample_lessons
        assert stats["tags"]["count"] >= 1


class TestInfoTagsCLI:
    """Test info tags CLI command."""

    def test_tags_empty(self, fast_config, monkeypatch):
        """Tags command with empty database."""
        monkeypatch.setattr("ai_lessons.core.get_config", lambda: fast_config)

        runner = CliRunner()
        result = runner.invoke(main, ["info", "tags"])

        assert result.exit_code == 0
        assert "No tags found" in result.output

    def test_tags_with_data(self, fast_sample_lessons, fast_config, monkeypatch):
        """Tags command lists tags."""
        monkeypatch.setattr("ai_lessons.core.get_config", lambda: fast_config)

        runner = CliRunner()
        result = runner.invoke(main, ["info", "tags"])

        assert result.exit_code == 0
        assert "Active tags:" in result.output
        assert "python" in result.output

    def test_tags_with_counts(self, fast_sample_lessons, fast_config, monkeypatch):
        """Tags command with --counts flag."""
        monkeypatch.setattr("ai_lessons.core.get_config", lambda: fast_config)

        runner = CliRunner()
        result = runner.invoke(main, ["info", "tags", "--counts"])

        assert result.exit_code == 0
        assert "lesson" in result.output  # Should show count like "1 lesson"

    def test_tags_json_output(self, fast_sample_lessons, fast_config, monkeypatch):
        """Tags command with --json flag."""
        monkeypatch.setattr("ai_lessons.core.get_config", lambda: fast_config)

        runner = CliRunner()
        result = runner.invoke(main, ["info", "tags", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "tags" in data
        assert "aliases" in data


class TestInfoConfidenceCLI:
    """Test info confidence CLI command."""

    def test_confidence_levels(self, fast_config, monkeypatch):
        """Confidence command lists levels."""
        monkeypatch.setattr("ai_lessons.core.get_config", lambda: fast_config)

        runner = CliRunner()
        result = runner.invoke(main, ["info", "confidence"])

        assert result.exit_code == 0
        assert "Confidence levels:" in result.output
        assert "high" in result.output or "medium" in result.output

    def test_confidence_json(self, fast_config, monkeypatch):
        """Confidence command with --json flag."""
        monkeypatch.setattr("ai_lessons.core.get_config", lambda: fast_config)

        runner = CliRunner()
        result = runner.invoke(main, ["info", "confidence", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "confidence_levels" in data


class TestInfoLessonSourcesCLI:
    """Test info lesson-sources CLI command."""

    def test_lesson_sources(self, fast_config, monkeypatch):
        """Lesson-sources command lists sources."""
        monkeypatch.setattr("ai_lessons.core.get_config", lambda: fast_config)

        runner = CliRunner()
        result = runner.invoke(main, ["info", "lesson-sources"])

        assert result.exit_code == 0
        assert "Source types:" in result.output

    def test_lesson_sources_json(self, fast_config, monkeypatch):
        """Lesson-sources command with --json flag."""
        monkeypatch.setattr("ai_lessons.core.get_config", lambda: fast_config)

        runner = CliRunner()
        result = runner.invoke(main, ["info", "lesson-sources", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "source_types" in data


class TestInfoRelationsCLI:
    """Test info relations CLI command."""

    def test_relations_empty(self, fast_config, monkeypatch):
        """Relations command with no edges."""
        monkeypatch.setattr("ai_lessons.core.get_config", lambda: fast_config)

        runner = CliRunner()
        result = runner.invoke(main, ["info", "relations"])

        assert result.exit_code == 0
        assert "No edge relations found" in result.output

    def test_relations_json(self, fast_config, monkeypatch):
        """Relations command with --json flag."""
        monkeypatch.setattr("ai_lessons.core.get_config", lambda: fast_config)

        runner = CliRunner()
        result = runner.invoke(main, ["info", "relations", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "relations" in data


class TestInfoStatsCLI:
    """Test info stats CLI command."""

    def test_stats(self, fast_config, monkeypatch):
        """Stats command shows statistics."""
        monkeypatch.setattr("ai_lessons.core.get_config", lambda: fast_config)

        runner = CliRunner()
        result = runner.invoke(main, ["info", "stats"])

        assert result.exit_code == 0
        assert "Lessons:" in result.output
        assert "Resources:" in result.output
        assert "Rules:" in result.output

    def test_stats_json(self, fast_config, monkeypatch):
        """Stats command with --json flag."""
        monkeypatch.setattr("ai_lessons.core.get_config", lambda: fast_config)

        runner = CliRunner()
        result = runner.invoke(main, ["info", "stats", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "lessons" in data
        assert "resources" in data


class TestTagInfo:
    """Test TagInfo dataclass."""

    def test_total_count(self):
        """Total count property sums all entity counts."""
        tag = core.TagInfo(
            name="test",
            lesson_count=5,
            resource_count=3,
            rule_count=2,
        )
        assert tag.total_count == 10

    def test_total_count_zeros(self):
        """Total count handles zero values."""
        tag = core.TagInfo(name="empty")
        assert tag.total_count == 0
