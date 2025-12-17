"""Command-line interface for ai-lessons."""

import subprocess
import sys
from pathlib import Path
from typing import Optional

import click

from . import core
from .config import Config, get_config, DEFAULT_LESSONS_DIR
from .db import init_db
from .search import SearchResult, search_resources, unified_search


def _parse_tags(tags: Optional[str]) -> Optional[list[str]]:
    """Parse comma-separated tags string."""
    if not tags:
        return None
    return [t.strip() for t in tags.split(",") if t.strip()]


def _show_feedback_reminder():
    """Show a reminder to submit feedback after search commands."""
    config = get_config()
    if config.suggest_feedback:
        click.echo()
        click.secho(
            "Tip: Help improve ai-lessons! When done searching, run:",
            dim=True,
        )
        click.secho(
            '  ai-lessons contribute feedback -t "your goal" -q "queries;used" -n <# of searches>',
            dim=True,
        )


def _format_lesson(lesson: core.Lesson, verbose: bool = False) -> str:
    """Format a lesson for display."""
    lines = []
    lines.append(f"[{lesson.id}] {lesson.title}")

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


def _format_search_result(result: SearchResult, verbose: bool = False) -> str:
    """Format a search result for display."""
    lines = []

    # Format based on result type
    if result.result_type == "chunk":
        # Chunk result - show breadcrumb/hierarchy
        if result.resource_title and result.title:
            display_title = f"{result.resource_title} > {result.title}"
        elif result.chunk_breadcrumb:
            display_title = result.chunk_breadcrumb
        elif result.title:
            display_title = result.title
        else:
            display_title = f"Chunk #{result.chunk_index}"

        lines.append(f"[chunk] [{result.id}] (score: {result.score:.3f}) {display_title}")

        meta = []
        if result.versions:
            meta.append(f"versions: {', '.join(result.versions)}")
        if result.resource_id:
            meta.append(f"parent: {result.resource_id[:12]}...")
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
        lines.append(f"{type_indicator} [{result.id}] (score: {result.score:.3f}) {result.title}")

        meta = []
        if result.versions:
            meta.append(f"versions: {', '.join(result.versions)}")
        if result.path:
            meta.append(f"path: {result.path}")
        if meta:
            lines.append(f"  {' | '.join(meta)}")

    elif result.result_type == "rule":
        lines.append(f"[rule] [{result.id}] (score: {result.score:.3f}) {result.title}")
        if result.rationale:
            lines.append(f"  rationale: \"{result.rationale[:100]}{'...' if len(result.rationale) > 100 else ''}\"")

    else:
        # Lesson (default)
        lines.append(f"[{result.id}] (score: {result.score:.3f}) {result.title}")

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


def _format_resource(resource: core.Resource, verbose: bool = False) -> str:
    """Format a resource for display."""
    lines = []
    type_indicator = f"[{resource.type}]" if resource.type else "[resource]"
    lines.append(f"{type_indicator} [{resource.id}] {resource.title}")

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


def _format_rule(rule: core.Rule, verbose: bool = False) -> str:
    """Format a rule for display."""
    lines = []
    status = "✓" if rule.approved else "○"
    lines.append(f"[{status}] [{rule.id}] {rule.title}")

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


def _format_chunk(chunk: core.ResourceChunk, verbose: bool = False) -> str:
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

    lines.append(f"[chunk] [{chunk.id}] {title}")

    # Metadata line
    meta = []
    if chunk.resource_id:
        meta.append(f"parent: {chunk.resource_id[:12]}...")
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


def _display_chunking_preview(result) -> None:
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


# =============================================================================
# Main CLI group
# =============================================================================

@click.group()
@click.version_option()
def main():
    """AI Lessons - Knowledge management with semantic search.

    Commands are organized into three groups:

    \b
      admin       Database and system management
      contribute  Add and modify lessons, resources, and rules
      recall      Search and view lessons
    """
    pass


# =============================================================================
# ADMIN group - Database and system management
# =============================================================================

@main.group()
def admin():
    """Database and system management commands."""
    pass


@admin.command()
@click.option("--force", is_flag=True, help="Reinitialize even if database exists")
def init(force: bool):
    """Initialize the database and configuration."""
    config = get_config()

    # Create config directory
    DEFAULT_LESSONS_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize database
    init_db(config, force=force)

    # Save default config if it doesn't exist
    config_path = DEFAULT_LESSONS_DIR / "config.yaml"
    if not config_path.exists():
        config.save(config_path)

    click.echo(f"Initialized ai-lessons at {DEFAULT_LESSONS_DIR}")
    click.echo(f"  Database: {config.db_path}")
    click.echo(f"  Config: {config_path}")


@admin.command()
def stats():
    """Show database statistics."""
    config = get_config()
    core.ensure_initialized(config)

    from .db import get_db

    with get_db(config) as conn:
        # Count lessons
        cursor = conn.execute("SELECT COUNT(*) FROM lessons")
        lesson_count = cursor.fetchone()[0]

        # Count lesson tags
        cursor = conn.execute("SELECT COUNT(DISTINCT tag) FROM lesson_tags")
        lesson_tag_count = cursor.fetchone()[0]

        # Count edges
        cursor = conn.execute("SELECT COUNT(*) FROM edges")
        edge_count = cursor.fetchone()[0]

        # Count resources
        cursor = conn.execute("SELECT COUNT(*) FROM resources")
        resource_count = cursor.fetchone()[0]

        # Count resources by type
        cursor = conn.execute(
            "SELECT type, COUNT(*) FROM resources GROUP BY type"
        )
        resource_type_counts = dict(cursor.fetchall())

        # Count rules
        cursor = conn.execute("SELECT COUNT(*) FROM rules WHERE approved = 1")
        approved_rules_count = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM rules WHERE approved = 0")
        pending_rules_count = cursor.fetchone()[0]

        # Count by confidence
        cursor = conn.execute(
            "SELECT confidence, COUNT(*) FROM lessons GROUP BY confidence"
        )
        confidence_counts = dict(cursor.fetchall())

        # Count by source
        cursor = conn.execute(
            "SELECT source, COUNT(*) FROM lessons GROUP BY source"
        )
        source_counts = dict(cursor.fetchall())

    click.echo(f"Database: {config.db_path}")
    click.echo(f"\nLessons: {lesson_count}")
    click.echo(f"  Tags: {lesson_tag_count}")
    click.echo(f"  Edges: {edge_count}")

    click.echo(f"\nResources: {resource_count}")
    if resource_type_counts:
        for rtype, count in resource_type_counts.items():
            click.echo(f"  {rtype}: {count}")

    click.echo(f"\nRules:")
    click.echo(f"  Approved: {approved_rules_count}")
    click.echo(f"  Pending: {pending_rules_count}")

    if confidence_counts:
        click.echo("\nLessons by confidence:")
        for conf, count in confidence_counts.items():
            click.echo(f"  {conf or 'unset'}: {count}")

    if source_counts:
        click.echo("\nLessons by source:")
        for src, count in source_counts.items():
            click.echo(f"  {src or 'unset'}: {count}")


@admin.command("merge-tags")
@click.argument("from_tag")
@click.argument("to_tag")
def merge_tags(from_tag: str, to_tag: str):
    """Merge one tag into another."""
    count = core.merge_tags(from_tag, to_tag)
    click.echo(f"Merged '{from_tag}' into '{to_tag}' ({count} lessons affected)")


@admin.command("add-source")
@click.argument("name")
@click.option("--description", "-d", help="Source description")
@click.option("--typical-confidence", help="Typical confidence for this source")
def add_source(name: str, description: Optional[str], typical_confidence: Optional[str]):
    """Add a new source type."""
    success = core.add_source(name, description, typical_confidence)

    if success:
        click.echo(f"Added source type: {name}")
    else:
        click.echo(f"Source type already exists: {name}", err=True)
        sys.exit(1)


# --- Rule admin commands ---


@admin.command("pending-rules")
@click.option("--count", is_flag=True, help="Only show count")
def pending_rules(count: bool):
    """List rules pending approval."""
    rules = core.list_pending_rules()

    if count:
        click.echo(len(rules))
        return

    if not rules:
        click.echo("No pending rules.")
        return

    click.echo(f"Pending rules ({len(rules)}):\n")
    for rule in rules:
        click.echo(_format_rule(rule))
        click.echo()


@admin.command("approve-rule")
@click.argument("rule_id")
@click.option("--by", "approved_by", help="Who is approving this rule")
def approve_rule(rule_id: str, approved_by: Optional[str]):
    """Approve a pending rule."""
    success = core.approve_rule(rule_id, approved_by)

    if success:
        click.echo(f"Approved rule: {rule_id}")
    else:
        click.echo(f"Rule not found: {rule_id}", err=True)
        sys.exit(1)


@admin.command("reject-rule")
@click.argument("rule_id")
@click.confirmation_option(prompt="Are you sure you want to reject (delete) this rule?")
def reject_rule(rule_id: str):
    """Reject (delete) a suggested rule."""
    success = core.reject_rule(rule_id)

    if success:
        click.echo(f"Rejected rule: {rule_id}")
    else:
        click.echo(f"Rule not found: {rule_id}", err=True)
        sys.exit(1)


@admin.command("reindex-resources")
def reindex_resources():
    """Reindex all resources (re-generate embeddings)."""
    from .db import get_db

    config = get_config()
    core.ensure_initialized(config)

    with get_db(config) as conn:
        cursor = conn.execute("SELECT id FROM resources")
        resource_ids = [row["id"] for row in cursor.fetchall()]

    if not resource_ids:
        click.echo("No resources to reindex.")
        return

    count = 0
    with click.progressbar(resource_ids, label="Reindexing resources") as bar:
        for resource_id in bar:
            if core.refresh_resource(resource_id):
                count += 1

    click.echo(f"Reindexed {count} resources.")


@admin.command("generate-summaries")
@click.option("--resource-id", "-r", help="Generate summaries for a specific resource by ID")
@click.option("--pattern", "-p", help="Filter resources by title (case-insensitive substring)")
@click.option("--type", "-t", "resource_type", type=click.Choice(["doc", "script"]),
              help="Filter by resource type")
@click.option("--version", "-v", "version", help="Filter by version")
@click.option("--tags", help="Filter by tags (comma-separated, matches any)")
@click.option("--force", is_flag=True, help="Regenerate even if summary already exists")
@click.option("--dry-run", is_flag=True, help="Show what would be generated without making changes")
def generate_summaries(
    resource_id: Optional[str],
    pattern: Optional[str],
    resource_type: Optional[str],
    version: Optional[str],
    tags: Optional[str],
    force: bool,
    dry_run: bool,
):
    """Generate LLM summaries for resource chunks.

    Requires 'summaries' configuration in config.yaml with backend and model settings.

    Examples:

    \b
      # Generate for all chunks without summaries
      ai-lessons admin generate-summaries

    \b
      # Generate for a specific resource
      ai-lessons admin generate-summaries -r 01KCK3PZ6K...

    \b
      # Generate for all v3 Jira API docs
      ai-lessons admin generate-summaries --version v3 --tags api,jira

    \b
      # Preview what would be generated
      ai-lessons admin generate-summaries --pattern "Vote" --dry-run
    """
    from .summaries import generate_chunk_summaries

    config = get_config()
    core.ensure_initialized(config)

    if not config.summaries.enabled:
        click.echo("Error: Summary generation not configured.", err=True)
        click.echo("Add to config.yaml:", err=True)
        click.echo("  summaries:", err=True)
        click.echo("    backend: anthropic  # or: openai", err=True)
        click.echo("    model: claude-3-haiku-20240307  # or: gpt-4o-mini", err=True)
        sys.exit(1)

    # Get chunks to process with filtering
    from .db import get_db
    tag_list = _parse_tags(tags)

    with get_db(config) as conn:
        if resource_id:
            # Simple case: specific resource by ID
            query = "SELECT id, title, content, summary FROM resource_chunks WHERE resource_id = ? ORDER BY chunk_index"
            cursor = conn.execute(query, (resource_id,))
        else:
            # Build query with filters (join with resources table)
            query = """
                SELECT c.id, c.title, c.content, c.summary
                FROM resource_chunks c
                JOIN resources r ON c.resource_id = r.id
            """
            joins = []
            conditions = []
            params = []

            if version:
                joins.append("JOIN resource_versions rv ON r.id = rv.resource_id")
                conditions.append("rv.version = ?")
                params.append(version)

            if tag_list:
                joins.append("JOIN resource_tags rt ON r.id = rt.resource_id")
                placeholders = ",".join("?" * len(tag_list))
                conditions.append(f"rt.tag IN ({placeholders})")
                params.extend(tag_list)

            if pattern:
                conditions.append("r.title LIKE ?")
                params.append(f"%{pattern}%")

            if resource_type:
                conditions.append("r.type = ?")
                params.append(resource_type)

            if joins:
                query += " " + " ".join(joins)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY c.resource_id, c.chunk_index"

            cursor = conn.execute(query, params)

        chunks = cursor.fetchall()

    if not chunks:
        click.echo("No chunks found.")
        return

    # Filter to chunks needing summaries
    if not force:
        chunks = [c for c in chunks if not c["summary"]]

    if not chunks:
        click.echo("All chunks already have summaries. Use --force to regenerate.")
        return

    click.echo(f"Found {len(chunks)} chunk(s) to process.")
    click.echo(f"Using: {config.summaries.backend} / {config.summaries.model}")
    click.echo()

    if dry_run:
        click.echo("Dry run - would generate summaries for:")
        for chunk in chunks[:10]:  # Show first 10
            title = chunk["title"] or f"(chunk)"
            click.echo(f"  {chunk['id'][:12]}... {title}")
        if len(chunks) > 10:
            click.echo(f"  ... and {len(chunks) - 10} more")
        return

    # Generate summaries with progress bar
    count = 0
    errors = 0
    with click.progressbar(chunks, label="Generating summaries") as bar:
        for chunk in bar:
            try:
                result = generate_chunk_summaries(
                    chunk_ids=[chunk["id"]],
                    force=force,
                    config=config,
                )
                if chunk["id"] in result:
                    count += 1
            except Exception as e:
                errors += 1
                # Log error but continue
                if errors == 1:
                    click.echo(f"\nWarning: {e}", err=True)

    click.echo(f"\nGenerated {count} summaries.")
    if errors:
        click.echo(f"Encountered {errors} error(s).", err=True)


@admin.command("update-paths")
@click.option("--from", "from_path", required=True, help="Old path prefix")
@click.option("--to", "to_path", required=True, help="New path prefix")
@click.option("--dry-run", is_flag=True, help="Show what would be updated without making changes")
def update_paths(from_path: str, to_path: str, dry_run: bool):
    """Update resource paths after files move.

    Updates both resource paths and link target paths when files are moved
    or directories are renamed. Also attempts to resolve any previously
    unresolved links that now match.

    Examples:

    \b
      # Preview path updates
      ai-lessons admin update-paths --from /old/docs --to /new/docs --dry-run

    \b
      # Apply path updates
      ai-lessons admin update-paths --from /old/docs --to /new/docs
    """
    config = get_config()
    core.ensure_initialized(config)

    counts = core.update_resource_paths(from_path, to_path, dry_run=dry_run, config=config)

    if dry_run:
        click.echo("Dry run - would update:")
    else:
        click.echo("Updated:")

    click.echo(f"  Resources: {counts['resources']}")
    click.echo(f"  Links: {counts['links']}")

    if counts["newly_resolved"] > 0:
        click.echo(f"  Newly resolved links: {counts['newly_resolved']}")


@admin.command("clear-resources")
@click.option("--pattern", "-p", help="Filter by title (case-insensitive substring)")
@click.option("--type", "-t", "resource_type", type=click.Choice(["doc", "script"]),
              help="Filter by resource type")
@click.option("--version", "-v", help="Filter by version")
@click.option("--tags", help="Filter by tags (comma-separated, matches any)")
@click.option("--all", "clear_all", is_flag=True, help="Clear ALL resources (required if no filters)")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without making changes")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def clear_resources(
    pattern: Optional[str],
    resource_type: Optional[str],
    version: Optional[str],
    tags: Optional[str],
    clear_all: bool,
    dry_run: bool,
    yes: bool,
):
    """Clear resources from the database.

    Requires either filters or --all flag for safety.

    \b
    Examples:
      # Clear all resources (requires --all)
      ai-lessons admin clear-resources --all

    \b
      # Clear only v2 docs
      ai-lessons admin clear-resources --version v2 --type doc

    \b
      # Preview what would be deleted
      ai-lessons admin clear-resources --tags test --dry-run
    """
    from .db import get_db

    # Safety check: require filters or --all
    has_filters = any([pattern, resource_type, version, tags])
    if not has_filters and not clear_all:
        click.echo("Error: No filters provided. Use --all to clear all resources, or specify filters.", err=True)
        click.echo("  Filters: --pattern, --type, --version, --tags", err=True)
        sys.exit(1)

    config = get_config()
    core.ensure_initialized(config)

    tag_list = _parse_tags(tags)

    # Find matching resources
    resources = core.list_resources(
        pattern=pattern,
        resource_type=resource_type,
        version=version,
        tags=tag_list,
        config=config,
    )

    if not resources:
        click.echo("No resources match the specified filters.")
        return

    click.echo(f"{'Would delete' if dry_run else 'Will delete'} {len(resources)} resource(s):")
    for resource in resources[:10]:
        click.echo(f"  [{resource.id[:12]}...] {resource.title}")
    if len(resources) > 10:
        click.echo(f"  ... and {len(resources) - 10} more")

    if dry_run:
        return

    # Confirm deletion
    if not yes:
        if not click.confirm("Are you sure you want to delete these resources?"):
            click.echo("Aborted.")
            return

    # Delete resources
    deleted = 0
    with get_db(config) as conn:
        for resource in resources:
            # Delete in correct order for foreign keys
            conn.execute("DELETE FROM resource_links WHERE from_resource_id = ?", (resource.id,))
            conn.execute("DELETE FROM resource_links WHERE resolved_resource_id = ?", (resource.id,))

            cursor = conn.execute("SELECT id FROM resource_chunks WHERE resource_id = ?", (resource.id,))
            chunk_ids = [row["id"] for row in cursor.fetchall()]
            for chunk_id in chunk_ids:
                conn.execute("DELETE FROM chunk_embeddings WHERE chunk_id = ?", (chunk_id,))

            conn.execute("DELETE FROM resource_chunks WHERE resource_id = ?", (resource.id,))
            conn.execute("DELETE FROM resource_embeddings WHERE resource_id = ?", (resource.id,))
            conn.execute("DELETE FROM resource_versions WHERE resource_id = ?", (resource.id,))
            conn.execute("DELETE FROM resource_tags WHERE resource_id = ?", (resource.id,))
            conn.execute("DELETE FROM resources WHERE id = ?", (resource.id,))
            deleted += 1

        conn.commit()

    click.echo(f"Deleted {deleted} resource(s).")


@admin.command("feedback-stats")
@click.option("--list", "-l", "list_entries", is_flag=True, help="List recent feedback entries")
@click.option("--limit", "-n", default=20, help="Number of entries to list (default 20)")
@click.option("--version-eq", help="Filter by exact version (e.g., 0.1.0)")
@click.option("--version-lt", help="Filter by versions less than (e.g., 0.2.0)")
@click.option("--version-gt", help="Filter by versions greater than (e.g., 0.1.0)")
def feedback_stats(
    list_entries: bool,
    limit: int,
    version_eq: Optional[str],
    version_lt: Optional[str],
    version_gt: Optional[str],
):
    """View feedback statistics for quality monitoring.

    Shows aggregate statistics about search quality feedback.
    Use --list to see individual feedback entries.

    Version filtering examples:
      --version-eq 0.1.0     Filter for exactly version 0.1.0
      --version-gt 0.1.0     Filter for versions > 0.1.0
      --version-lt 0.2.0     Filter for versions < 0.2.0

    Combine filters to create ranges:
      --version-gt 0.1.0 --version-lt 0.3.0   Versions between 0.1.0 and 0.3.0
    """
    stats = core.get_feedback_stats(
        version_eq=version_eq,
        version_lt=version_lt,
        version_gt=version_gt,
    )

    click.echo("Search Feedback Statistics")
    click.echo("=" * 40)

    # Show version filter if applied
    if "version_filter" in stats:
        vf = stats["version_filter"]
        filters = []
        if vf.get("eq"):
            filters.append(f"= {vf['eq']}")
        if vf.get("gt"):
            filters.append(f"> {vf['gt']}")
        if vf.get("lt"):
            filters.append(f"< {vf['lt']}")
        if filters:
            click.echo(f"Version filter: {', '.join(filters)}")
            click.echo()

    click.echo(f"Total feedback entries: {stats['total_feedback']}")

    if stats['total_feedback'] > 0:
        click.echo(f"Average invocations: {stats['avg_invocations']}")
        click.echo(f"Min invocations: {stats['min_invocations']}")
        click.echo(f"Max invocations: {stats['max_invocations']}")
        click.echo(f"Entries with suggestions: {stats['with_suggestions']}")

    if list_entries:
        entries = core.list_feedback(limit=limit)
        if entries:
            click.echo()
            click.echo(f"Recent Feedback (last {len(entries)}):")
            click.echo("-" * 40)
            for entry in entries:
                version_str = f" v{entry.version}" if entry.version else ""
                click.echo(f"#{entry.id} [{entry.created_at[:10]}]{version_str} {entry.invocation_count} invocations")
                click.echo(f"  Task: {entry.task}")
                click.echo(f"  Queries: {'; '.join(entry.queries)}")
                if entry.suggestion:
                    click.echo(f"  Suggestion: {entry.suggestion}")
                click.echo()


# =============================================================================
# CONTRIBUTE group - Add and modify lessons, resources, and rules
# =============================================================================

@main.group()
def contribute():
    """Add and modify lessons, resources, and rules."""
    pass


@contribute.command()
@click.option("--title", "-t", required=True, help="Lesson title")
@click.option("--content", "-c", help="Lesson content (or use stdin)")
@click.option("--tags", help="Comma-separated tags")
@click.option("--context", "contexts", multiple=True, help="Context where this applies")
@click.option("--anti-context", "anti_contexts", multiple=True, help="Context where this does NOT apply")
@click.option("--confidence", type=click.Choice(["very-low", "low", "medium", "high", "very-high"]))
@click.option("--source", type=click.Choice(["inferred", "tested", "documented", "observed", "hearsay"]))
@click.option("--source-notes", help="Notes about the source")
@click.option("--link-resource", "linked_resources", multiple=True, help="Resource ID to link (can specify multiple)")
def add(
    title: str,
    content: Optional[str],
    tags: Optional[str],
    contexts: tuple,
    anti_contexts: tuple,
    confidence: Optional[str],
    source: Optional[str],
    source_notes: Optional[str],
    linked_resources: tuple,
):
    """Add a new lesson."""
    # Read content from stdin if not provided
    if content is None:
        if sys.stdin.isatty():
            click.echo("Enter content (Ctrl+D to finish):")
        content = sys.stdin.read().strip()

    if not content:
        click.echo("Error: Content is required", err=True)
        sys.exit(1)

    # Verify linked resources exist before creating lesson
    for resource_id in linked_resources:
        resource = core.get_resource(resource_id)
        if not resource:
            click.echo(f"Error: Resource not found: {resource_id}", err=True)
            sys.exit(1)

    lesson_id = core.add_lesson(
        title=title,
        content=content,
        tags=_parse_tags(tags),
        contexts=list(contexts) if contexts else None,
        anti_contexts=list(anti_contexts) if anti_contexts else None,
        confidence=confidence,
        source=source,
        source_notes=source_notes,
    )

    # Create links to resources
    for resource_id in linked_resources:
        core.link_lesson_to_resource(lesson_id, resource_id)

    click.echo(f"Added lesson: {lesson_id}")
    if linked_resources:
        click.echo(f"  Linked to {len(linked_resources)} resource(s)")


@contribute.command()
@click.argument("lesson_id")
@click.option("--title", "-t", help="New title")
@click.option("--content", "-c", help="New content")
@click.option("--tags", help="New comma-separated tags (replaces existing)")
@click.option("--confidence", type=click.Choice(["very-low", "low", "medium", "high", "very-high"]))
@click.option("--source", type=click.Choice(["inferred", "tested", "documented", "observed", "hearsay"]))
@click.option("--source-notes", help="New source notes")
def update(
    lesson_id: str,
    title: Optional[str],
    content: Optional[str],
    tags: Optional[str],
    confidence: Optional[str],
    source: Optional[str],
    source_notes: Optional[str],
):
    """Update an existing lesson."""
    success = core.update_lesson(
        lesson_id=lesson_id,
        title=title,
        content=content,
        tags=_parse_tags(tags),
        confidence=confidence,
        source=source,
        source_notes=source_notes,
    )

    if success:
        click.echo(f"Updated lesson: {lesson_id}")
    else:
        click.echo(f"Lesson not found: {lesson_id}", err=True)
        sys.exit(1)


@contribute.command()
@click.argument("lesson_id")
@click.confirmation_option(prompt="Are you sure you want to delete this lesson?")
def delete(lesson_id: str):
    """Delete a lesson."""
    success = core.delete_lesson(lesson_id)

    if success:
        click.echo(f"Deleted lesson: {lesson_id}")
    else:
        click.echo(f"Lesson not found: {lesson_id}", err=True)
        sys.exit(1)


@contribute.command()
@click.argument("from_id")
@click.argument("to_id")
@click.option("--relation", "-r", required=True, help="Relationship type (e.g., related_to, derived_from)")
def link(from_id: str, to_id: str, relation: str):
    """Create a link between two lessons."""
    success = core.link_lessons(from_id, to_id, relation)

    if success:
        click.echo(f"Linked {from_id} --[{relation}]--> {to_id}")
    else:
        click.echo("Link already exists or lessons not found.", err=True)
        sys.exit(1)


@contribute.command()
@click.argument("from_id")
@click.argument("to_id")
@click.option("--relation", "-r", help="Specific relation to remove (all if not specified)")
def unlink(from_id: str, to_id: str, relation: Optional[str]):
    """Remove link(s) between two lessons."""
    count = core.unlink_lessons(from_id, to_id, relation)
    click.echo(f"Removed {count} link(s)")


@contribute.command("link-resource")
@click.argument("lesson_id")
@click.argument("resource_id")
@click.option("--relation", "-r", default="related_to", help="Relationship type (default: related_to)")
def link_resource(lesson_id: str, resource_id: str, relation: str):
    """Link a lesson to a resource.

    Creates a connection between a lesson and a resource document/script.
    This allows related documentation to be surfaced alongside lessons.
    """
    # Verify lesson exists
    lesson = core.get_lesson(lesson_id)
    if not lesson:
        click.echo(f"Lesson not found: {lesson_id}", err=True)
        sys.exit(1)

    # Verify resource exists
    resource = core.get_resource(resource_id)
    if not resource:
        click.echo(f"Resource not found: {resource_id}", err=True)
        sys.exit(1)

    success = core.link_lesson_to_resource(lesson_id, resource_id, relation)

    if success:
        click.echo(f"Linked lesson \"{lesson.title}\" --[{relation}]--> resource \"{resource.title}\"")
    else:
        click.echo("Link already exists.", err=True)
        sys.exit(1)


@contribute.command("unlink-resource")
@click.argument("lesson_id")
@click.argument("resource_id")
def unlink_resource(lesson_id: str, resource_id: str):
    """Remove a link between a lesson and a resource."""
    success = core.unlink_lesson_from_resource(lesson_id, resource_id)

    if success:
        click.echo(f"Unlinked lesson {lesson_id} from resource {resource_id}")
    else:
        click.echo("Link not found.", err=True)
        sys.exit(1)


# --- Resource commands ---


def _get_git_root(path: Path) -> Optional[Path]:
    """Get the git repository root for a path, if it's in a git repo."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _find_common_ancestor(paths: list[Path]) -> Path:
    """Find the highest-level shared directory among paths."""
    if len(paths) == 1:
        return paths[0].parent

    # Get all parts for each path
    all_parts = [p.resolve().parts for p in paths]

    # Find common prefix
    common_parts = []
    for parts in zip(*all_parts):
        if len(set(parts)) == 1:
            common_parts.append(parts[0])
        else:
            break

    if common_parts:
        return Path(*common_parts)
    return Path("/")


def _determine_root_dir(paths: list[Path], explicit_root: Optional[str]) -> Path:
    """Determine the root directory for title generation.

    Priority:
    1. Explicit --root if provided
    2. Git repo root (if first file is in a git repo)
    3. Common ancestor directory (multiple files)
    4. Parent directory (single file)
    """
    if explicit_root:
        return Path(explicit_root).resolve()

    # Try git root from first file
    git_root = _get_git_root(paths[0])
    if git_root:
        return git_root

    # Fall back to common ancestor or parent
    return _find_common_ancestor(paths)


def _generate_title(path: Path, root_dir: Path) -> str:
    """Generate a title from a path relative to root_dir.

    Title format: root_dir.name / relative_path
    Example: jira-cloud-rest-api/v3/Apis/IssueVotesApi.md
    """
    abs_path = path.resolve()
    try:
        relative = abs_path.relative_to(root_dir)
        return f"{root_dir.name}/{relative}"
    except ValueError:
        # Path is not under root_dir, use filename
        return abs_path.name


@contribute.command("add-resource")
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--type", "-t", "resource_type", required=True, type=click.Choice(["doc", "script"]),
              help="Resource type")
@click.option("--root", "-r", "root_dir", type=click.Path(exists=True),
              help="Root directory for title generation (default: git root or common ancestor)")
@click.option("--version", "versions", multiple=True, help="Version(s) this resource applies to")
@click.option("--tags", help="Comma-separated tags")
# Chunking options
@click.option("--chunk-strategy", type=click.Choice(["auto", "headers", "delimiter", "fixed", "none"]),
              default="auto", help="Chunking strategy (default: auto)")
@click.option("--chunk-min-size", default=100, type=int, help="Min chunk size in tokens (default: 100)")
@click.option("--chunk-max-size", default=800, type=int, help="Max chunk size in tokens (default: 800)")
@click.option("--chunk-header-levels", default="2,3",
              help="Header levels to split on, comma-separated (default: 2,3)")
@click.option("--chunk-delimiter", help="Custom delimiter pattern (regex)")
@click.option("--preview", is_flag=True, help="Preview chunking for first file without storing")
@click.option("--generate-summaries", is_flag=True, help="Generate LLM summaries for chunks (requires summaries config)")
def add_resource(
    paths: tuple,
    resource_type: str,
    root_dir: Optional[str],
    versions: tuple,
    tags: Optional[str],
    chunk_strategy: str,
    chunk_min_size: int,
    chunk_max_size: int,
    chunk_header_levels: str,
    chunk_delimiter: Optional[str],
    preview: bool,
    generate_summaries: bool,
):
    """Add doc or script resource(s).

    Titles are auto-generated from the file path relative to the root directory.
    The root directory is determined by: --root flag > git repo root > common ancestor.

    \b
    Examples:
      # Import a single doc (title: jira-cloud-rest-api/v3/Apis/IssueVotesApi.md)
      ai-lessons contribute add-resource -t doc v3/Apis/IssueVotesApi.md --version v3

    \b
      # Import multiple docs with glob
      ai-lessons contribute add-resource -t doc v3/Apis/*.md --version v3 --tags api,jira

    \b
      # Import with explicit root
      ai-lessons contribute add-resource -t doc --root /path/to/project src/**/*.py

    \b
      # Preview chunking before import
      ai-lessons contribute add-resource -t doc myfile.md --preview

    For documents, content is automatically chunked for better search.
    """
    from .chunking import ChunkingConfig, chunk_document

    # Convert to Path objects
    path_objs = [Path(p) for p in paths]

    # Determine root directory for title generation
    root = _determine_root_dir(path_objs, root_dir)

    # Build chunking config
    header_levels = [int(x.strip()) for x in chunk_header_levels.split(",") if x.strip()]
    chunking_config = ChunkingConfig(
        strategy=chunk_strategy,
        min_chunk_size=chunk_min_size,
        max_chunk_size=chunk_max_size,
        header_split_levels=header_levels,
        delimiter_pattern=chunk_delimiter,
    )

    # Preview mode - just show first file
    if preview:
        path_obj = path_objs[0]
        content = path_obj.read_text()
        result = chunk_document(content, chunking_config, source_path=str(path_obj))
        title = _generate_title(path_obj, root)
        click.echo(f"Preview for: {title}")
        click.echo(f"  Root: {root}")
        click.echo()
        _display_chunking_preview(result)
        return

    # Process each file
    total_chunks = 0
    all_warnings = []
    added_ids = []

    for path_obj in path_objs:
        title = _generate_title(path_obj, root)
        path_str = str(path_obj.resolve())

        # For doc type, run chunking to get stats
        result = None
        if resource_type == "doc":
            content = path_obj.read_text()
            result = chunk_document(content, chunking_config, source_path=path_str)

        resource_id = core.add_resource(
            type=resource_type,
            title=title,
            path=path_str,
            versions=list(versions) if versions else None,
            tags=_parse_tags(tags),
            chunking_config=chunking_config if resource_type == "doc" else None,
        )

        added_ids.append(resource_id)

        if result:
            total_chunks += len(result.chunks)
            all_warnings.extend(result.warnings)

        click.echo(f"Added: {resource_id[:12]}... {title}")

    # Summary
    click.echo()
    click.echo(f"Added {len(added_ids)} {resource_type}(s)")
    if resource_type == "doc":
        click.echo(f"  Total chunks: {total_chunks}")
        if all_warnings:
            click.echo(f"  Warnings: {len(all_warnings)}")

        # Generate summaries if requested
        if generate_summaries:
            config = get_config()
            if not config.summaries.enabled:
                click.echo("  Warning: --generate-summaries specified but summaries not configured.", err=True)
                click.echo("  Tip: Add 'summaries' section to config.yaml to enable.", err=True)
            else:
                click.echo("  Generating summaries...")
                from .summaries import generate_chunk_summaries
                total_summaries = 0
                for resource_id in added_ids:
                    try:
                        summaries = generate_chunk_summaries(resource_id=resource_id, config=config)
                        total_summaries += len(summaries)
                    except Exception as e:
                        click.echo(f"  Warning: Failed for {resource_id[:12]}...: {e}", err=True)
                click.echo(f"  Generated {total_summaries} summaries.")
        else:
            config = get_config()
            if config.summaries.enabled:
                click.echo("  Tip: Use --generate-summaries to create searchable summaries.")


@contribute.command("refresh-resource")
@click.argument("resource_id")
def refresh_resource(resource_id: str):
    """Refresh a resource's content from its source path."""
    success = core.refresh_resource(resource_id)

    if success:
        click.echo(f"Refreshed resource: {resource_id}")
    else:
        click.echo(f"Resource not found or has no path: {resource_id}", err=True)
        sys.exit(1)


@contribute.command("delete-resource")
@click.argument("resource_id")
@click.confirmation_option(prompt="Are you sure you want to delete this resource?")
def delete_resource(resource_id: str):
    """Delete a resource."""
    success = core.delete_resource(resource_id)

    if success:
        click.echo(f"Deleted resource: {resource_id}")
    else:
        click.echo(f"Resource not found: {resource_id}", err=True)
        sys.exit(1)


# --- Rule commands ---


@contribute.command("suggest-rule")
@click.option("--title", "-t", required=True, help="Rule title")
@click.option("--content", "-c", help="Rule content (or use stdin)")
@click.option("--rationale", "-r", required=True, help="Why this rule exists")
@click.option("--tags", help="Comma-separated tags")
@click.option("--link-lesson", "linked_lessons", multiple=True, help="Lesson ID to link")
@click.option("--link-resource", "linked_resources", multiple=True, help="Resource ID to link")
def suggest_rule(
    title: str,
    content: Optional[str],
    rationale: str,
    tags: Optional[str],
    linked_lessons: tuple,
    linked_resources: tuple,
):
    """Suggest a rule for human approval."""
    # Read content from stdin if not provided
    if content is None:
        if sys.stdin.isatty():
            click.echo("Enter rule content (Ctrl+D to finish):")
        content = sys.stdin.read().strip()

    if not content:
        click.echo("Error: Content is required", err=True)
        sys.exit(1)

    rule_id = core.suggest_rule(
        title=title,
        content=content,
        rationale=rationale,
        tags=_parse_tags(tags),
        linked_lessons=list(linked_lessons) if linked_lessons else None,
        linked_resources=list(linked_resources) if linked_resources else None,
    )

    click.echo(f"Suggested rule: {rule_id}")
    click.echo("Note: Rule requires approval before it will appear in search results.")


@contribute.command()
@click.option("--task", "-t", required=True, help="Brief description of what you were trying to find")
@click.option("--queries", "-q", required=True, help="Semicolon-separated list of queries used")
@click.option("--invocation-count", "-n", required=True, type=int, help="Number of ai-lessons invocations needed")
@click.option("--suggestion", "-s", help="Optional feedback or suggestions for the tool")
def feedback(task: str, queries: str, invocation_count: int, suggestion: Optional[str]):
    """Submit feedback on search quality.

    Help us improve ai-lessons by recording how well the search worked for you.

    Examples:

        ai-lessons contribute feedback -t "find jira vote API docs" -q "jira vote;vote on issue" -n 2

        ai-lessons contribute feedback -t "workflow status info" -q "workflow;transitions" -n 4 -s "missing workflow docs"
    """
    # Parse queries from semicolon-separated string
    query_list = [q.strip() for q in queries.split(";") if q.strip()]

    if not query_list:
        click.echo("Error: At least one query is required", err=True)
        sys.exit(1)

    if invocation_count < 1:
        click.echo("Error: Invocation count must be at least 1", err=True)
        sys.exit(1)

    feedback_id = core.add_feedback(
        task=task,
        queries=query_list,
        invocation_count=invocation_count,
        suggestion=suggestion,
    )

    click.echo(f"Recorded feedback #{feedback_id}")
    click.echo(f"  Task: {task}")
    click.echo(f"  Queries: {', '.join(query_list)}")
    click.echo(f"  Invocations: {invocation_count}")
    if suggestion:
        click.echo(f"  Suggestion: {suggestion}")
    click.echo("Thank you for helping improve ai-lessons!")


# =============================================================================
# RECALL group - Search and view lessons
# =============================================================================

@main.group()
def recall():
    """Search and view lessons."""
    pass


@recall.result_callback()
def _after_recall_command(*args, **kwargs):
    """Show feedback reminder after any recall command."""
    _show_feedback_reminder()


@recall.command()
@click.argument("query")
@click.option("--tags", help="Filter by comma-separated tags")
@click.option("--context", help="Filter by context")
@click.option("--confidence-min", type=click.Choice(["very-low", "low", "medium", "high", "very-high"]))
@click.option("--source", help="Filter by source type")
@click.option("--limit", "-n", default=10, help="Maximum results")
@click.option("--strategy", type=click.Choice(["hybrid", "semantic", "keyword"]), default="hybrid")
@click.option("--verbose", "-v", is_flag=True, help="Show content preview")
def search(
    query: str,
    tags: Optional[str],
    context: Optional[str],
    confidence_min: Optional[str],
    source: Optional[str],
    limit: int,
    strategy: str,
    verbose: bool,
):
    """Search for lessons."""
    results = core.recall(
        query=query,
        tags=_parse_tags(tags),
        contexts=[context] if context else None,
        confidence_min=confidence_min,
        source=source,
        limit=limit,
        strategy=strategy,
    )

    if not results:
        click.echo("No results found.")
        return

    for result in results:
        click.echo(_format_search_result(result, verbose))
        click.echo()


@recall.command()
@click.argument("lesson_id")
def show(lesson_id: str):
    """Show a lesson by ID."""
    lesson = core.get_lesson(lesson_id)

    if lesson is None:
        click.echo(f"Lesson not found: {lesson_id}", err=True)
        sys.exit(1)

    click.echo(_format_lesson(lesson, verbose=True))


@recall.command()
@click.argument("lesson_id")
@click.option("--depth", "-d", default=1, help="Traversal depth")
@click.option("--relation", "-r", multiple=True, help="Filter by relation type")
def related(lesson_id: str, depth: int, relation: tuple):
    """Show lessons related to a given lesson."""
    lessons = core.get_related(
        lesson_id=lesson_id,
        depth=depth,
        relations=list(relation) if relation else None,
    )

    if not lessons:
        click.echo("No related lessons found.")
        return

    for lesson in lessons:
        click.echo(_format_lesson(lesson))
        click.echo()


@recall.command("tags")
@click.option("--counts", is_flag=True, help="Show usage counts")
def list_tags(counts: bool):
    """List all tags."""
    tags = core.list_tags(with_counts=counts)

    if not tags:
        click.echo("No tags found.")
        return

    for tag in tags:
        if counts:
            click.echo(f"{tag.name} ({tag.count})")
        else:
            click.echo(tag.name)


@recall.command("sources")
def list_sources():
    """List all source types."""
    sources = core.list_sources()

    for source in sources:
        click.echo(f"{source.name}")
        if source.description:
            click.echo(f"  {source.description}")
        if source.typical_confidence:
            click.echo(f"  typical confidence: {source.typical_confidence}")


@recall.command("confidence")
def list_confidence():
    """List all confidence levels."""
    levels = core.list_confidence_levels()

    for level in levels:
        click.echo(f"{level.ordinal}. {level.name}")


# --- Resource recall commands ---


@recall.command("search-resources")
@click.argument("query")
@click.option("--type", "-t", "resource_type", type=click.Choice(["doc", "script"]),
              help="Filter by resource type")
@click.option("--version", "versions", multiple=True, help="Filter by version(s)")
@click.option("--tags", help="Filter by comma-separated tags")
@click.option("--limit", "-n", default=10, help="Maximum results")
@click.option("--verbose", "-v", is_flag=True, help="Show content preview")
def search_resources_cmd(
    query: str,
    resource_type: Optional[str],
    versions: tuple,
    tags: Optional[str],
    limit: int,
    verbose: bool,
):
    """Search for resources (docs and scripts)."""
    results = search_resources(
        query=query,
        resource_type=resource_type,
        versions=list(versions) if versions else None,
        tag_filter=_parse_tags(tags),
        limit=limit,
    )

    if not results:
        click.echo("No resources found.")
        return

    for result in results:
        click.echo(_format_search_result(result, verbose))
        click.echo()


@recall.command("show-resource")
@click.argument("resource_id")
def show_resource(resource_id: str):
    """Show a resource by ID."""
    resource = core.get_resource(resource_id)

    if resource is None:
        click.echo(f"Resource not found: {resource_id}", err=True)
        sys.exit(1)

    click.echo(_format_resource(resource, verbose=True))


@recall.command("show-chunk")
@click.argument("chunk_id")
def show_chunk(chunk_id: str):
    """Show a resource chunk by ID."""
    chunk = core.get_chunk(chunk_id)

    if chunk is None:
        click.echo(f"Chunk not found: {chunk_id}", err=True)
        sys.exit(1)

    click.echo(_format_chunk(chunk, verbose=True))

    # Show linked resources
    links = core.get_chunk_links(chunk_id)
    if links:
        click.echo()
        click.echo("---")
        click.echo("Linked resources:")
        for link in links:
            if link.resolved_resource_id:
                resource = core.get_resource(link.resolved_resource_id)
                if resource:
                    target = f"[{link.resolved_resource_id[:12]}...] {resource.title}"
                else:
                    target = f"[{link.resolved_resource_id[:12]}...] (deleted)"
            else:
                target = "(not imported)"

            # Show original link syntax
            fragment = f"#{link.to_fragment}" if link.to_fragment else ""
            click.echo(f"  [{link.link_text}](...{fragment}) -> {target}")


@recall.command("related")
@click.argument("resource_id")
def show_related(resource_id: str):
    """Show resources related to the given resource via links.

    Displays both outgoing links (from this resource) and incoming links
    (to this resource from other resources).
    """
    resource = core.get_resource(resource_id)

    if resource is None:
        click.echo(f"Resource not found: {resource_id}", err=True)
        sys.exit(1)

    outgoing, incoming = core.get_related_resources(resource_id)

    click.echo(f"Links from \"{resource.title}\":")
    if outgoing:
        for link in outgoing:
            if link.resolved_resource_id:
                target = core.get_resource(link.resolved_resource_id)
                if target:
                    click.echo(f"  -> [{link.resolved_resource_id[:12]}...] {target.title}")
                else:
                    click.echo(f"  -> [{link.resolved_resource_id[:12]}...] (deleted)")
            else:
                # Show path for unresolved links
                click.echo(f"  -> {link.to_path} (not imported)")
    else:
        click.echo("  (none)")

    click.echo()
    click.echo(f"Links to \"{resource.title}\":")
    if incoming:
        for link in incoming:
            source = core.get_resource(link.from_resource_id)
            if source:
                click.echo(f"  <- [{link.from_resource_id[:12]}...] {source.title}")
            else:
                click.echo(f"  <- [{link.from_resource_id[:12]}...] (deleted)")
    else:
        click.echo("  (none)")


@recall.command("list-resources")
@click.option("--pattern", "-p", help="Filter by title (case-insensitive substring)")
@click.option("--type", "-t", "resource_type", type=click.Choice(["doc", "script"]),
              help="Filter by resource type")
@click.option("--version", "-v", help="Filter by version")
@click.option("--tags", help="Filter by tags (comma-separated, matches any)")
def list_resources_cmd(pattern: Optional[str], resource_type: Optional[str],
                       version: Optional[str], tags: Optional[str]):
    """List resources with optional filtering."""
    from .db import get_db

    config = get_config()
    core.ensure_initialized(config)

    tag_list = _parse_tags(tags)
    resources = core.list_resources(
        pattern=pattern,
        resource_type=resource_type,
        version=version,
        tags=tag_list,
        config=config,
    )

    if not resources:
        click.echo("No resources found.")
        return

    # Get chunk counts for each resource
    with get_db(config) as conn:
        chunk_counts = {}
        for resource in resources:
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM resource_chunks WHERE resource_id = ?",
                (resource.id,),
            )
            chunk_counts[resource.id] = cursor.fetchone()["count"]

    click.echo(f"Found {len(resources)} resource(s):\n")
    for resource in resources:
        type_indicator = f"[{resource.type}]" if resource.type else "[resource]"
        chunk_count = chunk_counts.get(resource.id, 0)
        chunk_info = f", {chunk_count} chunk(s)" if chunk_count > 0 else ""

        versions_str = ", ".join(resource.versions) if resource.versions else "unversioned"
        click.echo(f"{type_indicator} [{resource.id}] {resource.title}")
        click.echo(f"  versions: {versions_str}{chunk_info}")
        if resource.tags:
            click.echo(f"  tags: {', '.join(resource.tags)}")
        click.echo()


@recall.command("list-chunks")
@click.argument("resource_id")
def list_chunks_cmd(resource_id: str):
    """List all chunks for a resource."""
    resource = core.get_resource(resource_id)

    if resource is None:
        click.echo(f"Resource not found: {resource_id}", err=True)
        sys.exit(1)

    chunks = core.list_chunks(resource_id)

    if not chunks:
        click.echo(f"No chunks found for resource '{resource.title}'.")
        return

    click.echo(f"Chunks in \"{resource.title}\" ({len(chunks)} total):\n")
    for chunk in chunks:
        # Determine title to display
        if chunk.title:
            title = chunk.title
        elif chunk.breadcrumb:
            title = chunk.breadcrumb
        else:
            title = "(no title)"

        # Line info
        line_info = ""
        if chunk.start_line is not None and chunk.end_line is not None:
            line_info = f"lines {chunk.start_line + 1}-{chunk.end_line + 1}, "

        token_info = f"{chunk.token_count} tokens" if chunk.token_count else "? tokens"
        summary_marker = " [S]" if chunk.summary else ""

        click.echo(f"  {chunk.chunk_index}. [{chunk.id[:12]}...] ({line_info}{token_info}){summary_marker}")
        click.echo(f"     {title}")

    # Legend
    click.echo()
    click.echo("Legend: [S] = has summary")


@recall.command("run-resource")
@click.argument("resource_id")
@click.argument("args", nargs=-1)
def run_resource(resource_id: str, args: tuple):
    """Run a script resource."""
    resource = core.get_resource(resource_id)

    if resource is None:
        click.echo(f"Resource not found: {resource_id}", err=True)
        sys.exit(1)

    if resource.type != "script":
        click.echo(f"Error: Resource is not a script (type: {resource.type})", err=True)
        sys.exit(1)

    if not resource.path:
        click.echo("Error: Script has no path", err=True)
        sys.exit(1)

    from pathlib import Path
    if not Path(resource.path).exists():
        click.echo(f"Error: Script file not found: {resource.path}", err=True)
        sys.exit(1)

    # Execute the script
    try:
        result = subprocess.run(
            [resource.path] + list(args),
            capture_output=False,
            text=True,
        )
        sys.exit(result.returncode)
    except PermissionError:
        click.echo(f"Error: Script is not executable: {resource.path}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error running script: {e}", err=True)
        sys.exit(1)


@recall.command("show-rule")
@click.argument("rule_id")
def show_rule(rule_id: str):
    """Show a rule by ID."""
    rule = core.get_rule(rule_id)

    if rule is None:
        click.echo(f"Rule not found: {rule_id}", err=True)
        sys.exit(1)

    click.echo(_format_rule(rule, verbose=True))


if __name__ == "__main__":
    main()
