"""Tests for search scoring functions and constants."""

from __future__ import annotations

import pytest

from ai_lessons import core
from ai_lessons.search import (
    # Constants
    KEYWORD_TITLE_WEIGHT,
    KEYWORD_CONTENT_WEIGHT,
    KEYWORD_TAG_WEIGHT,
    SIGMOID_STEEPNESS,
    SIGMOID_CENTER,
    HYBRID_SEMANTIC_WEIGHT,
    HYBRID_KEYWORD_WEIGHT,
    LINK_BOOST_FACTOR,
    MIN_LINKED_SCORE,
    MATCH_BONUS,
    CHUNK_SPECIFICITY_MULT,
    RULE_DEFAULT_SCORE,
    # Functions
    _normalize_text,
    _keyword_score,
    _distance_to_score,
    _compute_resource_score,
    compute_version_score,
    # Result types
    LessonResult,
    ResourceResult,
    ChunkResult,
    RuleResult,
)


class TestScoringConstants:
    """Test that scoring constants have reasonable values."""

    def test_keyword_weights_positive(self):
        """Keyword weights should be positive."""
        assert KEYWORD_TITLE_WEIGHT > 0
        assert KEYWORD_CONTENT_WEIGHT > 0
        assert KEYWORD_TAG_WEIGHT > 0

    def test_title_weighted_higher_than_content(self):
        """Title matches should be weighted higher than content."""
        assert KEYWORD_TITLE_WEIGHT > KEYWORD_CONTENT_WEIGHT

    def test_tag_weighted_higher_than_content(self):
        """Tag matches should be weighted higher than content."""
        assert KEYWORD_TAG_WEIGHT > KEYWORD_CONTENT_WEIGHT

    def test_sigmoid_params_reasonable(self):
        """Sigmoid parameters should produce sensible curves."""
        assert SIGMOID_STEEPNESS > 0
        assert 0 < SIGMOID_CENTER < 2  # Cosine distance is 0-2

    def test_hybrid_weights_sum_to_one(self):
        """Hybrid weights should sum to approximately 1."""
        assert abs(HYBRID_SEMANTIC_WEIGHT + HYBRID_KEYWORD_WEIGHT - 1.0) < 0.01

    def test_link_boost_bounded(self):
        """Link boost factor should be bounded reasonably."""
        assert 0 < LINK_BOOST_FACTOR < 1

    def test_min_linked_score_reasonable(self):
        """Min linked score threshold should be reasonable."""
        assert 0 < MIN_LINKED_SCORE < 1

    def test_match_bonus_small(self):
        """Match bonus should be a small increment."""
        assert 0 < MATCH_BONUS < 0.5

    def test_chunk_specificity_mult_above_one(self):
        """Chunk specificity multiplier should boost (>1)."""
        assert CHUNK_SPECIFICITY_MULT > 1.0
        assert CHUNK_SPECIFICITY_MULT < 1.2  # But not too much

    def test_rule_default_score_reasonable(self):
        """Rule default score should be middle-ish."""
        assert 0.3 < RULE_DEFAULT_SCORE < 0.7


class TestNormalizeText:
    """Test text normalization for keyword matching."""

    def test_lowercase(self):
        """Should lowercase text."""
        assert _normalize_text("Hello World") == "hello world"

    def test_collapse_whitespace(self):
        """Should collapse multiple whitespace to single space."""
        assert _normalize_text("hello   world") == "hello world"
        assert _normalize_text("hello\t\nworld") == "hello world"

    def test_strip_leading_trailing(self):
        """Should strip leading/trailing whitespace."""
        assert _normalize_text("  hello  ") == "hello"

    def test_empty_string(self):
        """Should handle empty string."""
        assert _normalize_text("") == ""


class TestKeywordScore:
    """Test basic keyword scoring."""

    def test_empty_query_returns_zero(self):
        """Empty query should return 0 score."""
        assert _keyword_score("", "title", "content") == 0.0

    def test_title_match_scores_higher(self):
        """Title matches should score higher than content-only matches."""
        title_match = _keyword_score("hello", "hello world", "goodbye")
        content_match = _keyword_score("hello", "goodbye", "hello world")
        assert title_match > content_match

    def test_both_match_highest(self):
        """Matching both title and content should score highest."""
        both = _keyword_score("hello", "hello title", "hello content")
        title_only = _keyword_score("hello", "hello title", "goodbye")
        content_only = _keyword_score("hello", "goodbye", "hello content")
        assert both > title_only
        assert both > content_only

    def test_no_match_returns_zero(self):
        """No matches should return 0."""
        assert _keyword_score("hello", "goodbye", "world") == 0.0

    def test_case_insensitive(self):
        """Should match case-insensitively."""
        assert _keyword_score("Hello", "HELLO", "hello") > 0

    def test_multiple_terms_averaged(self):
        """Score should be averaged across query terms."""
        # Single term match
        single = _keyword_score("hello", "hello world", "content")
        # Two terms, one matches
        double = _keyword_score("hello goodbye", "hello world", "content")
        # Two terms, both match
        double_both = _keyword_score("hello world", "hello world", "content")
        assert double < single  # One of two matches
        assert double_both > double  # Both match


class TestDistanceToScore:
    """Test sigmoid distance-to-score conversion."""

    def test_zero_distance_high_score(self):
        """Distance 0 should give high score (near 1)."""
        score = _distance_to_score(0.0)
        assert score > 0.9

    def test_center_distance_half_score(self):
        """Distance at center should give ~0.5 score."""
        score = _distance_to_score(SIGMOID_CENTER)
        assert 0.45 < score < 0.55

    def test_high_distance_low_score(self):
        """High distance should give low score."""
        score = _distance_to_score(2.0)
        assert score < 0.1

    def test_monotonically_decreasing(self):
        """Score should decrease as distance increases."""
        scores = [_distance_to_score(d) for d in [0.0, 0.5, 1.0, 1.5, 2.0]]
        for i in range(len(scores) - 1):
            assert scores[i] > scores[i + 1]

    def test_bounded_zero_one(self):
        """Score should always be between 0 and 1."""
        for d in [0.0, 0.5, 1.0, 1.5, 2.0, 10.0]:
            score = _distance_to_score(d)
            assert 0 <= score <= 1

    def test_custom_parameters(self):
        """Should accept custom steepness and center."""
        # Steeper curve
        steep = _distance_to_score(1.0, steepness=12.0, center=1.0)
        normal = _distance_to_score(1.0, steepness=6.0, center=1.0)
        # Both at center should be ~0.5
        assert abs(steep - 0.5) < 0.01
        assert abs(normal - 0.5) < 0.01


class TestKeywordScoreWithTags:
    """Test keyword scoring that includes tags."""

    def test_tag_match_scores(self):
        """Tag matches should contribute to score."""
        with_tag = _keyword_score("python", "title", "content", ["python"])
        without_tag = _keyword_score("python", "title", "content", [])
        assert with_tag > without_tag

    def test_tag_weight_higher_than_content(self):
        """Tag matches should be weighted higher than content matches."""
        tag_match = _keyword_score("python", "title", "other", ["python"])
        content_match = _keyword_score("python", "title", "python code", [])
        assert tag_match > content_match

    def test_multiple_tags(self):
        """Multiple matching tags should increase score."""
        one_tag = _keyword_score("python api", "title", "content", ["python"])
        two_tags = _keyword_score("python api", "title", "content", ["python", "api"])
        assert two_tags > one_tag

    def test_tag_case_insensitive(self):
        """Tag matching should be case-insensitive."""
        upper = _keyword_score("Python", "title", "content", ["python"])
        lower = _keyword_score("python", "title", "content", ["PYTHON"])
        assert upper > 0
        assert lower > 0

    def test_empty_query_returns_zero(self):
        """Empty query should return 0."""
        assert _keyword_score("", "title", "content", ["tag"]) == 0.0


class TestComputeResourceScore:
    """Test combined resource scoring."""

    def test_low_distance_high_score(self):
        """Low distance should give high score."""
        score = _compute_resource_score(
            distance=0.5,
            title="Test",
            content="Content",
            tags=["test"],
            query="test",
        )
        assert score > 0.7

    def test_version_score_multiplier(self):
        """Version score should multiply final score."""
        full = _compute_resource_score(
            distance=0.5, title="Test", content="Content",
            tags=[], query="test", version_score=1.0,
        )
        half = _compute_resource_score(
            distance=0.5, title="Test", content="Content",
            tags=[], query="test", version_score=0.5,
        )
        assert abs(half - full * 0.5) < 0.1  # Approximately half

    def test_chunk_boost_increases_score(self):
        """Chunk boost should increase score slightly."""
        # Use higher distance to avoid hitting the 1.0 cap
        without_boost = _compute_resource_score(
            distance=1.2, title="Generic", content="Other",
            tags=[], query="different", chunk_boost=False,
        )
        with_boost = _compute_resource_score(
            distance=1.2, title="Generic", content="Other",
            tags=[], query="different", chunk_boost=True,
        )
        assert with_boost > without_boost
        # The boost should be small (CHUNK_SPECIFICITY_MULT is ~1.03)
        assert with_boost < without_boost * 1.1

    def test_score_bounded_at_one(self):
        """Score should never exceed 1.0."""
        score = _compute_resource_score(
            distance=0.0,  # Best distance
            title="test test test",  # Max title match
            content="test",
            tags=["test"],  # Tag match too
            query="test",
            version_score=1.0,
            chunk_boost=True,
        )
        assert score <= 1.0


class TestVersionScoring:
    """Test version match scoring."""

    def test_exact_match_highest(self):
        """Exact version match should score 1.0."""
        score = compute_version_score({"v2", "v3"}, {"v2", "v3"})
        assert score == 1.0

    def test_superset_slightly_lower(self):
        """Resource with more versions should score 0.95."""
        score = compute_version_score({"v1", "v2", "v3"}, {"v2", "v3"})
        assert score == 0.95

    def test_subset_lower(self):
        """Resource with fewer versions should score 0.85."""
        score = compute_version_score({"v3"}, {"v2", "v3"})
        assert score == 0.85

    def test_partial_overlap_lower_still(self):
        """Partial overlap should score 0.75."""
        score = compute_version_score({"v2", "v4"}, {"v2", "v3"})
        assert score == 0.75

    def test_unversioned_scores(self):
        """Unversioned resource should score 0.70."""
        score = compute_version_score({"unversioned"}, {"v2", "v3"})
        assert score == 0.70

    def test_disjoint_excluded(self):
        """No overlap should return 0 (excluded)."""
        score = compute_version_score({"v1"}, {"v2", "v3"})
        assert score == 0.0

    def test_no_query_versions_matches_all(self):
        """Empty query versions should match everything."""
        score = compute_version_score({"v2", "v3"}, set())
        assert score == 1.0


class TestResultDataclasses:
    """Test search result dataclasses."""

    def test_lesson_result_type(self):
        """LessonResult should have result_type='lesson'."""
        result = LessonResult(
            id="1", title="Test", content="Content", score=0.5, result_type="",
        )
        assert result.result_type == "lesson"

    def test_resource_result_type(self):
        """ResourceResult should have result_type='resource'."""
        result = ResourceResult(
            id="1", title="Test", content="Content", score=0.5, result_type="",
        )
        assert result.result_type == "resource"

    def test_chunk_result_type(self):
        """ChunkResult should have result_type='chunk'."""
        result = ChunkResult(
            id="1", title="Test", content="Content", score=0.5, result_type="",
        )
        assert result.result_type == "chunk"

    def test_rule_result_type(self):
        """RuleResult should have result_type='rule'."""
        result = RuleResult(
            id="1", title="Test", content="Content", score=0.5, result_type="",
        )
        assert result.result_type == "rule"

    def test_lesson_result_fields(self):
        """LessonResult should have all expected fields."""
        result = LessonResult(
            id="1", title="Test", content="Content", score=0.5, result_type="",
            confidence="high", source="tested", contexts=["ctx"], anti_contexts=["anti"],
        )
        assert result.confidence == "high"
        assert result.source == "tested"
        assert result.contexts == ["ctx"]
        assert result.anti_contexts == ["anti"]

    def test_chunk_result_fields(self):
        """ChunkResult should have chunk-specific fields."""
        result = ChunkResult(
            id="1", title="Test", content="Content", score=0.5, result_type="",
            chunk_index=3, breadcrumb="Parent > Child", resource_id="res1",
            resource_title="Resource", versions=["v3"], sections=["Sec1"],
        )
        assert result.chunk_index == 3
        assert result.breadcrumb == "Parent > Child"
        assert result.resource_id == "res1"
        assert result.sections == ["Sec1"]


class TestGroupedResourceResult:
    """Test GroupedResourceResult dataclass."""

    def test_grouped_result_creation(self):
        """GroupedResourceResult should be creatable with expected fields."""
        from ai_lessons.search import GroupedResourceResult

        chunk1 = ChunkResult(
            id="res1.0", title="Chunk 0", content="Content 0", score=0.9, result_type="",
            chunk_index=0, resource_id="res1",
        )
        chunk2 = ChunkResult(
            id="res1.1", title="Chunk 1", content="Content 1", score=0.7, result_type="",
            chunk_index=1, resource_id="res1",
        )

        result = GroupedResourceResult(
            resource_id="res1",
            resource_title="Test Resource",
            resource_type="doc",
            versions=["v3"],
            tags=["api", "jira"],
            path="/path/to/doc.md",
            best_score=0.9,
            chunks=[chunk1, chunk2],
        )

        assert result.resource_id == "res1"
        assert result.resource_title == "Test Resource"
        assert result.resource_type == "doc"
        assert result.best_score == 0.9
        assert result.chunk_count == 2
        assert len(result.chunks) == 2

    def test_chunk_count_property(self):
        """chunk_count property should return len(chunks)."""
        from ai_lessons.search import GroupedResourceResult

        result = GroupedResourceResult(
            resource_id="res1",
            resource_title="Test",
            resource_type="doc",
            versions=[],
            tags=[],
            path=None,
            best_score=0.5,
            chunks=[],
        )
        assert result.chunk_count == 0

        chunk = ChunkResult(
            id="res1.0", title="Chunk", content="Content", score=0.5, result_type="",
            chunk_index=0, resource_id="res1",
        )
        result = GroupedResourceResult(
            resource_id="res1",
            resource_title="Test",
            resource_type="doc",
            versions=[],
            tags=[],
            path=None,
            best_score=0.5,
            chunks=[chunk],
        )
        assert result.chunk_count == 1
