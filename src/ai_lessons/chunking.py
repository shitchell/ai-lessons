"""Document chunking for ai-lessons.

This module provides intelligent document chunking for better embedding and retrieval.
Strategies include:
- headers: Split on markdown headers (h2, h3, etc.)
- delimiter: Split on custom regex patterns
- fixed: Fixed-size chunks with overlap
- none: No chunking (small documents)
- auto: Auto-detect best strategy
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ChunkingConfig:
    """Configuration for document chunking."""

    # Strategy selection
    strategy: str = "auto"  # "auto", "headers", "delimiter", "fixed", "none"

    # Size constraints (in tokens, estimated as chars/4)
    min_chunk_size: int = 100
    max_chunk_size: int = 800

    # Header-based options
    header_split_levels: list[int] = field(default_factory=lambda: [2, 3])  # h2, h3
    include_parent_context: bool = True  # Prepend breadcrumb to chunk

    # Delimiter-based options
    delimiter_pattern: str | None = None  # Regex pattern
    include_delimiter: bool = False

    # Fixed-size options
    fixed_chunk_size: int = 500
    fixed_overlap: int = 50

    # Behavior
    complete_sentences: bool = True  # Don't cut mid-sentence

    def __post_init__(self):
        if self.min_chunk_size >= self.max_chunk_size:
            raise ValueError(
                f"min_chunk_size ({self.min_chunk_size}) must be less than "
                f"max_chunk_size ({self.max_chunk_size})"
            )


@dataclass
class Chunk:
    """A chunk of a document."""

    # Identity
    index: int  # Order within document (0-based)

    # Content
    content: str
    title: str | None  # Section title if from header split
    breadcrumb: str | None  # "Parent > Child > Grandchild"

    # Boundaries
    start_line: int
    end_line: int

    # Metrics
    token_count: int  # Estimated

    # Section hints (v5)
    sections: list[str] = field(default_factory=list)  # Headers within this chunk

    # Flags
    is_continuation: bool = False  # Part of an oversized section
    continuation_of: int | None = None  # Index of chunk this continues

    # Warnings
    warnings: list[str] = field(default_factory=list)  # "oversized", "undersized"

    def __post_init__(self):
        if self.token_count < 0:
            raise ValueError(f"token_count must be non-negative, got {self.token_count}")


@dataclass
class ChunkingResult:
    """Result of chunking a document."""

    # Input info
    document_path: str
    total_tokens: int

    # Strategy used
    strategy: str
    strategy_reason: str  # Why this strategy was chosen

    # Output
    chunks: list[Chunk]

    # Summary
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        """Return summary statistics."""
        if not self.chunks:
            return {
                "total_chunks": 0,
                "avg_tokens": 0,
                "min_tokens": 0,
                "max_tokens": 0,
                "oversized": 0,
                "undersized": 0,
            }
        return {
            "total_chunks": len(self.chunks),
            "avg_tokens": sum(c.token_count for c in self.chunks) // len(self.chunks),
            "min_tokens": min(c.token_count for c in self.chunks),
            "max_tokens": max(c.token_count for c in self.chunks),
            "oversized": sum(1 for c in self.chunks if "oversized" in c.warnings),
            "undersized": sum(1 for c in self.chunks if "undersized" in c.warnings),
        }


def estimate_tokens(text: str) -> int:
    """Estimate token count. Approximation: chars / 4."""
    return len(text) // 4


def extract_sections(content: str) -> list[str]:
    """Extract header texts from markdown content.

    Scans for markdown headers (# to ######) and returns their text,
    cleaned of formatting markers.

    Args:
        content: Markdown content to scan.

    Returns:
        List of header texts, cleaned of formatting.
    """
    # Match markdown headers (# to ######)
    header_pattern = r"^#{1,6}\s+(.+)$"
    matches = re.findall(header_pattern, content, re.MULTILINE)

    sections = []
    for header in matches:
        # Clean up: remove bold/italic markers, trailing anchors, etc.
        cleaned = header.strip()
        cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)  # **bold**
        cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)  # *italic*
        cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)  # `code`
        cleaned = re.sub(r'\s*<a\s+name="[^"]*">\s*</a>\s*', "", cleaned)  # anchors
        cleaned = re.sub(r"\s*\{#[^}]+\}\s*$", "", cleaned)  # {#anchor} suffix
        sections.append(cleaned.strip())

    return sections


def detect_strategy(content: str, config: ChunkingConfig) -> tuple[str, str]:
    """
    Detect the best chunking strategy for content.

    Returns:
        Tuple of (strategy, reason)
    """
    tokens = estimate_tokens(content)

    # Small documents: create single chunk with full content
    if tokens < config.min_chunk_size * 2:
        return "single", f"document small enough for single chunk ({tokens} tokens)"

    # Check for markdown headers
    header_pattern = r"^#{1,6}\s+.+$"
    headers = re.findall(header_pattern, content, re.MULTILINE)
    if len(headers) >= 3:  # Enough structure to chunk on
        return "headers", f"found {len(headers)} markdown headers"

    # Check for common delimiters
    delimiter_patterns = [
        (r"^---+$", "horizontal rules"),
        (r"^===+$", "alternative horizontal rules"),
        (r"^\*\*\*+$", "asterisk rules"),
    ]
    for pattern, name in delimiter_patterns:
        matches = len(re.findall(pattern, content, re.MULTILINE))
        if matches >= 3:
            return "delimiter", f"found {matches} {name}"

    # Fallback to fixed-size
    return "fixed", "no clear structure detected"


def chunk_by_headers(content: str, config: ChunkingConfig) -> list[Chunk]:
    """Split document on markdown headers."""
    lines = content.split("\n")
    chunks: list[Chunk] = []

    # Build header hierarchy for breadcrumbs
    header_stack: list[tuple[int, str]] = []  # [(level, title), ...]

    current_chunk_lines: list[str] = []
    current_chunk_start = 0
    current_title: str | None = None
    current_breadcrumb: str | None = None

    for i, line in enumerate(lines):
        header_match = re.match(r"^(#{1,6})\s+(.+)$", line)

        if header_match:
            level = len(header_match.group(1))
            title = header_match.group(2).strip()

            # Check if this header level triggers a split
            if level in config.header_split_levels:
                # Save current chunk if it has content
                if current_chunk_lines:
                    chunk_content = "\n".join(current_chunk_lines)
                    chunks.append(
                        Chunk(
                            index=len(chunks),
                            content=chunk_content,
                            title=current_title,
                            breadcrumb=current_breadcrumb,
                            start_line=current_chunk_start,
                            end_line=i - 1,
                            token_count=estimate_tokens(chunk_content),
                        )
                    )

                # Start new chunk
                current_chunk_lines = [line]
                current_chunk_start = i
                current_title = title

                # Update breadcrumb
                # Pop headers at same or lower level (higher number = lower in hierarchy)
                while header_stack and header_stack[-1][0] >= level:
                    header_stack.pop()
                header_stack.append((level, title))
                current_breadcrumb = " > ".join(h[1] for h in header_stack)
            else:
                # Header doesn't trigger split, include in current chunk
                current_chunk_lines.append(line)

                # Still update header stack for breadcrumb tracking
                while header_stack and header_stack[-1][0] >= level:
                    header_stack.pop()
                header_stack.append((level, title))
                # Update breadcrumb for current chunk (e.g., h1 before first h2)
                current_breadcrumb = " > ".join(h[1] for h in header_stack)
        else:
            current_chunk_lines.append(line)

    # Don't forget the last chunk
    if current_chunk_lines:
        chunk_content = "\n".join(current_chunk_lines)
        chunks.append(
            Chunk(
                index=len(chunks),
                content=chunk_content,
                title=current_title,
                breadcrumb=current_breadcrumb,
                start_line=current_chunk_start,
                end_line=len(lines) - 1,
                token_count=estimate_tokens(chunk_content),
            )
        )

    return chunks


def chunk_by_delimiter(content: str, config: ChunkingConfig) -> list[Chunk]:
    """Split document on a regex pattern."""
    if not config.delimiter_pattern:
        # Default to horizontal rules
        config.delimiter_pattern = r"^---+$"

    # Split content by delimiter
    pattern = re.compile(config.delimiter_pattern, re.MULTILINE)
    parts = pattern.split(content)

    chunks: list[Chunk] = []
    current_line = 0

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Count lines in this part
        part_lines = part.count("\n") + 1

        chunks.append(
            Chunk(
                index=len(chunks),
                content=part,
                title=None,
                breadcrumb=None,
                start_line=current_line,
                end_line=current_line + part_lines - 1,
                token_count=estimate_tokens(part),
            )
        )

        current_line += part_lines + 1  # +1 for the delimiter line

    return chunks


def chunk_fixed_size(content: str, config: ChunkingConfig) -> list[Chunk]:
    """Split document into fixed-size chunks with overlap."""
    lines = content.split("\n")
    chunks: list[Chunk] = []

    # Convert token sizes to approximate character counts
    chars_per_chunk = config.fixed_chunk_size * 4
    chars_overlap = config.fixed_overlap * 4

    current_chars = 0
    current_lines: list[str] = []
    current_start = 0
    overlap_lines: list[str] = []

    for i, line in enumerate(lines):
        line_chars = len(line) + 1  # +1 for newline

        if current_chars + line_chars > chars_per_chunk and current_lines:
            # Find sentence boundary if configured
            if config.complete_sentences:
                current_lines, remainder = _split_at_sentence(current_lines)
            else:
                remainder = []

            # Create chunk
            chunk_content = "\n".join(overlap_lines + current_lines)
            is_continuation = len(chunks) > 0
            chunks.append(
                Chunk(
                    index=len(chunks),
                    content=chunk_content,
                    title=None,
                    breadcrumb=None,
                    start_line=current_start,
                    end_line=i - 1,
                    token_count=estimate_tokens(chunk_content),
                    is_continuation=is_continuation,
                    continuation_of=len(chunks) - 1 if is_continuation else None,
                )
            )

            # Calculate overlap for next chunk
            overlap_chars = 0
            overlap_lines = []
            for overlap_line in reversed(current_lines):
                if overlap_chars + len(overlap_line) > chars_overlap:
                    break
                overlap_lines.insert(0, overlap_line)
                overlap_chars += len(overlap_line)

            # Start new chunk
            current_lines = remainder + [line]
            current_chars = sum(len(line) for line in current_lines)
            current_start = i - len(remainder)
        else:
            current_lines.append(line)
            current_chars += line_chars

    # Last chunk
    if current_lines:
        chunk_content = "\n".join(overlap_lines + current_lines)
        is_continuation = len(chunks) > 0
        chunks.append(
            Chunk(
                index=len(chunks),
                content=chunk_content,
                title=None,
                breadcrumb=None,
                start_line=current_start,
                end_line=len(lines) - 1,
                token_count=estimate_tokens(chunk_content),
                is_continuation=is_continuation,
                continuation_of=len(chunks) - 1 if is_continuation else None,
            )
        )

    return chunks


def _split_at_sentence(lines: list[str]) -> tuple[list[str], list[str]]:
    """Split lines at the last sentence boundary."""
    text = "\n".join(lines)

    # Find last sentence boundary
    sentence_enders = list(re.finditer(r"[.!?]\s", text))

    if not sentence_enders:
        return lines, []

    last_boundary = sentence_enders[-1].end()

    # Convert back to lines
    before = text[:last_boundary]
    after = text[last_boundary:]

    return before.split("\n"), after.split("\n") if after.strip() else []


def _whole_document_chunk(content: str) -> Chunk:
    """Create a single chunk for the entire document."""
    lines = content.split("\n")
    return Chunk(
        index=0,
        content=content,
        title=None,
        breadcrumb=None,
        start_line=0,
        end_line=len(lines) - 1,
        token_count=estimate_tokens(content),
    )


MAX_CHUNKING_DEPTH = 3  # Maximum recursion depth for oversized chunk handling


def _handle_oversized(
    chunks: list[Chunk], config: ChunkingConfig, depth: int = 0
) -> list[Chunk]:
    """Sub-chunk any chunks that exceed max_chunk_size.

    Args:
        chunks: List of chunks to process.
        config: Chunking configuration.
        depth: Current recursion depth (internal use).

    Returns:
        List of chunks with oversized chunks split.
    """
    result: list[Chunk] = []

    for chunk in chunks:
        if chunk.token_count <= config.max_chunk_size:
            result.append(chunk)
        elif depth >= MAX_CHUNKING_DEPTH:
            # Max depth reached - add warning and keep as-is
            chunk.warnings.append("max_depth_exceeded")
            logger.warning(
                f"Max chunking depth ({MAX_CHUNKING_DEPTH}) exceeded for chunk "
                f"with {chunk.token_count} tokens"
            )
            result.append(chunk)
        else:
            # Recursively chunk with fixed-size strategy
            sub_config = ChunkingConfig(
                strategy="fixed",
                fixed_chunk_size=config.max_chunk_size - 50,  # Leave room
                fixed_overlap=config.fixed_overlap,
                complete_sentences=config.complete_sentences,
                min_chunk_size=config.min_chunk_size,
                max_chunk_size=config.max_chunk_size,
            )
            sub_chunks = chunk_fixed_size(chunk.content, sub_config)

            # If line-based splitting didn't help (single long line), use character-based
            if len(sub_chunks) == 1 and sub_chunks[0].token_count > config.max_chunk_size:
                sub_chunks = _chunk_by_characters(chunk.content, sub_config)

            # Recursively handle any still-oversized chunks
            sub_chunks = _handle_oversized(sub_chunks, config, depth + 1)

            # Check if still oversized after all fallbacks
            for i, sub in enumerate(sub_chunks):
                if sub.token_count > config.max_chunk_size and "max_depth_exceeded" not in sub.warnings:
                    sub.warnings.append("failed_to_split")
                    logger.warning(
                        f"Chunk {len(result) + i} still oversized after splitting: "
                        f"{sub.token_count} tokens (max: {config.max_chunk_size})"
                    )

            # Preserve parent breadcrumb and adjust metadata
            for i, sub in enumerate(sub_chunks):
                sub.breadcrumb = chunk.breadcrumb
                sub.title = f"{chunk.title} (part {i + 1})" if chunk.title else None
                sub.is_continuation = i > 0
                sub.continuation_of = len(result) - 1 if i > 0 else chunk.continuation_of
                # Adjust line numbers relative to parent
                sub.start_line = chunk.start_line + sub.start_line
                sub.end_line = chunk.start_line + sub.end_line
                result.append(sub)

    # Re-index
    for i, chunk in enumerate(result):
        chunk.index = i

    return result


def _chunk_by_characters(content: str, config: ChunkingConfig) -> list[Chunk]:
    """
    Split content by characters when line-based splitting fails.

    Used as a fallback for single very long lines.
    """
    chunks: list[Chunk] = []
    chars_per_chunk = config.fixed_chunk_size * 4
    chars_overlap = config.fixed_overlap * 4

    start = 0
    while start < len(content):
        end = min(start + chars_per_chunk, len(content))

        # Try to find a sentence boundary if configured
        if config.complete_sentences and end < len(content):
            # Look for sentence enders near the end
            search_start = max(start, end - 200)
            sentence_end = -1
            for pattern in [". ", "! ", "? ", ".\n", "!\n", "?\n"]:
                idx = content.rfind(pattern, search_start, end)
                if idx > sentence_end:
                    sentence_end = idx

            if sentence_end > start:
                end = sentence_end + 1

        chunk_content = content[start:end].strip()
        if chunk_content:
            chunks.append(
                Chunk(
                    index=len(chunks),
                    content=chunk_content,
                    title=None,
                    breadcrumb=None,
                    start_line=0,  # Character-based, line numbers not meaningful
                    end_line=0,
                    token_count=estimate_tokens(chunk_content),
                    is_continuation=len(chunks) > 0,
                    continuation_of=len(chunks) - 1 if len(chunks) > 0 else None,
                )
            )

        # Move forward, accounting for overlap
        start = end - chars_overlap if end < len(content) else end

    return chunks if chunks else [Chunk(
        index=0,
        content=content,
        title=None,
        breadcrumb=None,
        start_line=0,
        end_line=0,
        token_count=estimate_tokens(content),
    )]


def _handle_undersized(chunks: list[Chunk], config: ChunkingConfig) -> list[Chunk]:
    """Merge undersized chunks with adjacent chunks."""
    if len(chunks) <= 1:
        return chunks

    result: list[Chunk] = []
    i = 0

    while i < len(chunks):
        chunk = chunks[i]

        # If undersized and there's a next chunk, consider merging
        if chunk.token_count < config.min_chunk_size and i + 1 < len(chunks):
            next_chunk = chunks[i + 1]
            combined_size = chunk.token_count + next_chunk.token_count

            # Only merge if combined size is reasonable
            if combined_size <= config.max_chunk_size:
                merged = Chunk(
                    index=len(result),
                    content=chunk.content + "\n\n" + next_chunk.content,
                    title=chunk.title or next_chunk.title,
                    breadcrumb=chunk.breadcrumb or next_chunk.breadcrumb,
                    start_line=chunk.start_line,
                    end_line=next_chunk.end_line,
                    token_count=combined_size,
                )
                result.append(merged)
                i += 2
                continue

        chunk.index = len(result)
        result.append(chunk)
        i += 1

    return result


def _collect_warnings(chunks: list[Chunk]) -> list[str]:
    """Collect and deduplicate warnings from all chunks."""
    warnings: list[str] = []
    oversized = sum(1 for c in chunks if "oversized" in c.warnings)
    undersized = sum(1 for c in chunks if "undersized" in c.warnings)

    if oversized:
        warnings.append(f"{oversized} chunk(s) exceed max size")
    if undersized:
        warnings.append(f"{undersized} chunk(s) below min size")

    return warnings


def chunk_document(
    content: str,
    config: ChunkingConfig | None = None,
    source_path: str | None = None,
) -> ChunkingResult:
    """
    Chunk a document according to configuration.

    Args:
        content: Document content (string)
        config: Chunking configuration (defaults applied if None)
        source_path: Original file path (for reporting)

    Returns:
        ChunkingResult with chunks and metadata
    """
    if config is None:
        config = ChunkingConfig()

    # Auto-detect strategy if needed
    strategy = config.strategy
    strategy_reason = "user specified"

    if strategy == "auto":
        strategy, strategy_reason = detect_strategy(content, config)

    # Dispatch to strategy implementation
    if strategy == "none":
        chunks = [_whole_document_chunk(content)]
    elif strategy == "single":
        # Single chunk for small documents - same as "none" but semantically different
        chunks = [_whole_document_chunk(content)]
    elif strategy == "headers":
        chunks = chunk_by_headers(content, config)
    elif strategy == "delimiter":
        chunks = chunk_by_delimiter(content, config)
    elif strategy == "fixed":
        chunks = chunk_fixed_size(content, config)
    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    # Post-process: handle oversized chunks (skip for 'none' and 'single')
    if strategy not in ("none", "single"):
        chunks = _handle_oversized(chunks, config)

    # Post-process: merge undersized chunks (skip for 'none' and 'single')
    if strategy not in ("none", "single"):
        chunks = _handle_undersized(chunks, config)

    # Add warnings
    for chunk in chunks:
        if chunk.token_count > config.max_chunk_size:
            chunk.warnings.append("oversized")
        if chunk.token_count < config.min_chunk_size:
            chunk.warnings.append("undersized")

    # Extract sections (headers within each chunk) for section hints
    for chunk in chunks:
        chunk.sections = extract_sections(chunk.content)

    return ChunkingResult(
        document_path=source_path or "<string>",
        total_tokens=estimate_tokens(content),
        strategy=strategy,
        strategy_reason=strategy_reason,
        chunks=chunks,
        warnings=_collect_warnings(chunks),
    )
