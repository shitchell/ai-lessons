"""Recall CLI commands for searching and viewing lessons."""

from __future__ import annotations

import subprocess
import sys
from typing import Optional

import click

from .. import core
from ..config import get_config
from ..db import get_db
from ..search import search_resources, search_resources_grouped, search_rules
from ..chunk_ids import is_chunk_id
from .display import (
    format_chunk,
    format_grouped_search_results,
    format_lesson,
    format_resource,
    format_rule,
    format_search_result,
)
from .utils import parse_tags, show_feedback_reminder


@click.group()
def recall():
    """Search and view lessons."""
    pass


@recall.result_callback()
def _after_recall_command(*args, **kwargs):
    """Show feedback reminder after any recall command."""
    show_feedback_reminder()


@recall.command("search")
@click.argument("query")
@click.option("--tags", help="Filter by comma-separated tags")
@click.option("--limit", "-n", default=10, help="Maximum results per type")
@click.option("--verbose", "-v", is_flag=True, help="Show content preview")
@click.option("--grouped", "-g", is_flag=True, help="Group resource chunks by parent")
def search(
    query: str,
    tags: Optional[str],
    limit: int,
    verbose: bool,
    grouped: bool,
):
    """Search across lessons, resources, and rules.

    This unified search finds relevant content across all knowledge types:
    - Lessons: Short-form knowledge and tips
    - Resources: Documentation and scripts (searched by chunks)
    - Rules: Approved coding standards and guidelines
    """
    tag_list = parse_tags(tags)
    has_results = False

    # Search lessons
    lessons = core.recall(
        query=query,
        tags=tag_list,
        limit=limit,
    )
    if lessons:
        has_results = True
        click.echo(f"=== Lessons ({len(lessons)}) ===")
        click.echo()
        for result in lessons:
            click.echo(format_search_result(result, verbose))
            click.echo()

    # Search resources (chunks)
    if grouped:
        top_matches, grouped_results = search_resources_grouped(
            query=query,
            tag_filter=tag_list,
            limit=limit,
        )
        if grouped_results:
            has_results = True
            click.echo(f"=== Resources ({len(grouped_results)} resources, {len(top_matches)} top chunks) ===")
            click.echo()
            click.echo(format_grouped_search_results(top_matches, grouped_results))
            click.echo()
    else:
        resources = search_resources(
            query=query,
            tag_filter=tag_list,
            limit=limit,
        )
        if resources:
            has_results = True
            click.echo(f"=== Resources ({len(resources)}) ===")
            click.echo()
            for result in resources:
                click.echo(format_search_result(result, verbose))
                click.echo()

    # Search rules
    rules = search_rules(
        query=query,
        tag_filter=tag_list,
        limit=limit,
    )
    if rules:
        has_results = True
        click.echo(f"=== Rules ({len(rules)}) ===")
        click.echo()
        for result in rules:
            click.echo(format_search_result(result, verbose))
            click.echo()

    if not has_results:
        click.echo("No results found.")


@recall.command("search-lesson")
@click.argument("query")
@click.option("--tags", help="Filter by comma-separated tags")
@click.option("--context", help="Filter by context")
@click.option("--confidence-min", type=click.Choice(["very-low", "low", "medium", "high", "very-high"]))
@click.option("--source", help="Filter by source type")
@click.option("--limit", "-n", default=10, help="Maximum results")
@click.option("--strategy", type=click.Choice(["hybrid", "semantic", "keyword"]), default="hybrid")
@click.option("--verbose", "-v", is_flag=True, help="Show content preview")
def search_lesson(
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
        tags=parse_tags(tags),
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
        click.echo(format_search_result(result, verbose))
        click.echo()


@recall.command()
@click.argument("id")
@click.option("--verbose", "-v", is_flag=True, default=True, help="Show full content")
def show(id: str, verbose: bool):
    """Show a resource, chunk, or lesson by ID.

    IDs with a .N suffix are chunks (e.g., ABC123.5).
    IDs without a suffix are resources or lessons.
    """
    if is_chunk_id(id):
        # Chunk ID (has .N suffix)
        chunk = core.get_chunk(id)
        if chunk is None:
            click.echo(f"Chunk not found: {id}", err=True)
            sys.exit(1)
        click.echo(format_chunk(chunk, verbose=verbose))

        # Show linked resources
        links = core.get_chunk_links(id)
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
                fragment = f"#{link.to_fragment}" if link.to_fragment else ""
                click.echo(f"  [{link.link_text}](...{fragment}) -> {target}")
    else:
        # Try resource first, then lesson (for backwards compatibility)
        resource = core.get_resource(id)
        if resource is not None:
            click.echo(format_resource(resource, verbose=verbose))
        else:
            # Fall back to lesson
            lesson = core.get_lesson(id)
            if lesson is not None:
                click.echo(format_lesson(lesson, verbose=verbose))
            else:
                click.echo(f"Not found: {id}", err=True)
                click.echo("(checked: resource, lesson)", err=True)
                sys.exit(1)


@recall.command("related-lesson")
@click.argument("lesson_id")
@click.option("--depth", "-d", default=1, help="Traversal depth")
@click.option("--relation", "-r", multiple=True, help="Filter by relation type")
def related_lesson(lesson_id: str, depth: int, relation: tuple):
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
        click.echo(format_lesson(lesson))
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
@click.option("--grouped", "-g", is_flag=True, help="Group chunks by resource")
def search_resources_cmd(
    query: str,
    resource_type: Optional[str],
    versions: tuple,
    tags: Optional[str],
    limit: int,
    verbose: bool,
    grouped: bool,
):
    """Search for resources (docs and scripts)."""
    if grouped:
        # Use grouped search and display
        top_matches, grouped_results = search_resources_grouped(
            query=query,
            resource_type=resource_type,
            versions=list(versions) if versions else None,
            tag_filter=parse_tags(tags),
            limit=limit,
        )

        if not grouped_results:
            click.echo("No resources found.")
            return

        click.echo(format_grouped_search_results(top_matches, grouped_results))
    else:
        # Use flat search and display (backwards compatible)
        results = search_resources(
            query=query,
            resource_type=resource_type,
            versions=list(versions) if versions else None,
            tag_filter=parse_tags(tags),
            limit=limit,
        )

        if not results:
            click.echo("No resources found.")
            return

        for result in results:
            click.echo(format_search_result(result, verbose))
            click.echo()


@recall.command("show-resource")
@click.argument("resource_id")
@click.pass_context
def show_resource(ctx, resource_id: str):
    """Show a resource by ID (alias for 'show')."""
    ctx.invoke(show, id=resource_id)


@recall.command("show-chunk")
@click.argument("chunk_id")
@click.pass_context
def show_chunk(ctx, chunk_id: str):
    """Show a resource chunk by ID (alias for 'show')."""
    ctx.invoke(show, id=chunk_id)


@recall.command("related-resource")
@click.argument("resource_id")
def related_resource(resource_id: str):
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
    config = get_config()
    core.ensure_initialized(config)

    tag_list = parse_tags(tags)
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
    except OSError as e:
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

    click.echo(format_rule(rule, verbose=True))
