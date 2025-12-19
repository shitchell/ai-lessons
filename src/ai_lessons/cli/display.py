"""CLI display and formatting functions."""

from __future__ import annotations

import click

from .. import core
from ..search import SearchResult, ChunkResult, GroupedResourceResult


# ID display length (set high to show full IDs for copy-paste usability)
ID_DISPLAY_LENGTH = 100


def format_lesson(lesson: core.Lesson, verbose: bool = False) -> str:
    """Format a lesson for display."""
    lines = []
    lines.append(f"[{lesson.id[:ID_DISPLAY_LENGTH]}] {lesson.title}")

    if lesson.confidence or lesson.source:
        meta = []
        if lesson.confidence:
            meta.append(f"confidence: {lesson.confidence}")
        if lesson.source:
            meta.append(f"source: {lesson.source}")
        lines.append(f"  {' | '.join(meta)}")

    if lesson.tags:
        lines.append(f"  tags: {', '.join(lesson.tags)}")

    if lesson.contexts:
        lines.append(f"  contexts: {', '.join(lesson.contexts)}")

    if lesson.anti_contexts:
        lines.append(f"  anti-contexts: {', '.join(lesson.anti_contexts)}")

    if verbose:
        if lesson.source_notes:
            lines.append(f"  notes: {lesson.source_notes}")
        lines.append("")
        lines.append(lesson.content)

    return "\n".join(lines)


def format_search_result(result: SearchResult, verbose: bool = False) -> str:
    """Format a search result for display."""
    lines = []

    # Format based on result type
    if result.result_type == "chunk":
        # Chunk result - show breadcrumb/hierarchy
        if result.resource_title and result.title:
            display_title = f"{result.resource_title} > {result.title}"
        elif result.breadcrumb:
            display_title = result.breadcrumb
        elif result.title:
            display_title = result.title
        else:
            display_title = f"Chunk #{result.chunk_index}"

        lines.append(f"[chunk] [{result.id[:ID_DISPLAY_LENGTH]}] (score: {result.score:.3f}) {display_title}")

        meta = []
        if result.versions:
            meta.append(f"versions: {', '.join(result.versions)}")
        if result.resource_id:
            meta.append(f"parent: {result.resource_id[:ID_DISPLAY_LENGTH]}")
        if meta:
            lines.append(f"  {' | '.join(meta)}")

        # Show sections (headers within chunk)
        if result.sections:
            sections_str = ", ".join(result.sections[:4])
            if len(result.sections) > 4:
                sections_str += f" (+{len(result.sections) - 4} more)"
            lines.append(f"  sections: {sections_str}")

        # Show summary or content preview for chunks (always, not just verbose)
        if result.summary:
            lines.append(f"  > {result.summary}")
        elif not verbose:  # Show truncated content if no summary (unless verbose shows full)
            preview = result.content[:100].replace('\n', ' ')
            if len(result.content) > 100:
                preview += "..."
            lines.append(f"  > {preview}")

    elif result.result_type == "resource":
        type_indicator = f"[{result.resource_type}]" if result.resource_type else "[resource]"
        lines.append(f"{type_indicator} [{result.id[:ID_DISPLAY_LENGTH]}] (score: {result.score:.3f}) {result.title}")

        meta = []
        if result.versions:
            meta.append(f"versions: {', '.join(result.versions)}")
        if result.path:
            meta.append(f"path: {result.path}")
        if meta:
            lines.append(f"  {' | '.join(meta)}")

    elif result.result_type == "rule":
        lines.append(f"[rule] [{result.id[:ID_DISPLAY_LENGTH]}] (score: {result.score:.3f}) {result.title}")
        if result.rationale:
            lines.append(f"  rationale: \"{result.rationale[:100]}{'...' if len(result.rationale) > 100 else ''}\"")

    else:
        # Lesson (default)
        lines.append(f"[{result.id[:ID_DISPLAY_LENGTH]}] (score: {result.score:.3f}) {result.title}")

        if result.confidence or result.source:
            meta = []
            if result.confidence:
                meta.append(f"confidence: {result.confidence}")
            if result.source:
                meta.append(f"source: {result.source}")
            lines.append(f"  {' | '.join(meta)}")

    if result.tags:
        lines.append(f"  tags: {', '.join(result.tags)}")

    if verbose:
        # Show first 200 chars of content
        preview = result.content[:200]
        if len(result.content) > 200:
            preview += "..."
        lines.append(f"  {preview}")

    return "\n".join(lines)


def format_resource(resource: core.Resource, verbose: bool = False) -> str:
    """Format a resource for display."""
    lines = []
    type_indicator = f"[{resource.type}]" if resource.type else "[resource]"
    lines.append(f"{type_indicator} [{resource.id[:ID_DISPLAY_LENGTH]}] {resource.title}")

    meta = []
    if resource.versions:
        meta.append(f"versions: {', '.join(resource.versions)}")
    if resource.path:
        meta.append(f"path: {resource.path}")
    if meta:
        lines.append(f"  {' | '.join(meta)}")

    if resource.tags:
        lines.append(f"  tags: {', '.join(resource.tags)}")

    if resource.source_ref:
        lines.append(f"  git ref: {resource.source_ref}")

    if verbose and resource.content:
        lines.append("")
        lines.append(resource.content)

    return "\n".join(lines)


def format_rule(rule: core.Rule, verbose: bool = False) -> str:
    """Format a rule for display."""
    lines = []
    status = "✓" if rule.approved else "○"
    lines.append(f"[{status}] [{rule.id[:ID_DISPLAY_LENGTH]}] {rule.title}")

    if rule.tags:
        lines.append(f"  applies to: {', '.join(rule.tags)}")

    lines.append(f"  rationale: \"{rule.rationale}\"")

    if rule.suggested_by:
        lines.append(f"  suggested by: {rule.suggested_by}")

    if rule.approved and rule.approved_by:
        lines.append(f"  approved by: {rule.approved_by}")

    if verbose:
        lines.append("")
        lines.append(rule.content)

    return "\n".join(lines)


def format_chunk(chunk: core.ResourceChunk, verbose: bool = False) -> str:
    """Format a resource chunk for display."""
    lines = []

    # Build title with breadcrumb context
    if chunk.resource_title and chunk.title:
        title = f"{chunk.resource_title} > {chunk.title}"
    elif chunk.breadcrumb:
        title = chunk.breadcrumb
    elif chunk.title:
        title = chunk.title
    else:
        title = f"Chunk #{chunk.chunk_index}"

    lines.append(f"[chunk] [{chunk.id[:ID_DISPLAY_LENGTH]}] {title}")

    # Metadata line
    meta = []
    if chunk.resource_id:
        meta.append(f"parent: {chunk.resource_id[:ID_DISPLAY_LENGTH]}")
    if chunk.resource_versions:
        meta.append(f"versions: {', '.join(chunk.resource_versions)}")
    if chunk.start_line is not None and chunk.end_line is not None:
        meta.append(f"lines: {chunk.start_line + 1}-{chunk.end_line + 1}")
    if chunk.token_count:
        meta.append(f"tokens: {chunk.token_count}")
    if meta:
        lines.append(f"  {' | '.join(meta)}")

    if chunk.resource_tags:
        lines.append(f"  tags: {', '.join(chunk.resource_tags)}")

    # Show summary if available
    if chunk.summary:
        lines.append(f"  summary: {chunk.summary}")

    if verbose:
        lines.append("")
        lines.append(chunk.content)

    return "\n".join(lines)


def format_grouped_search_results(
    top_matches: list[ChunkResult],
    grouped: list[GroupedResourceResult],
    show_top_n: int = 3,
) -> str:
    """Format grouped search results for display.

    Args:
        top_matches: Top N chunks across all resources.
        grouped: Resources with their matching chunks.
        show_top_n: Number of top matches to show in summary.

    Output format:
    ```
    Top matches: README.md.58 (0.87), AnnouncementBannerApi.md.1 (0.75)

    README.md (v3) [jira, api]
      .58 (0.87) Authorization > OAuth2
      .62 (0.81) basicAuth

    AnnouncementBannerApi.md (v3) [jira, api]
      .1  (0.75) getBanner
      .3  (0.68) setBanner
    ```
    """
    lines = []

    # Top matches summary
    if top_matches:
        top_summaries = []
        for chunk in top_matches[:show_top_n]:
            # Show chunk index and score
            top_summaries.append(f".{chunk.chunk_index} ({chunk.score:.2f})")
        lines.append(f"Top matches: {', '.join(top_summaries)}")
        lines.append("")

    # Grouped resources
    for group in grouped:
        # Resource header: title (versions) [tags]
        header_parts = [group.resource_title]
        if group.versions:
            header_parts.append(f"({', '.join(group.versions)})")
        if group.tags:
            header_parts.append(f"[{', '.join(group.tags[:3])}]")
        lines.append(" ".join(header_parts))

        # Chunks under this resource
        if group.chunks:
            for chunk in group.chunks:
                # Format: .N (score) title
                title = chunk.title or chunk.breadcrumb or f"chunk {chunk.chunk_index}"
                lines.append(f"  .{chunk.chunk_index:<3} ({chunk.score:.2f}) {title}")
        else:
            # Resource matched but no specific chunk matches
            lines.append(f"  (best score: {group.best_score:.2f})")

        lines.append("")

    return "\n".join(lines).rstrip()


def display_chunking_preview(result) -> None:
    """Display chunking preview in a nice format."""
    click.echo(f"Document: {result.document_path}")
    click.echo(f"Total tokens: {result.total_tokens:,}")
    click.echo(f"Strategy: {result.strategy} ({result.strategy_reason})")
    click.echo()

    # Table header
    click.echo("Chunks:")
    click.echo()
    click.echo("  #    Tokens  Title/Location")
    click.echo("  " + "-" * 60)

    for chunk in result.chunks:
        # Determine title to display
        if chunk.breadcrumb:
            title = chunk.breadcrumb
        elif chunk.title:
            title = chunk.title
        else:
            title = f"(lines {chunk.start_line + 1}-{chunk.end_line + 1})"

        # Truncate if too long
        if len(title) > 42:
            title = title[:39] + "..."

        # Add warning indicator
        warning = ""
        if "oversized" in chunk.warnings:
            warning = " [oversized]"
        elif "undersized" in chunk.warnings:
            warning = " [small]"

        click.echo(f"  {chunk.index:3d}  {chunk.token_count:6d}  {title}{warning}")

    # Summary
    summary = result.summary()
    click.echo()
    click.echo("Summary:")
    click.echo(f"  Total chunks: {summary['total_chunks']}")
    click.echo(f"  Avg size: {summary['avg_tokens']} tokens")
    click.echo(f"  Range: {summary['min_tokens']} - {summary['max_tokens']} tokens")

    if summary['oversized']:
        click.echo(f"  Warning: {summary['oversized']} chunk(s) exceed max size")
    if summary['undersized']:
        click.echo(f"  Warning: {summary['undersized']} chunk(s) below min size")
