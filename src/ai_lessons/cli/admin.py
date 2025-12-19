"""Admin CLI commands for database and system management."""

from __future__ import annotations

import sys
from typing import Optional

import click

from .. import core
from ..config import get_config, DEFAULT_LESSONS_DIR
from ..db import init_db, get_db
from .display import ID_DISPLAY_LENGTH, format_rule
from .utils import parse_tags


@click.group()
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
        click.echo(format_rule(rule))
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


# NOTE: reject-rule has been removed in favor of `contribute delete RUL...`


@admin.command("reindex")
def reindex_resources():
    """Reindex all resources (re-generate embeddings)."""
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
    from ..summaries import generate_chunk_summaries

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
    tag_list = parse_tags(tags)

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
            click.echo(f"  {chunk['id'][:ID_DISPLAY_LENGTH]} {title}")
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


@admin.command("clear")
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
      ai-lessons admin clear --all

    \b
      # Clear only v2 docs
      ai-lessons admin clear --version v2 --type doc

    \b
      # Preview what would be deleted
      ai-lessons admin clear --tags test --dry-run
    """
    # Safety check: require filters or --all
    has_filters = any([pattern, resource_type, version, tags])
    if not has_filters and not clear_all:
        click.echo("Error: No filters provided. Use --all to clear all resources, or specify filters.", err=True)
        click.echo("  Filters: --pattern, --type, --version, --tags", err=True)
        sys.exit(1)

    config = get_config()
    core.ensure_initialized(config)

    tag_list = parse_tags(tags)

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
        click.echo(f"  [{resource.id[:ID_DISPLAY_LENGTH]}] {resource.title}")
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
            # Delete edges involving this resource (resource_anchors cascade deletes)
            conn.execute("DELETE FROM edges WHERE (from_id = ? AND from_type = 'resource') OR (to_id = ? AND to_type = 'resource')", (resource.id, resource.id))

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
