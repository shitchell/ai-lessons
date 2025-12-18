"""Contribute CLI commands for adding and modifying lessons, resources, and rules."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click

from .. import core
from ..config import get_config
from .display import display_chunking_preview
from .utils import determine_root_dir, generate_title, parse_tags


@click.group()
def contribute():
    """Add and modify lessons, resources, and rules."""
    pass


@contribute.command("add-lesson")
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
        tags=parse_tags(tags),
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


@contribute.command("update-lesson")
@click.argument("lesson_id")
@click.option("--title", "-t", help="New title")
@click.option("--content", "-c", help="New content")
@click.option("--tags", help="New comma-separated tags (replaces existing)")
@click.option("--confidence", type=click.Choice(["very-low", "low", "medium", "high", "very-high"]))
@click.option("--source", type=click.Choice(["inferred", "tested", "documented", "observed", "hearsay"]))
@click.option("--source-notes", help="New source notes")
def update_lesson(
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
        tags=parse_tags(tags),
        confidence=confidence,
        source=source,
        source_notes=source_notes,
    )

    if success:
        click.echo(f"Updated lesson: {lesson_id}")
    else:
        click.echo(f"Lesson not found: {lesson_id}", err=True)
        sys.exit(1)


@contribute.command("delete-lesson")
@click.argument("lesson_id")
@click.confirmation_option(prompt="Are you sure you want to delete this lesson?")
def delete_lesson(lesson_id: str):
    """Delete a lesson."""
    success = core.delete_lesson(lesson_id)

    if success:
        click.echo(f"Deleted lesson: {lesson_id}")
    else:
        click.echo(f"Lesson not found: {lesson_id}", err=True)
        sys.exit(1)


@contribute.command("link-lesson")
@click.argument("from_id")
@click.argument("to_id")
@click.option("--relation", "-r", required=True, help="Relationship type (e.g., related_to, derived_from)")
def link_lesson(from_id: str, to_id: str, relation: str):
    """Create a link between two lessons."""
    success = core.link_lessons(from_id, to_id, relation)

    if success:
        click.echo(f"Linked {from_id} --[{relation}]--> {to_id}")
    else:
        click.echo("Link already exists or lessons not found.", err=True)
        sys.exit(1)


@contribute.command("unlink-lesson")
@click.argument("from_id")
@click.argument("to_id")
@click.option("--relation", "-r", help="Specific relation to remove (all if not specified)")
def unlink_lesson(from_id: str, to_id: str, relation: Optional[str]):
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
    from ..chunking import ChunkingConfig, chunk_document

    # Convert to Path objects
    path_objs = [Path(p) for p in paths]

    # Determine root directory for title generation
    root = determine_root_dir(path_objs, root_dir)

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
        title = generate_title(path_obj, root)
        click.echo(f"Preview for: {title}")
        click.echo(f"  Root: {root}")
        click.echo()
        display_chunking_preview(result)
        return

    # Process each file
    total_chunks = 0
    all_warnings = []
    added_ids = []

    for path_obj in path_objs:
        title = generate_title(path_obj, root)
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
            tags=parse_tags(tags),
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
                from ..summaries import generate_chunk_summaries
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
        tags=parse_tags(tags),
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
