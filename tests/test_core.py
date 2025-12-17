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


# --- v2 Tests ---


class TestResources:
    """Test resource operations (v2)."""

    def test_add_doc_resource(self, temp_config):
        """Test adding a doc resource."""
        resource_id = core.add_resource(
            type="doc",
            title="Test Doc",
            content="This is test documentation content.",
            versions=["v3"],
            tags=["test", "doc"],
            config=temp_config,
        )

        assert resource_id is not None
        assert len(resource_id) > 0

    def test_add_doc_without_version_defaults_to_unversioned(self, temp_config):
        """Test that docs without versions default to 'unversioned'."""
        resource_id = core.add_resource(
            type="doc",
            title="Unversioned Doc",
            content="Content without version.",
            config=temp_config,
        )

        resource = core.get_resource(resource_id, config=temp_config)
        assert resource.versions == ["unversioned"]

    def test_add_script_requires_path(self, temp_config):
        """Test that scripts require a path."""
        with pytest.raises(ValueError, match="Scripts require a path"):
            core.add_resource(
                type="script",
                title="Script without path",
                content="echo hello",
                config=temp_config,
            )

    def test_add_script_with_path(self, temp_config):
        """Test adding a script resource with path."""
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write("#!/bin/bash\necho 'Hello, World!'")
            script_path = f.name

        try:
            resource_id = core.add_resource(
                type="script",
                title="Test Script",
                path=script_path,
                versions=["v2", "v3"],
                tags=["test", "script"],
                config=temp_config,
            )

            resource = core.get_resource(resource_id, config=temp_config)
            assert resource is not None
            assert resource.type == "script"
            assert resource.title == "Test Script"
            assert resource.path == script_path
            assert "echo" in resource.content
            assert set(resource.versions) == {"v2", "v3"}
            assert set(resource.tags) == {"test", "script"}
        finally:
            import os
            os.unlink(script_path)

    def test_get_resource(self, temp_config):
        """Test getting a resource by ID."""
        resource_id = core.add_resource(
            type="doc",
            title="Get Test Doc",
            content="Content for get test.",
            versions=["v3"],
            tags=["get", "test"],
            config=temp_config,
        )

        resource = core.get_resource(resource_id, config=temp_config)

        assert resource is not None
        assert resource.id == resource_id
        assert resource.title == "Get Test Doc"
        assert resource.content == "Content for get test."
        assert "v3" in resource.versions
        assert "get" in resource.tags

    def test_get_nonexistent_resource(self, temp_config):
        """Test getting a resource that doesn't exist."""
        resource = core.get_resource("nonexistent-id", config=temp_config)
        assert resource is None

    def test_delete_resource(self, temp_config):
        """Test deleting a resource."""
        resource_id = core.add_resource(
            type="doc",
            title="To Delete",
            content="This will be deleted.",
            config=temp_config,
        )

        success = core.delete_resource(resource_id, config=temp_config)
        assert success is True

        resource = core.get_resource(resource_id, config=temp_config)
        assert resource is None

    def test_multi_version_resource(self, temp_config):
        """Test resource with multiple versions."""
        resource_id = core.add_resource(
            type="doc",
            title="Multi-version Doc",
            content="Works with multiple API versions.",
            versions=["v2", "v3", "v4"],
            config=temp_config,
        )

        resource = core.get_resource(resource_id, config=temp_config)
        assert set(resource.versions) == {"v2", "v3", "v4"}


class TestRules:
    """Test rule operations (v2)."""

    def test_suggest_rule(self, temp_config):
        """Test suggesting a rule."""
        rule_id = core.suggest_rule(
            title="Always GET before PUT",
            content="Always fetch the current state before updating.",
            rationale="PUT replaces entire resource; GET ensures you have current state.",
            tags=["api", "best-practice"],
            suggested_by="test-agent",
            config=temp_config,
        )

        assert rule_id is not None
        assert len(rule_id) > 0

    def test_suggest_rule_requires_rationale(self, temp_config):
        """Test that rules require rationale."""
        with pytest.raises(ValueError, match="Rationale is required"):
            core.suggest_rule(
                title="Rule without rationale",
                content="Some content.",
                rationale="",
                config=temp_config,
            )

    def test_rule_defaults_to_unapproved(self, temp_config):
        """Test that new rules are unapproved by default."""
        rule_id = core.suggest_rule(
            title="Unapproved Rule",
            content="This should not be approved yet.",
            rationale="Testing default approval status.",
            config=temp_config,
        )

        rule = core.get_rule(rule_id, config=temp_config)
        assert rule.approved is False
        assert rule.approved_at is None
        assert rule.approved_by is None

    def test_get_rule(self, temp_config):
        """Test getting a rule by ID."""
        rule_id = core.suggest_rule(
            title="Test Rule",
            content="Rule content.",
            rationale="Test rationale.",
            tags=["test", "rule"],
            suggested_by="tester",
            config=temp_config,
        )

        rule = core.get_rule(rule_id, config=temp_config)

        assert rule is not None
        assert rule.id == rule_id
        assert rule.title == "Test Rule"
        assert rule.content == "Rule content."
        assert rule.rationale == "Test rationale."
        assert "test" in rule.tags
        assert rule.suggested_by == "tester"

    def test_get_nonexistent_rule(self, temp_config):
        """Test getting a rule that doesn't exist."""
        rule = core.get_rule("nonexistent-id", config=temp_config)
        assert rule is None

    def test_approve_rule(self, temp_config):
        """Test approving a rule."""
        rule_id = core.suggest_rule(
            title="Rule to Approve",
            content="Will be approved.",
            rationale="For testing approval.",
            config=temp_config,
        )

        success = core.approve_rule(rule_id, approved_by="admin", config=temp_config)
        assert success is True

        rule = core.get_rule(rule_id, config=temp_config)
        assert rule.approved is True
        assert rule.approved_by == "admin"
        assert rule.approved_at is not None

    def test_reject_rule(self, temp_config):
        """Test rejecting (deleting) a rule."""
        rule_id = core.suggest_rule(
            title="Rule to Reject",
            content="Will be rejected.",
            rationale="For testing rejection.",
            config=temp_config,
        )

        success = core.reject_rule(rule_id, config=temp_config)
        assert success is True

        rule = core.get_rule(rule_id, config=temp_config)
        assert rule is None

    def test_list_pending_rules(self, temp_config):
        """Test listing pending (unapproved) rules."""
        # Create some rules
        rule1_id = core.suggest_rule(
            title="Pending Rule 1",
            content="Content 1.",
            rationale="Rationale 1.",
            config=temp_config,
        )
        rule2_id = core.suggest_rule(
            title="Pending Rule 2",
            content="Content 2.",
            rationale="Rationale 2.",
            config=temp_config,
        )
        rule3_id = core.suggest_rule(
            title="Approved Rule",
            content="Content 3.",
            rationale="Rationale 3.",
            config=temp_config,
        )

        # Approve one rule
        core.approve_rule(rule3_id, config=temp_config)

        # List pending rules
        pending = core.list_pending_rules(config=temp_config)

        assert len(pending) == 2
        pending_ids = [r.id for r in pending]
        assert rule1_id in pending_ids
        assert rule2_id in pending_ids
        assert rule3_id not in pending_ids

    def test_rule_with_linked_lesson(self, temp_config):
        """Test creating a rule linked to a lesson."""
        lesson_id = core.add_lesson(
            title="Related Lesson",
            content="This lesson relates to the rule.",
            config=temp_config,
        )

        rule_id = core.suggest_rule(
            title="Rule with Lesson Link",
            content="Rule content.",
            rationale="Based on the related lesson.",
            linked_lessons=[lesson_id],
            config=temp_config,
        )

        rule = core.get_rule(rule_id, config=temp_config)
        assert lesson_id in rule.linked_lessons

    def test_rule_with_linked_resource(self, temp_config):
        """Test creating a rule linked to a resource."""
        resource_id = core.add_resource(
            type="doc",
            title="Related Doc",
            content="Related documentation.",
            config=temp_config,
        )

        rule_id = core.suggest_rule(
            title="Rule with Resource Link",
            content="Rule content.",
            rationale="Based on the related resource.",
            linked_resources=[resource_id],
            config=temp_config,
        )

        rule = core.get_rule(rule_id, config=temp_config)
        assert resource_id in rule.linked_resources

    def test_link_to_rule(self, temp_config):
        """Test adding a link to an existing rule."""
        rule_id = core.suggest_rule(
            title="Rule to Link To",
            content="Rule content.",
            rationale="Will have links added.",
            config=temp_config,
        )

        lesson_id = core.add_lesson(
            title="Lesson to Link",
            content="Will be linked to the rule.",
            config=temp_config,
        )

        success = core.link_to_rule(
            rule_id, lesson_id, "lesson", config=temp_config
        )
        assert success is True

        rule = core.get_rule(rule_id, config=temp_config)
        assert lesson_id in rule.linked_lessons


class TestVersionMatching:
    """Test version matching logic (v2)."""

    def test_exact_match(self):
        """Test exact version match scores 1.0."""
        from ai_lessons.search import compute_version_score
        score = compute_version_score({"v2", "v3"}, {"v2", "v3"})
        assert score == 1.0

    def test_superset_match(self):
        """Test superset (resource has more) scores 0.95."""
        from ai_lessons.search import compute_version_score
        score = compute_version_score({"v2", "v3", "v4"}, {"v2", "v3"})
        assert score == 0.95

    def test_subset_match(self):
        """Test subset (resource has fewer) scores 0.85."""
        from ai_lessons.search import compute_version_score
        score = compute_version_score({"v3"}, {"v2", "v3"})
        assert score == 0.85

    def test_partial_overlap(self):
        """Test partial overlap scores 0.75."""
        from ai_lessons.search import compute_version_score
        score = compute_version_score({"v2", "v4"}, {"v2", "v3"})
        assert score == 0.75

    def test_unversioned(self):
        """Test unversioned resource scores 0.70."""
        from ai_lessons.search import compute_version_score
        score = compute_version_score({"unversioned"}, {"v2", "v3"})
        assert score == 0.70

    def test_disjoint_excluded(self):
        """Test disjoint versions return 0.0 (excluded)."""
        from ai_lessons.search import compute_version_score
        score = compute_version_score({"v1"}, {"v2", "v3"})
        assert score == 0.0

    def test_no_query_versions_matches_all(self):
        """Test empty query versions matches everything with 1.0."""
        from ai_lessons.search import compute_version_score
        score = compute_version_score({"v2", "v3"}, set())
        assert score == 1.0


class TestUnifiedSearch:
    """Test unified search across lessons, resources, and rules (v2)."""

    def test_search_resources(self, temp_config):
        """Test searching resources."""
        from ai_lessons.search import search_resources

        # Add a resource
        core.add_resource(
            type="doc",
            title="Jira Workflow API",
            content="Documentation about Jira workflow transitions and statuses.",
            versions=["v3"],
            tags=["jira", "api"],
            config=temp_config,
        )

        results = search_resources(
            "workflow transitions",
            config=temp_config,
        )

        assert len(results) > 0
        # Can return "resource" or "chunk" result type depending on scoring
        assert results[0].result_type in ("resource", "chunk")

    def test_search_resources_with_version_filter(self, temp_config):
        """Test searching resources with version filter."""
        from ai_lessons.search import search_resources

        # Add v2 and v3 resources
        core.add_resource(
            type="doc",
            title="V2 Only Doc",
            content="This doc is for version 2 only.",
            versions=["v2"],
            config=temp_config,
        )
        core.add_resource(
            type="doc",
            title="V3 Only Doc",
            content="This doc is for version 3 only.",
            versions=["v3"],
            config=temp_config,
        )

        # Search for v3 only
        results = search_resources(
            "doc version",
            versions=["v3"],
            config=temp_config,
        )

        # V2 doc should be excluded (disjoint)
        result_titles = [r.title for r in results]
        assert "V2 Only Doc" not in result_titles

    def test_rules_require_tag_overlap(self, temp_config):
        """Test that rules only surface with tag overlap."""
        from ai_lessons.search import search_rules

        # Add and approve a rule with specific tag
        rule_id = core.suggest_rule(
            title="Jira Specific Rule",
            content="Always GET before PUT on Jira.",
            rationale="PUT replaces entire resource.",
            tags=["jira"],
            config=temp_config,
        )
        core.approve_rule(rule_id, config=temp_config)

        # Search without any tags - rule should NOT surface
        results_no_tags = search_rules(
            "jira",
            config=temp_config,
        )
        assert len(results_no_tags) == 0

        # Search with matching tag - rule should surface
        results_with_tag = search_rules(
            "jira",
            tag_filter=["jira"],
            config=temp_config,
        )
        assert len(results_with_tag) > 0

    def test_unapproved_rules_not_in_search(self, temp_config):
        """Test that unapproved rules don't appear in search."""
        from ai_lessons.search import search_rules

        # Add but don't approve a rule
        core.suggest_rule(
            title="Unapproved Rule",
            content="This should not appear.",
            rationale="Testing unapproved rules.",
            tags=["test"],
            config=temp_config,
        )

        results = search_rules(
            "unapproved",
            tag_filter=["test"],
            config=temp_config,
        )

        assert len(results) == 0


class TestChunkStorage:
    """Test chunk storage integration (v3)."""

    def test_doc_creates_chunks(self, temp_config):
        """Test that adding a doc resource creates chunks."""
        from ai_lessons.chunking import ChunkingConfig
        from ai_lessons.db import get_db

        content = """# Title

## Section One

Content for section one.

## Section Two

Content for section two.

## Section Three

Content for section three.
"""
        # Use min_chunk_size=1 to prevent undersized merging
        resource_id = core.add_resource(
            type="doc",
            title="Chunked Doc",
            content=content,
            chunking_config=ChunkingConfig(min_chunk_size=1),
            config=temp_config,
        )

        # Verify chunks were created
        with get_db(temp_config) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM resource_chunks WHERE resource_id = ?",
                (resource_id,),
            )
            chunk_count = cursor.fetchone()[0]

        assert chunk_count >= 3  # At least 3 sections

    def test_chunks_have_metadata(self, temp_config):
        """Test that chunks have breadcrumb and line info."""
        from ai_lessons.chunking import ChunkingConfig
        from ai_lessons.db import get_db

        content = """# Main Title

## First Section

Some content here.

## Second Section

More content here.
"""
        # Use min_chunk_size=1 to prevent undersized merging
        resource_id = core.add_resource(
            type="doc",
            title="Doc with Metadata",
            content=content,
            chunking_config=ChunkingConfig(min_chunk_size=1),
            config=temp_config,
        )

        with get_db(temp_config) as conn:
            cursor = conn.execute(
                """
                SELECT chunk_index, title, breadcrumb, start_line, end_line, token_count
                FROM resource_chunks
                WHERE resource_id = ?
                ORDER BY chunk_index
                """,
                (resource_id,),
            )
            chunks = cursor.fetchall()

        # Verify we have chunks with metadata
        assert len(chunks) >= 2

        # Check that breadcrumbs are set
        for chunk in chunks:
            assert chunk["breadcrumb"] is not None
            assert "Main Title" in chunk["breadcrumb"]

        # Check line numbers are set
        for chunk in chunks:
            assert chunk["start_line"] is not None
            assert chunk["end_line"] is not None
            assert chunk["start_line"] <= chunk["end_line"]

        # Check token counts
        for chunk in chunks:
            assert chunk["token_count"] is not None
            assert chunk["token_count"] > 0

    def test_chunks_have_embeddings(self, temp_config):
        """Test that chunks have embeddings stored."""
        from ai_lessons.db import get_db

        content = """# API Reference

## GET /users

Returns a list of users.

## POST /users

Creates a new user.
"""
        resource_id = core.add_resource(
            type="doc",
            title="API Doc",
            content=content,
            config=temp_config,
        )

        with get_db(temp_config) as conn:
            # Get chunk IDs
            cursor = conn.execute(
                "SELECT id FROM resource_chunks WHERE resource_id = ?",
                (resource_id,),
            )
            chunk_ids = [row["id"] for row in cursor.fetchall()]

            # Check each chunk has an embedding
            for chunk_id in chunk_ids:
                cursor = conn.execute(
                    "SELECT chunk_id FROM chunk_embeddings WHERE chunk_id = ?",
                    (chunk_id,),
                )
                assert cursor.fetchone() is not None

    def test_custom_chunking_config(self, temp_config):
        """Test that custom chunking config is respected."""
        from ai_lessons.chunking import ChunkingConfig
        from ai_lessons.db import get_db

        content = """# Title

## Section A

### Subsection A.1

Content A.1.

### Subsection A.2

Content A.2.

## Section B

Content B.
"""
        # Only split on h3, not h2
        chunking_config = ChunkingConfig(
            strategy="headers",
            header_split_levels=[3],
            min_chunk_size=1,
        )

        resource_id = core.add_resource(
            type="doc",
            title="Custom Chunked Doc",
            content=content,
            chunking_config=chunking_config,
            config=temp_config,
        )

        with get_db(temp_config) as conn:
            cursor = conn.execute(
                "SELECT title FROM resource_chunks WHERE resource_id = ? ORDER BY chunk_index",
                (resource_id,),
            )
            titles = [row["title"] for row in cursor.fetchall()]

        # Should have chunks for A.1, A.2, and an intro chunk
        assert len(titles) == 3
        assert "Subsection A.1" in titles
        assert "Subsection A.2" in titles

    def test_delete_resource_deletes_chunks(self, temp_config):
        """Test that deleting a resource deletes its chunks."""
        from ai_lessons.db import get_db

        content = """# Title

## Section

Content.
"""
        resource_id = core.add_resource(
            type="doc",
            title="Doc to Delete",
            content=content,
            config=temp_config,
        )

        # Verify chunks exist
        with get_db(temp_config) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM resource_chunks WHERE resource_id = ?",
                (resource_id,),
            )
            assert cursor.fetchone()[0] > 0

        # Delete resource
        core.delete_resource(resource_id, config=temp_config)

        # Verify chunks are deleted (via CASCADE)
        with get_db(temp_config) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM resource_chunks WHERE resource_id = ?",
                (resource_id,),
            )
            assert cursor.fetchone()[0] == 0

    def test_script_no_chunks(self, temp_config):
        """Test that scripts don't create chunks."""
        import tempfile
        from ai_lessons.db import get_db

        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write("#!/bin/bash\necho 'Hello'")
            script_path = f.name

        try:
            resource_id = core.add_resource(
                type="script",
                title="Script No Chunks",
                path=script_path,
                config=temp_config,
            )

            with get_db(temp_config) as conn:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM resource_chunks WHERE resource_id = ?",
                    (resource_id,),
                )
                assert cursor.fetchone()[0] == 0
        finally:
            import os
            os.unlink(script_path)


class TestChunkSearch:
    """Tests for searching chunk embeddings."""

    def test_search_finds_chunk_content(self, temp_config):
        """Test that search finds content within specific chunks."""
        from ai_lessons.chunking import ChunkingConfig
        from ai_lessons.search import search_resources

        content = """# API Documentation

## User Endpoints

Create, read, update, and delete users.

## Order Endpoints

Manage customer orders and fulfillment tracking.

## Payment Endpoints

Process payments and handle refunds securely.
"""
        # Use min_chunk_size=1 to prevent merging
        core.add_resource(
            type="doc",
            title="API Docs",
            content=content,
            chunking_config=ChunkingConfig(min_chunk_size=1),
            config=temp_config,
        )

        # Search for content that's specifically in the Orders chunk
        results = search_resources(
            "customer orders fulfillment tracking",
            config=temp_config,
        )

        assert len(results) > 0
        # Should find it via chunk search
        found = results[0]
        assert "order" in found.content.lower() or "order" in found.title.lower()

    def test_chunk_results_include_breadcrumb(self, temp_config):
        """Test that chunk results include breadcrumb context."""
        from ai_lessons.chunking import ChunkingConfig
        from ai_lessons.search import search_resources

        content = """# Main Guide

## Installation

### Prerequisites

You need Python 3.10 or higher.

### Steps

Run pip install to setup.
"""
        core.add_resource(
            type="doc",
            title="Setup Guide",
            content=content,
            chunking_config=ChunkingConfig(
                strategy="headers",
                header_split_levels=[2, 3],
                min_chunk_size=1,
            ),
            config=temp_config,
        )

        # Search for prerequisites content
        results = search_resources(
            "Python 3.10 required",
            config=temp_config,
        )

        assert len(results) > 0
        # If it's a chunk result, should have breadcrumb info
        result = results[0]
        if result.result_type == "chunk":
            assert result.chunk_breadcrumb is not None or result.title is not None
            # Title should include hierarchy
            assert ">" in result.title or "Main Guide" in result.title or "Prerequisites" in result.title

    def test_deduplication_keeps_best_chunk(self, temp_config):
        """Test that multiple chunks from same resource return only best one."""
        from ai_lessons.chunking import ChunkingConfig
        from ai_lessons.search import search_resources

        content = """# Unique Document Title XYZ123

## Section Alpha

Alpha content about widgets.

## Section Beta

Beta content about widgets.

## Section Gamma

Gamma content about widgets.
"""
        resource_id = core.add_resource(
            type="doc",
            title="Widget Docs XYZ123",
            content=content,
            chunking_config=ChunkingConfig(min_chunk_size=1),
            config=temp_config,
        )

        # Search for something all chunks might match
        results = search_resources(
            "widgets content XYZ123",
            config=temp_config,
        )

        # Should only get one result per resource (deduplicated)
        result_resource_ids = []
        for r in results:
            rid = r.resource_id if r.resource_id else r.id
            result_resource_ids.append(rid)

        # The resource_id should appear at most once
        matching_results = [r for r in results if resource_id in (r.resource_id, r.id)]
        assert len(matching_results) <= 1

    def test_search_without_chunks(self, temp_config):
        """Test that include_chunks=False returns only resource-level results."""
        from ai_lessons.chunking import ChunkingConfig
        from ai_lessons.search import search_resources

        content = """# Test Doc

## Section One

Content for section one about unique topic ABC789.
"""
        core.add_resource(
            type="doc",
            title="Test Resource ABC789",
            content=content,
            chunking_config=ChunkingConfig(min_chunk_size=1),
            config=temp_config,
        )

        # Search with chunks disabled
        results = search_resources(
            "unique topic ABC789",
            include_chunks=False,
            config=temp_config,
        )

        # All results should be resource type, not chunk
        for result in results:
            assert result.result_type == "resource"

    def test_chunk_version_filtering(self, temp_config):
        """Test that chunk search respects version filtering."""
        from ai_lessons.chunking import ChunkingConfig
        from ai_lessons.search import search_resources

        content = """# Version Specific Doc

## Feature Description

This feature specific to version 3 only.
"""
        core.add_resource(
            type="doc",
            title="V3 Feature Doc",
            content=content,
            versions=["v3"],
            chunking_config=ChunkingConfig(min_chunk_size=1),
            config=temp_config,
        )

        # Search with v2 filter - should not find v3 doc
        results = search_resources(
            "feature specific version 3",
            versions=["v2"],
            config=temp_config,
        )

        # V3 doc should be excluded due to disjoint versions
        for result in results:
            assert "V3 Feature Doc" not in result.title
