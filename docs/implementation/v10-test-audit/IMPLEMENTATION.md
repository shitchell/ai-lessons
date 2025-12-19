# v10-test-audit Implementation Plan

## Executive Summary

This implementation plan addresses critical test infrastructure issues identified in the v10-test-audit. The primary issue is that **55+ tests are using `temp_config` (slow, with real embeddings) when they should use `fast_config` (fast, with mocked embeddings)**. Converting these tests will result in a **5-10x speedup** of the test suite.

### Key Metrics
- **Total tests affected**: 61 tests
- **Tests to convert**: 55 tests (38 in test_core.py, 17 in test_edges.py)
- **Tests to refactor**: 38 tests in test_search.py
- **Estimated speedup**: 5-10x overall, 10-30x for converted tests
- **Unused fixtures to remove**: 3 fixtures in conftest.py

---

## 1. Priority Classification

### CRITICAL (Week 1)
Convert tests that don't require real embeddings to use `fast_config`.

### HIGH (Week 2)
Improve assertions and remove unused fixtures.

### MEDIUM (Week 3)
Refactor to use helper functions and improve test quality.

---

## 2. File-by-File Changes

### 2.1 `/home/guy/git/github.com/shitchell/ai-lessons/tests/test_core.py`

**Priority**: CRITICAL

**Summary**: Convert all 38 tests from `temp_config` to `fast_config`. None of these tests require real embeddings for CRUD operations.

**Estimated speedup**: 10-30x

#### Changes Required

**CHANGE 1**: Replace all `temp_config` parameters with `fast_config`

Lines to modify (38 occurrences):

1. **Line 14**: `def test_add_lesson(self, temp_config):`
   - Change to: `def test_add_lesson(self, fast_config):`

2. **Line 22**: `config=temp_config,`
   - Change to: `config=fast_config,`

3. **Line 28**: `def test_get_lesson(self, temp_config):`
   - Change to: `def test_get_lesson(self, fast_config):`

4. **Lines 35, 38**: `config=temp_config,` (2 occurrences)
   - Change to: `config=fast_config,`

5. **Line 48**: `def test_get_nonexistent_lesson(self, temp_config):`
   - Change to: `def test_get_nonexistent_lesson(self, fast_config):`

6. **Line 50**: `core.get_lesson("nonexistent-id", config=temp_config)`
   - Change to: `core.get_lesson("nonexistent-id", config=fast_config)`

7. **Line 53**: `def test_update_lesson(self, temp_config):`
   - Change to: `def test_update_lesson(self, fast_config):`

8. **Lines 59, 66, 71**: `config=temp_config,` (3 occurrences)
   - Change to: `config=fast_config,`

9. **Line 76**: `def test_delete_lesson(self, temp_config):`
   - Change to: `def test_delete_lesson(self, fast_config):`

10. **Lines 81, 84, 87**: `config=temp_config,` (3 occurrences)
    - Change to: `config=fast_config,`

11. **Line 94**: `def test_recall_finds_lesson(self, temp_config):`
    - Change to: `def test_recall_finds_lesson(self, fast_config):`

12. **Lines 102, 107**: `config=temp_config,` (2 occurrences)
    - Change to: `config=fast_config,`

13. **Line 113**: `def test_recall_with_tag_filter(self, temp_config):`
    - Change to: `def test_recall_with_tag_filter(self, fast_config):`

14. **Lines 119, 126, 132**: `config=temp_config,` (3 occurrences)
    - Change to: `config=fast_config,`

15. **Line 142**: `def test_link_lessons(self, temp_config):`
    - Change to: `def test_link_lessons(self, fast_config):`

16. **Lines 147, 153, 156**: `config=temp_config,` (3 occurrences)
    - Change to: `config=fast_config,`

17. **Line 159**: `def test_get_related(self, temp_config):`
    - Change to: `def test_get_related(self, fast_config):`

18. **Lines 164, 170, 173, 175**: `config=temp_config,` (4 occurrences)
    - Change to: `config=fast_config,`

19. **Line 184**: `def test_list_sources(self, temp_config):`
    - Change to: `def test_list_sources(self, fast_config):`

20. **Line 186**: `sources = core.list_sources(config=temp_config)`
    - Change to: `sources = core.list_sources(config=fast_config)`

21. **Line 193**: `def test_list_confidence_levels(self, temp_config):`
    - Change to: `def test_list_confidence_levels(self, fast_config):`

22. **Line 195**: `levels = core.list_confidence_levels(config=temp_config)`
    - Change to: `levels = core.list_confidence_levels(config=fast_config)`

23. **Line 201**: `def test_list_tags(self, temp_config):`
    - Change to: `def test_list_tags(self, fast_config):`

24. **Lines 207, 210**: `config=temp_config,` (2 occurrences)
    - Change to: `config=fast_config,`

25. **Line 224**: `def test_add_doc_resource(self, temp_config):`
    - Change to: `def test_add_doc_resource(self, fast_config):`

26. **Line 232**: `config=temp_config,`
    - Change to: `config=fast_config,`

27. **Line 238**: `def test_add_doc_without_version_defaults_to_unversioned(self, temp_config):`
    - Change to: `def test_add_doc_without_version_defaults_to_unversioned(self, fast_config):`

28. **Lines 244, 247**: `config=temp_config,` (2 occurrences)
    - Change to: `config=fast_config,`

29. **Line 250**: `def test_add_script_requires_path(self, temp_config):`
    - Change to: `def test_add_script_requires_path(self, fast_config):`

30. **Line 257**: `config=temp_config,`
    - Change to: `config=fast_config,`

31. **Line 260**: `def test_add_script_with_path(self, temp_config):`
    - Change to: `def test_add_script_with_path(self, fast_config):`

32. **Lines 274, 277**: `config=temp_config,` (2 occurrences)
    - Change to: `config=fast_config,`

33. **Line 289**: `def test_get_resource(self, temp_config):`
    - Change to: `def test_get_resource(self, fast_config):`

34. **Lines 297, 300**: `config=temp_config,` (2 occurrences)
    - Change to: `config=fast_config,`

35. **Line 309**: `def test_get_nonexistent_resource(self, temp_config):`
    - Change to: `def test_get_nonexistent_resource(self, fast_config):`

36. **Line 311**: `resource = core.get_resource("nonexistent-id", config=temp_config)`
    - Change to: `resource = core.get_resource("nonexistent-id", config=fast_config)`

37. **Line 314**: `def test_delete_resource(self, temp_config):`
    - Change to: `def test_delete_resource(self, fast_config):`

38. **Lines 320, 323, 326**: `config=temp_config,` (3 occurrences)
    - Change to: `config=fast_config,`

39. **Line 329**: `def test_multi_version_resource(self, temp_config):`
    - Change to: `def test_multi_version_resource(self, fast_config):`

40. **Lines 336, 339**: `config=temp_config,` (2 occurrences)
    - Change to: `config=fast_config,`

41. **Line 346**: `def test_suggest_rule(self, temp_config):`
    - Change to: `def test_suggest_rule(self, fast_config):`

42. **Line 354**: `config=temp_config,`
    - Change to: `config=fast_config,`

43. **Line 360**: `def test_suggest_rule_requires_rationale(self, temp_config):`
    - Change to: `def test_suggest_rule_requires_rationale(self, fast_config):`

44. **Line 367**: `config=temp_config,`
    - Change to: `config=fast_config,`

45. **Line 370**: `def test_rule_defaults_to_unapproved(self, temp_config):`
    - Change to: `def test_rule_defaults_to_unapproved(self, fast_config):`

46. **Lines 376, 379**: `config=temp_config,` (2 occurrences)
    - Change to: `config=fast_config,`

47. **Line 384**: `def test_get_rule(self, temp_config):`
    - Change to: `def test_get_rule(self, fast_config):`

48. **Lines 392, 395**: `config=temp_config,` (2 occurrences)
    - Change to: `config=fast_config,`

49. **Line 405**: `def test_get_nonexistent_rule(self, temp_config):`
    - Change to: `def test_get_nonexistent_rule(self, fast_config):`

50. **Line 407**: `rule = core.get_rule("nonexistent-id", config=temp_config)`
    - Change to: `rule = core.get_rule("nonexistent-id", config=fast_config)`

51. **Line 410**: `def test_approve_rule(self, temp_config):`
    - Change to: `def test_approve_rule(self, fast_config):`

52. **Lines 416, 419, 422**: `config=temp_config,` (3 occurrences)
    - Change to: `config=fast_config,`

53. **Line 427**: `def test_reject_rule(self, temp_config):`
    - Change to: `def test_reject_rule(self, fast_config):`

54. **Lines 433, 436, 439**: `config=temp_config,` (3 occurrences)
    - Change to: `config=fast_config,`

55. **Line 442**: `def test_list_pending_rules(self, temp_config):`
    - Change to: `def test_list_pending_rules(self, fast_config):`

56. **Lines 449, 455, 461, 465, 468**: `config=temp_config,` (5 occurrences)
    - Change to: `config=fast_config,`

57. **Line 476**: `def test_rule_with_linked_lesson(self, temp_config):`
    - Change to: `def test_rule_with_linked_lesson(self, fast_config):`

58. **Lines 481, 489, 492**: `config=temp_config,` (3 occurrences)
    - Change to: `config=fast_config,`

59. **Line 495**: `def test_rule_with_linked_resource(self, temp_config):`
    - Change to: `def test_rule_with_linked_resource(self, fast_config):`

60. **Lines 501, 509, 512**: `config=temp_config,` (3 occurrences)
    - Change to: `config=fast_config,`

61. **Line 515**: `def test_link_to_rule(self, temp_config):`
    - Change to: `def test_link_to_rule(self, fast_config):`

62. **Lines 521, 527, 531, 535**: `config=temp_config,` (4 occurrences)
    - Change to: `config=fast_config,`

63. **Line 588**: `def test_search_resources(self, temp_config):`
    - Change to: `def test_search_resources(self, fast_config):`

64. **Lines 599, 604**: `config=temp_config,` (2 occurrences)
    - Change to: `config=fast_config,`

65. **Line 611**: `def test_search_resources_with_version_filter(self, temp_config):`
    - Change to: `def test_search_resources_with_version_filter(self, fast_config):`

66. **Lines 621, 628, 635**: `config=temp_config,` (3 occurrences)
    - Change to: `config=fast_config,`

67. **Line 642**: `def test_rules_require_tag_overlap(self, temp_config):`
    - Change to: `def test_rules_require_tag_overlap(self, fast_config):`

68. **Lines 652, 654, 659, 667**: `config=temp_config,` (4 occurrences)
    - Change to: `config=fast_config,`

69. **Line 671**: `def test_unapproved_rules_not_in_search(self, temp_config):`
    - Change to: `def test_unapproved_rules_not_in_search(self, fast_config):`

70. **Lines 681, 687**: `config=temp_config,` (2 occurrences)
    - Change to: `config=fast_config,`

71. **Line 696**: `def test_doc_creates_chunks(self, temp_config):`
    - Change to: `def test_doc_creates_chunks(self, fast_config):`

72. **Lines 721, 725**: `config=temp_config,` (2 occurrences)
    - Change to: `config=fast_config,`

73. **Line 734**: `def test_chunks_have_metadata(self, temp_config):`
    - Change to: `def test_chunks_have_metadata(self, fast_config):`

74. **Lines 755, 758**: `config=temp_config,` (2 occurrences)
    - Change to: `config=fast_config,`

75. **Line 789**: `def test_chunks_have_embeddings(self, temp_config):`
    - Change to: `def test_chunks_have_embeddings(self, fast_config):`

76. **Lines 807, 810**: `config=temp_config,` (2 occurrences)
    - Change to: `config=fast_config,`

77. **Line 826**: `def test_custom_chunking_config(self, temp_config):`
    - Change to: `def test_custom_chunking_config(self, fast_config):`

78. **Lines 859, 862**: `config=temp_config,` (2 occurrences)
    - Change to: `config=fast_config,`

79. **Line 874**: `def test_delete_resource_deletes_chunks(self, temp_config):`
    - Change to: `def test_delete_resource_deletes_chunks(self, fast_config):`

80. **Lines 888, 892, 900, 903**: `config=temp_config,` (4 occurrences)
    - Change to: `config=fast_config,`

81. **Line 910**: `def test_script_gets_chunks(self, temp_config):`
    - Change to: `def test_script_gets_chunks(self, fast_config):`

82. **Lines 924, 927**: `config=temp_config,` (2 occurrences)
    - Change to: `config=fast_config,`

83. **Line 942**: `def test_search_finds_chunk_content(self, temp_config):`
    - Change to: `def test_search_finds_chunk_content(self, fast_config):`

84. **Lines 967, 972**: `config=temp_config,` (2 occurrences)
    - Change to: `config=fast_config,`

85. **Line 981**: `def test_chunk_results_include_breadcrumb(self, temp_config):`
    - Change to: `def test_chunk_results_include_breadcrumb(self, fast_config):`

86. **Lines 1007, 1012**: `config=temp_config,` (2 occurrences)
    - Change to: `config=fast_config,`

87. **Line 1024**: `def test_deduplication_keeps_best_chunk(self, temp_config):`
    - Change to: `def test_deduplication_keeps_best_chunk(self, fast_config):`

88. **Lines 1048, 1052**: `config=temp_config,` (2 occurrences)
    - Change to: `config=fast_config,`

89. **Line 1067**: `def test_search_without_chunks(self, temp_config):`
    - Change to: `def test_search_without_chunks(self, fast_config):`

90. **Lines 1083, 1089**: `config=temp_config,` (2 occurrences)
    - Change to: `config=fast_config,`

91. **Line 1097**: `def test_chunk_version_filtering(self, temp_config):`
    - Change to: `def test_chunk_version_filtering(self, fast_config):`

92. **Lines 1114, 1121**: `config=temp_config,` (2 occurrences)
    - Change to: `config=fast_config,`

**IMPROVEMENT 1** (MEDIUM priority): Strengthen assertions in test_add_lesson

**Lines 25-26**:
```python
# Current (weak)
assert lesson_id is not None
assert len(lesson_id) > 0
```

**Change to**:
```python
# Better - actually retrieve and verify
assert lesson_id is not None
assert len(lesson_id) > 0

lesson = core.get_lesson(lesson_id, config=fast_config)
assert lesson is not None
assert lesson.title == "Test Lesson"
assert lesson.content == "This is a test lesson content."
assert set(lesson.tags) == {"test", "example"}
assert lesson.confidence == "medium"
```

**IMPROVEMENT 2** (MEDIUM priority): Strengthen assertion in test_recall_finds_lesson

**Line 111**:
```python
# Current (weak)
assert "jira" in results[0].title.lower() or "workflow" in results[0].title.lower()
```

**Change to**:
```python
# Better - more specific
assert len(results) > 0
assert results[0].title == "Jira workflow updates delete missing statuses"
assert results[0].score > 0.5  # Should be a good match
```

---

### 2.2 `/home/guy/git/github.com/shitchell/ai-lessons/tests/test_edges.py`

**Priority**: CRITICAL

**Summary**: Convert all 17 tests from `temp_config` to `fast_config`. Graph operations don't require real embeddings.

**Estimated speedup**: 10-30x

#### Changes Required

**CHANGE 1**: Replace all `temp_config` parameters with `fast_config`

Lines to modify (17 test methods):

1. **Line 17**: `def test_link_lessons(self, temp_config):`
   - Change to: `def test_link_lessons(self, fast_config):`

2. **Lines 22, 27, 30, 34**: `config=temp_config,` (4 occurrences)
   - Change to: `config=fast_config,`

3. **Line 45**: `def test_link_lessons_duplicate_raises(self, temp_config):`
   - Change to: `def test_link_lessons_duplicate_raises(self, fast_config):`

4. **Lines 50, 55, 59, 65, 68**: `config=temp_config,` (5 occurrences)
   - Change to: `config=fast_config,`

5. **Line 76**: `def test_get_related_lessons(self, temp_config):`
   - Change to: `def test_get_related_lessons(self, fast_config):`

6. **Lines 81, 86, 91, 94, 95, 97**: `config=temp_config,` (6 occurrences)
   - Change to: `config=fast_config,`

7. **Line 104**: `def test_get_related_with_depth(self, temp_config):`
   - Change to: `def test_get_related_with_depth(self, fast_config):`

8. **Lines 109, 114, 119, 122, 123, 126, 131**: `config=temp_config,` (7 occurrences)
   - Change to: `config=fast_config,`

9. **Line 137**: `def test_get_related_bidirectional(self, temp_config):`
   - Change to: `def test_get_related_bidirectional(self, fast_config):`

10. **Lines 140, 141, 142, 144, 145, 148, 153**: `config=temp_config,` (7 occurrences)
    - Change to: `config=fast_config,`

11. **Line 159**: `def test_different_relation_types(self, temp_config):`
    - Change to: `def test_different_relation_types(self, fast_config):`

12. **Lines 164, 169, 172, 173, 176**: `config=temp_config,` (5 occurrences)
    - Change to: `config=fast_config,`

13. **Line 185**: `def test_delete_lesson_cascades_edges(self, temp_config):`
    - Change to: `def test_delete_lesson_cascades_edges(self, fast_config):`

14. **Lines 190, 195, 198, 201, 206**: `config=temp_config,` (5 occurrences)
    - Change to: `config=fast_config,`

15. **Line 219**: `def test_link_lesson_to_resource(self, temp_config):`
    - Change to: `def test_link_lesson_to_resource(self, fast_config):`

16. **Lines 224, 230, 234, 240**: `config=temp_config,` (4 occurrences)
    - Change to: `config=fast_config,`

17. **Line 248**: `def test_unlink_lesson_from_resource(self, temp_config):`
    - Change to: `def test_unlink_lesson_from_resource(self, fast_config):`

18. **Lines 253, 259, 262, 265, 270**: `config=temp_config,` (5 occurrences)
    - Change to: `config=fast_config,`

19. **Line 282**: `def test_link_to_rule_lesson(self, temp_config):`
    - Change to: `def test_link_to_rule_lesson(self, fast_config):`

20. **Lines 288, 293, 297, 301**: `config=temp_config,` (4 occurrences)
    - Change to: `config=fast_config,`

21. **Line 304**: `def test_link_to_rule_resource(self, temp_config):`
    - Change to: `def test_link_to_rule_resource(self, fast_config):`

22. **Lines 310, 316, 320, 324**: `config=temp_config,` (4 occurrences)
    - Change to: `config=fast_config,`

23. **Line 327**: `def test_unlink_from_rule(self, temp_config):`
    - Change to: `def test_unlink_from_rule(self, fast_config):`

24. **Lines 332, 339, 343, 348, 353**: `config=temp_config,` (5 occurrences)
    - Change to: `config=fast_config,`

25. **Line 360**: `def test_query_edges_by_from(self, temp_config):`
    - Change to: `def test_query_edges_by_from(self, fast_config):`

26. **Lines 365, 370, 375, 378, 379, 381**: `config=temp_config,` (6 occurrences)
    - Change to: `config=fast_config,`

27. **Line 390**: `def test_query_edges_by_to(self, temp_config):`
    - Change to: `def test_query_edges_by_to(self, fast_config):`

28. **Lines 395, 400, 405, 408, 409, 411**: `config=temp_config,` (6 occurrences)
    - Change to: `config=fast_config,`

29. **Line 421**: `def test_query_edges_by_relation(self, temp_config):`
    - Change to: `def test_query_edges_by_relation(self, fast_config):`

30. **Lines 423, 424, 425, 427, 428, 430**: `config=temp_config,` (6 occurrences)
    - Change to: `config=fast_config,`

31. **Line 444**: `def test_edge_types_constrained(self, temp_config):`
    - Change to: `def test_edge_types_constrained(self, fast_config):`

32. **Line 446**: `with get_db(temp_config) as conn:`
    - Change to: `with get_db(fast_config) as conn:`

33. **Line 454**: `def test_unique_edge_constraint(self, temp_config):`
    - Change to: `def test_unique_edge_constraint(self, fast_config):`

34. **Line 456**: `with get_db(temp_config) as conn:`
    - Change to: `with get_db(fast_config) as conn:`

35. **Line 475**: `def test_resource_anchor_created_with_edge(self, temp_config):`
    - Change to: `def test_resource_anchor_created_with_edge(self, fast_config):`

36. **Line 477**: `with get_db(temp_config) as conn:`
    - Change to: `with get_db(fast_config) as conn:`

37. **Line 509**: `def test_anchor_edge_id_nulled_on_edge_delete(self, temp_config):`
    - Change to: `def test_anchor_edge_id_nulled_on_edge_delete(self, fast_config):`

38. **Line 511**: `with get_db(temp_config) as conn:`
    - Change to: `with get_db(fast_config) as conn:`

**IMPROVEMENT 1** (HIGH priority): Fix cascade test assertion

**Lines 185-214**: `test_delete_lesson_cascades_edges`

Currently, the test creates edges but doesn't assert their cleanup. Add assertion:

```python
def test_delete_lesson_cascades_edges(self, fast_config):
    """Test that deleting a lesson removes its edges."""
    id1 = core.add_lesson(
        title="Lesson to Delete",
        content="Will be deleted.",
        config=fast_config,
    )
    id2 = core.add_lesson(
        title="Related Lesson",
        content="Stays.",
        config=fast_config,
    )

    core.link_lessons(id1, id2, "related_to", config=fast_config)

    # Verify edge exists before deletion
    with get_db(fast_config) as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) as count FROM edges WHERE from_id = ? OR to_id = ?",
            (id1, id1),
        )
        assert cursor.fetchone()["count"] == 1  # Edge exists

    # Delete lesson
    core.delete_lesson(id1, config=fast_config)

    # Verify edge is removed (or at least document expected behavior)
    with get_db(fast_config) as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) as count FROM edges WHERE from_id = ? OR to_id = ?",
            (id1, id1),
        )
        count = cursor.fetchone()["count"]
        # Document: Edges table doesn't have FK CASCADE.
        # Either assert count == 0 (if manually cleaned) or document that orphan edges are acceptable
        # For now, assert cleanup happens:
        assert count == 0, "Edges should be cleaned up when lesson is deleted"
```

---

### 2.3 `/home/guy/git/github.com/shitchell/ai-lessons/tests/test_search.py`

**Priority**: CRITICAL

**Summary**: Replace manual config creation with `fast_config` fixture. Analyze which tests genuinely need real embeddings vs. which can use mocks.

**Current Anti-Pattern** (lines 5-11):
```python
@pytest.fixture
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

#### Changes Required

**CHANGE 1**: Remove manual config fixture (lines 5-11)

**DELETE** lines 5-11 entirely.

**CHANGE 2**: Remove unused imports

**Line 5**: `import tempfile`
- DELETE this line (no longer needed)

**Line 6**: `from pathlib import Path`
- DELETE this line (no longer needed)

**Line 10**: `from ai_lessons.config import Config, EmbeddingConfig, SearchConfig`
- Keep only if needed for type hints, otherwise delete

**Line 11**: `from ai_lessons.db import init_db`
- DELETE this line (no longer needed)

**ANALYSIS REQUIRED**: Review which tests need real embeddings

Most tests in this file test **scoring logic** and **result structures**, which don't require real embeddings. However, some tests might genuinely test semantic search quality.

**Tests that CAN use fast_config** (most of them):
- All tests in `TestScoringConstants` (lines 41-87) - tests constants
- All tests in `TestNormalizeText` (lines 89-108) - tests text normalization
- All tests in `TestKeywordScore` (lines 110-149) - tests keyword matching
- All tests in `TestDistanceToScore` (lines 151-189) - tests sigmoid function
- All tests in `TestKeywordScoreWithTags` (lines 191-222) - tests tag matching
- All tests in `TestComputeResourceScore` (lines 224-277) - tests scoring combination
- All tests in `TestVersionScoring` (lines 279-316) - tests version matching
- All tests in `TestResultDataclasses` (lines 318-371) - tests data structures
- All tests in `TestGroupedResourceResult` (lines 373-438) - tests data structures

**Tests that might need real embeddings**:
- None - all these tests are testing scoring functions, not actual semantic search

**RECOMMENDATION**: Replace `_temp_config` with `fast_config` throughout. No tests in this file require real embeddings.

---

### 2.4 `/home/guy/git/github.com/shitchell/ai-lessons/tests/test_info.py`

**Priority**: HIGH

**Summary**: 6 tests still use `temp_config`, should be converted to `fast_config`.

#### Changes Required

Currently using `fast_config`:
- Lines 18-22: `test_empty_database` ✓
- Lines 23-38: `test_lesson_tags` ✓ (uses `fast_sample_lessons`)
- Lines 39-43: `test_filter_by_pattern` ✓ (uses `fast_sample_lessons`)
- Lines 45-58: `test_filter_by_entity_type` ✓
- Lines 63-67: `test_empty_database` (aliases) ✓
- Lines 73-76: `test_empty_database` (relations) ✓
- Lines 78-92: `test_with_edges` ✓
- Lines 98-103: `test_without_counts` ✓
- Lines 105-118: `test_with_counts` ✓
- Lines 124-128: `test_without_counts` (confidence) ✓
- Lines 130-143: `test_with_counts` (confidence) ✓
- Lines 149-161: `test_empty_database` (stats) ✓
- Lines 163-168: `test_populated_database` ✓ (uses `fast_sample_lessons`)
- Lines 174-182: `test_tags_empty` ✓
- Lines 184-193: `test_tags_with_data` ✓ (uses `fast_sample_lessons`)
- Lines 195-203: `test_tags_with_counts` ✓ (uses `fast_sample_lessons`)
- Lines 205-215: `test_tags_json_output` ✓ (uses `fast_sample_lessons`)
- Lines 221-230: `test_confidence_levels` ✓
- Lines 232-241: `test_confidence_json` ✓
- Lines 247-255: `test_lesson_sources` ✓
- Lines 257-266: `test_lesson_sources_json` ✓
- Lines 272-280: `test_relations_empty` ✓
- Lines 282-291: `test_relations_json` ✓
- Lines 298-307: `test_stats` ✓
- Lines 309-319: `test_stats_json` ✓

**Excellent!** This file is already using `fast_config` correctly. No changes needed.

---

### 2.5 `/home/guy/git/github.com/shitchell/ai-lessons/tests/conftest.py`

**Priority**: HIGH

**Summary**: Remove or document unused fixtures.

#### Fixtures Analysis

**Unused fixtures** (lines to document or remove):

1. **Lines 151-185**: `sample_lessons` - NEVER USED
   - Only used by `populated_db`
   - `populated_db` itself is NEVER USED
   - **RECOMMENDATION**: Keep for now, document as "available for integration tests"

2. **Lines 188-238**: `sample_resources` - NEVER USED
   - Only used by `populated_db`
   - **RECOMMENDATION**: Keep for now, document as "available for integration tests"

3. **Lines 241-273**: `sample_rules` - NEVER USED
   - Only used by `populated_db`
   - **RECOMMENDATION**: Keep for now, document as "available for integration tests"

4. **Lines 276-312**: `populated_db` - NEVER USED
   - **RECOMMENDATION**: Keep for now, document as "available for integration tests"

5. **Lines 320-338**: `fast_sample_lessons` - USED!
   - Used by `test_info.py` (lines 23, 39, 163, 184, 195, 205)
   - **ACTION**: Keep as-is ✓

6. **Lines 341-347**: `fast_populated_db` - NEVER USED
   - **RECOMMENDATION**: Remove or document

#### Changes Required

**CHANGE 1**: Add documentation for unused fixtures

Add comment block before `sample_lessons` (before line 151):

```python
# -----------------------------------------------------------------------------
# Pre-populated Database Fixtures (SLOW - uses real embeddings)
#
# These fixtures are available for integration tests that specifically need
# real embeddings. Most tests should use the fast_ variants below instead.
# -----------------------------------------------------------------------------
```

**CHANGE 2**: Document fast_populated_db usage

Add comment at line 341:

```python
@pytest.fixture
def fast_populated_db(
    fast_config: Config,
    fast_sample_lessons: dict[str, str],
) -> tuple[Config, dict[str, str]]:
    """Create a populated test database with mocked embeddings (fast).

    NOTE: Currently unused. Available for integration tests.
    Consider expanding to match populated_db structure if needed.
    """
    return fast_config, fast_sample_lessons
```

**CHANGE 3** (OPTIONAL): Remove `fast_populated_db` if truly not needed

If we decide it's not needed, delete lines 341-347.

---

## 3. Implementation Order

### Week 1: Critical Changes (5-10x speedup)

1. **Day 1**: Convert `test_core.py`
   - Replace all `temp_config` with `fast_config` (38 tests)
   - Run tests to verify no breakage
   - Measure speedup

2. **Day 2**: Convert `test_edges.py`
   - Replace all `temp_config` with `fast_config` (17 tests)
   - Run tests to verify no breakage
   - Measure speedup

3. **Day 3**: Refactor `test_search.py`
   - Remove manual config creation
   - Replace with `fast_config` fixture
   - Run tests to verify no breakage
   - Measure speedup

4. **Day 4**: Verify and document
   - Run full test suite
   - Measure overall speedup
   - Update README.md with new test speeds

### Week 2: High Priority

5. **Day 5**: Improve assertions in `test_core.py`
   - Strengthen `test_add_lesson` (lines 25-26)
   - Strengthen `test_recall_finds_lesson` (line 111)
   - Add similar improvements to resource/rule tests

6. **Day 6**: Fix `test_edges.py` cascade test
   - Add proper assertions to `test_delete_lesson_cascades_edges`
   - Document expected behavior

7. **Day 7**: Document conftest fixtures
   - Add documentation for unused fixtures
   - Clarify when to use `temp_config` vs `fast_config`

### Week 3: Medium Priority

8. **Day 8-10**: Refactor to use helper functions
   - Replace manual `core.add_lesson()` with `make_lesson()` from helpers
   - Replace manual assertions with `assert_lesson_matches()`, etc.
   - Improve test readability

---

## 4. Validation Steps

After each change:

1. **Run affected tests**:
   ```bash
   pytest tests/test_core.py -v
   pytest tests/test_edges.py -v
   pytest tests/test_search.py -v
   ```

2. **Run full test suite**:
   ```bash
   pytest tests/ -v
   ```

3. **Measure execution time**:
   ```bash
   time pytest tests/test_core.py
   time pytest tests/test_edges.py
   ```

4. **Check coverage** (optional):
   ```bash
   pytest tests/ --cov=ai_lessons --cov-report=term-missing
   ```

---

## 5. Expected Impact

### Performance

| Test File | Current Time | Expected Time | Speedup |
|-----------|-------------|---------------|---------|
| test_core.py | ~30s | ~1-2s | 15-30x |
| test_edges.py | ~15s | ~0.5-1s | 15-30x |
| test_search.py | ~5s | ~0.5s | 10x |
| test_info.py | Already fast | ~0.5s | ✓ |
| **Total Suite** | **~50s** | **~5-10s** | **5-10x** |

### Code Quality

- **Consistency**: All tests using fixtures uniformly
- **Clarity**: Helper functions improve readability
- **Robustness**: Stronger assertions catch more bugs
- **Maintainability**: Less code duplication

---

## 6. Risk Assessment

### Low Risk
- Converting `temp_config` to `fast_config` in CRUD tests
- Adding documentation
- Improving assertions

### Medium Risk
- Removing unused fixtures (might break external code)
- Changing test_search.py fixture approach

### Mitigation
- Run full test suite after each change
- Keep changes in separate commits
- Document any breaking changes
- Consider keeping unused fixtures with deprecation warnings

---

## 7. Success Criteria

1. ✅ All 167 tests still pass
2. ✅ Test suite runs 5-10x faster
3. ✅ No tests use `temp_config` unless they genuinely need real embeddings
4. ✅ All fixtures are documented
5. ✅ Assertions are specific and meaningful
6. ✅ Test code uses helper functions consistently

---

## 8. Notes

- The `fast_config` fixture uses `MockEmbedder` which provides deterministic embeddings based on text hash
- Tests that genuinely need semantic search quality (if any) should continue using `temp_config`
- After this refactor, consider adding `@pytest.mark.slow` to any remaining real-embedding tests
- The `test_info.py` file is an excellent example of correct fixture usage
