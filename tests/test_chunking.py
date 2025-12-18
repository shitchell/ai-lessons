"""Tests for document chunking."""

import pytest

from ai_lessons.chunking import (
    Chunk,
    ChunkingConfig,
    ChunkingResult,
    chunk_by_delimiter,
    chunk_by_headers,
    chunk_document,
    chunk_fixed_size,
    detect_strategy,
    estimate_tokens,
)


class TestTokenEstimation:
    """Test token estimation."""

    def test_estimate_tokens_basic(self):
        """Test basic token estimation."""
        # 11 chars / 4 = 2
        assert estimate_tokens("hello world") == 2

    def test_estimate_tokens_empty(self):
        """Test empty string."""
        assert estimate_tokens("") == 0

    def test_estimate_tokens_longer(self):
        """Test longer text."""
        # 100 chars / 4 = 25
        text = "a" * 100
        assert estimate_tokens(text) == 25


class TestStrategyDetection:
    """Test strategy auto-detection."""

    def test_detect_small_document(self):
        """Small documents should use 'single' strategy (not 'none')."""
        content = "Short doc"
        strategy, reason = detect_strategy(content, ChunkingConfig())
        assert strategy == "single"
        assert "single chunk" in reason

    def test_detect_markdown_headers(self):
        """Documents with headers should use 'headers' strategy."""
        content = """# Title

## Section 1

Content here with enough text to make this section reasonably sized.

## Section 2

More content with additional text to ensure adequate length.

## Section 3

Even more content to make sure we have enough tokens.
""" + ("Additional padding text. " * 50)  # Ensure > 200 tokens
        strategy, reason = detect_strategy(content, ChunkingConfig())
        assert strategy == "headers"
        assert "markdown headers" in reason

    def test_detect_delimiter(self):
        """Documents with delimiters should use 'delimiter' strategy."""
        content = """Part 1 with some content here to make it long enough.

---

Part 2 with additional content for adequate size.

---

Part 3 has more text content here.

---

Part 4 also needs sufficient length.
""" + ("Padding text for size. " * 50)  # Ensure > 200 tokens
        strategy, reason = detect_strategy(content, ChunkingConfig())
        assert strategy == "delimiter"
        assert "horizontal rules" in reason

    def test_detect_fallback_to_fixed(self):
        """Long unstructured documents should use 'fixed' strategy."""
        content = "A " * 1000  # Long but no structure
        strategy, reason = detect_strategy(content, ChunkingConfig())
        assert strategy == "fixed"
        assert "no clear structure" in reason


class TestHeaderChunking:
    """Test header-based chunking."""

    def test_basic_h2_split(self):
        """Test splitting on h2 headers."""
        content = """# Title

Intro paragraph.

## Section One

Content for section one.

## Section Two

Content for section two.
"""
        # Use min_chunk_size=1 to prevent undersized merging
        result = chunk_document(content, ChunkingConfig(strategy="headers", min_chunk_size=1))

        assert len(result.chunks) == 3
        assert result.chunks[0].breadcrumb == "Title"
        assert result.chunks[1].breadcrumb == "Title > Section One"
        assert result.chunks[2].breadcrumb == "Title > Section Two"

    def test_nested_headers(self):
        """Test that h3 stays with parent h2 when not in split levels."""
        content = """# Title

## A

### A.1

Content for A.1.

## B

Content for B.
"""
        config = ChunkingConfig(strategy="headers", header_split_levels=[2], min_chunk_size=1)
        result = chunk_document(content, config)

        # h3 should NOT trigger split, stays with parent h2
        assert len(result.chunks) == 3  # intro, A (with A.1), B

    def test_split_on_h3_too(self):
        """Test splitting on both h2 and h3."""
        content = """# Title

## A

### A.1

Content.

### A.2

More content.

## B

Content.
"""
        config = ChunkingConfig(strategy="headers", header_split_levels=[2, 3], min_chunk_size=1)
        result = chunk_document(content, config)

        # Should split on both h2 and h3
        assert len(result.chunks) >= 4

    def test_breadcrumb_depth(self):
        """Test that breadcrumbs track hierarchy correctly."""
        content = """# L1

## L2

### L3

Content.
"""
        config = ChunkingConfig(strategy="headers", header_split_levels=[2, 3], min_chunk_size=1)
        result = chunk_document(content, config)

        # Find the chunk with L3
        l3_chunk = [c for c in result.chunks if c.title == "L3"]
        assert len(l3_chunk) == 1
        assert l3_chunk[0].breadcrumb == "L1 > L2 > L3"

    def test_empty_sections_not_created(self):
        """Test that consecutive headers don't create empty chunks."""
        content = """# Title

## Section 1
## Section 2

Content here.
"""
        result = chunk_document(content, ChunkingConfig(strategy="headers", min_chunk_size=1))

        # Section 1 should have minimal content (just its header line)
        # Both should be created but Section 1 will be small
        assert len(result.chunks) >= 2


class TestFixedSizeChunking:
    """Test fixed-size chunking."""

    def test_basic_fixed_split(self):
        """Test basic fixed-size splitting."""
        # Use multi-line content (algorithm is line-based)
        content = "\n".join(["This is line number " + str(i) + " with some content." for i in range(100)])
        config = ChunkingConfig(strategy="fixed", fixed_chunk_size=200, min_chunk_size=1)
        result = chunk_document(content, config)

        assert len(result.chunks) >= 2

    def test_overlap(self):
        """Test that chunks have overlap."""
        content = "The quick brown fox jumps over the lazy dog. " * 50
        config = ChunkingConfig(
            strategy="fixed", fixed_chunk_size=100, fixed_overlap=20
        )
        result = chunk_document(content, config)

        # Check that overlap exists between consecutive chunks
        if len(result.chunks) >= 2:
            chunk1_end_words = result.chunks[0].content.split()[-10:]
            chunk2_start_words = result.chunks[1].content.split()[:20]
            # Some words from end of chunk1 should appear in chunk2
            overlap_found = any(word in chunk2_start_words for word in chunk1_end_words)
            assert overlap_found

    def test_continuation_flags(self):
        """Test that continuation flags are set correctly."""
        content = "word " * 1000
        config = ChunkingConfig(strategy="fixed", fixed_chunk_size=200)
        result = chunk_document(content, config)

        if len(result.chunks) > 1:
            assert not result.chunks[0].is_continuation
            assert result.chunks[1].is_continuation
            assert result.chunks[1].continuation_of == 0


class TestDelimiterChunking:
    """Test delimiter-based chunking."""

    def test_horizontal_rule_split(self):
        """Test splitting on horizontal rules."""
        content = """Part 1 content.

---

Part 2 content.

---

Part 3 content.
"""
        config = ChunkingConfig(strategy="delimiter", delimiter_pattern=r"^---+$", min_chunk_size=1)
        result = chunk_document(content, config)

        assert len(result.chunks) == 3
        assert "Part 1" in result.chunks[0].content
        assert "Part 2" in result.chunks[1].content
        assert "Part 3" in result.chunks[2].content

    def test_custom_delimiter(self):
        """Test splitting on a custom delimiter."""
        content = """Section A

===

Section B

===

Section C
"""
        config = ChunkingConfig(strategy="delimiter", delimiter_pattern=r"^===+$", min_chunk_size=1)
        result = chunk_document(content, config)

        assert len(result.chunks) == 3


class TestOversizedHandling:
    """Test handling of oversized chunks."""

    def test_oversized_chunk_gets_split(self):
        """Test that oversized chunks are sub-chunked."""
        # Create a doc with one huge section
        content = "# Title\n\n## Big Section\n\n" + ("Content. " * 500)
        config = ChunkingConfig(strategy="headers", max_chunk_size=200, min_chunk_size=1)
        result = chunk_document(content, config)

        # The big section should be sub-chunked
        assert len(result.chunks) > 2

    def test_oversized_preserves_breadcrumb(self):
        """Test that sub-chunks preserve parent breadcrumb."""
        content = "# Title\n\n## Big Section\n\n" + ("Content. " * 500)
        # Use min_chunk_size=1 to prevent undersized merging which would lose breadcrumbs
        config = ChunkingConfig(strategy="headers", max_chunk_size=200, min_chunk_size=1)
        result = chunk_document(content, config)

        # All chunks from the big section should have the breadcrumb
        big_section_chunks = [
            c for c in result.chunks if c.breadcrumb and "Big Section" in c.breadcrumb
        ]
        assert len(big_section_chunks) > 1
        for chunk in big_section_chunks:
            assert "Big Section" in chunk.breadcrumb


class TestUndersizedHandling:
    """Test handling of undersized chunks."""

    def test_undersized_chunks_get_merged(self):
        """Test that small chunks are merged."""
        content = """# Title

## A

Tiny.

## B

Also tiny.

## C

Tiny too.
"""
        config = ChunkingConfig(strategy="headers", min_chunk_size=100)
        result = chunk_document(content, config)

        # Some chunks should be merged (original would have 4)
        # After merging, should have fewer
        assert len(result.chunks) < 4

    def test_no_merge_if_combined_too_big(self):
        """Test that chunks aren't merged if combined size exceeds max."""
        # Create chunks that would be oversized if merged
        content = """# Title

## A

""" + ("A content. " * 100) + """

## B

""" + ("B content. " * 100)

        config = ChunkingConfig(
            strategy="headers", min_chunk_size=10, max_chunk_size=200
        )
        result = chunk_document(content, config)

        # Should keep them separate if merging would exceed max
        assert len(result.chunks) >= 2


class TestSentenceBoundary:
    """Test sentence boundary handling."""

    def test_splits_at_sentence(self):
        """Test that fixed-size chunks end at sentence boundaries."""
        content = "First sentence. Second sentence. Third sentence. Fourth sentence. Fifth sentence. Sixth sentence."
        config = ChunkingConfig(
            strategy="fixed", fixed_chunk_size=20, complete_sentences=True
        )
        result = chunk_document(content, config)

        # Most chunks should end with a period (except possibly the last)
        for chunk in result.chunks[:-1]:
            stripped = chunk.content.rstrip()
            assert stripped.endswith(".") or stripped.endswith("!") or stripped.endswith("?")


class TestChunkDocument:
    """Test main chunk_document entry point."""

    def test_auto_strategy(self):
        """Test that auto-detection works."""
        content = """# Title

## Section 1

Content here with enough text to pass size threshold.

## Section 2

More content with additional text for adequate size.

## Section 3

Even more content to ensure we have enough tokens.
""" + ("Padding text. " * 50)  # Ensure > 200 tokens
        result = chunk_document(content)  # Default is auto

        assert result.strategy == "headers"
        assert "markdown headers" in result.strategy_reason

    def test_single_strategy_for_small_doc(self):
        """Test that small docs use 'single' strategy and still get one chunk."""
        content = "Small document."
        result = chunk_document(content)

        assert result.strategy == "single"
        assert len(result.chunks) == 1
        assert result.chunks[0].content == content
        assert result.chunks[0].index == 0

    def test_result_metadata(self):
        """Test that result contains correct metadata."""
        content = "word " * 100
        result = chunk_document(content, source_path="/path/to/doc.md")

        assert result.document_path == "/path/to/doc.md"
        assert result.total_tokens == estimate_tokens(content)

    def test_summary_statistics(self):
        """Test summary() method."""
        content = """# Title

## Section 1

Content for section 1.

## Section 2

Content for section 2.
"""
        result = chunk_document(content, ChunkingConfig(strategy="headers"))
        summary = result.summary()

        assert "total_chunks" in summary
        assert "avg_tokens" in summary
        assert "min_tokens" in summary
        assert "max_tokens" in summary
        assert summary["total_chunks"] == len(result.chunks)

    def test_unknown_strategy_raises(self):
        """Test that unknown strategy raises ValueError."""
        with pytest.raises(ValueError, match="Unknown strategy"):
            chunk_document("content", ChunkingConfig(strategy="unknown"))


class TestWarnings:
    """Test warning generation."""

    def test_oversized_warning(self):
        """Test that oversized chunks get warnings."""
        # Create a situation where a chunk is oversized and can't be split further
        content = "A" * 5000  # Long content with no sentence boundaries
        config = ChunkingConfig(
            strategy="none",  # Force no chunking
            min_chunk_size=50,  # Must be less than max_chunk_size
            max_chunk_size=100,
        )
        result = chunk_document(content, config)

        assert any("oversized" in c.warnings for c in result.chunks)

    def test_undersized_warning(self):
        """Test that undersized chunks get warnings."""
        content = "Small."
        config = ChunkingConfig(
            strategy="none",  # Force single chunk
            min_chunk_size=100,  # Way bigger than content
        )
        result = chunk_document(content, config)

        assert any("undersized" in c.warnings for c in result.chunks)

    def test_result_warnings_collected(self):
        """Test that warnings are collected in result."""
        content = "Small."
        config = ChunkingConfig(strategy="none", min_chunk_size=100)
        result = chunk_document(content, config)

        assert len(result.warnings) > 0


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_content(self):
        """Test chunking empty content."""
        result = chunk_document("")
        assert len(result.chunks) == 1
        assert result.chunks[0].content == ""

    def test_only_headers(self):
        """Test document with only headers, no content."""
        content = """# Title

## Section 1

## Section 2

## Section 3
"""
        result = chunk_document(content, ChunkingConfig(strategy="headers"))

        # Should create chunks even if sections are empty
        assert len(result.chunks) >= 1

    def test_no_h2_in_split_levels(self):
        """Test splitting only on h3, not h2."""
        content = """# Title

## Overview

Content.

### Detail 1

Detail content.

### Detail 2

More detail.
"""
        config = ChunkingConfig(strategy="headers", header_split_levels=[3], min_chunk_size=1)
        result = chunk_document(content, config)

        # Should only split on h3
        # First chunk: everything before first h3
        # Second chunk: Detail 1
        # Third chunk: Detail 2
        assert len(result.chunks) == 3

    def test_unicode_content(self):
        """Test handling of unicode content."""
        content = """# Unicode Test

## Section

Content with unicode: 你好世界 🎉 émojis and 日本語
"""
        result = chunk_document(content, ChunkingConfig(strategy="headers"))

        assert len(result.chunks) >= 1
        assert "你好世界" in result.chunks[-1].content
