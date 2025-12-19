"""Contribute CLI commands for adding and modifying lessons, resources, and rules."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click

from .. import core
from ..config import get_config
from .display import ID_DISPLAY_LENGTH, display_chunking_preview
from .utils import determine_root_dir, generate_title, parse_tags, warn_deprecation


@click.group()
def contribute():
    """Add and modify lessons, resources, and rules."""
    pass


@contribute.command("add")
@click.option("--type", "-t", "entity_type", required=True, type=click.Choice(["lesson", "rule"]),
              help="Entity type to add")
# Shared options
@click.option("--title", required=True, help="Title (required for both)")
@click.option("--content", "-c", help="Content (or use stdin)")
@click.option("--tags", help="Comma-separated tags")
@click.option("--link-resource", "linked_resources", multiple=True, help="Resource ID to link")
# Lesson-specific options
@click.option("--context", "contexts", multiple=True, help="[lesson] Context where this applies")
@click.option("--anti-context", "anti_contexts", multiple=True, help="[lesson] Context where this does NOT apply")
@click.option("--confidence", type=click.Choice(["very-low", "low", "medium", "high", "very-high"]),
              help="[lesson] Confidence level")
@click.option("--source", type=click.Choice(["inferred", "tested", "documented", "observed", "hearsay"]),
              help="[lesson] Source type")
@click.option("--source-notes", help="[lesson] Notes about the source")
# Rule-specific options
@click.option("--rationale", "-r", help="[rule] Why this rule exists (required for rules)")
@click.option("--link-lesson", "linked_lessons", multiple=True, help="[rule] Lesson ID to link")
def add(
    entity_type: str,
    title: str,
    content: Optional[str],
    tags: Optional[str],
    linked_resources: tuple,
    contexts: tuple,
    anti_contexts: tuple,
    confidence: Optional[str],
    source: Optional[str],
    source_notes: Optional[str],
    rationale: Optional[str],
    linked_lessons: tuple,
):
    """Add a new lesson or suggest a rule.

    \b
    Examples:
      # Add a lesson
      ai-lessons contribute add --type lesson --title "API Rate Limits" -c "Content here" --tags api,limits

      # Suggest a rule (requires approval)
      ai-lessons contribute add --type rule --title "Use Pagination" --rationale "Prevents timeouts" -c "Always paginate large result sets"
    """
    # Read content from stdin if not provided
    if content is None:
        if sys.stdin.isatty():
            click.echo("Enter content (Ctrl+D to finish):")
        content = sys.stdin.read().strip()

    if not content:
        click.echo("Error: Content is required", err=True)
        sys.exit(1)

    # Verify linked resources exist
    for resource_id in linked_resources:
        resource = core.get_resource(resource_id)
        if not resource:
            click.echo(f"Error: Resource not found: {resource_id}", err=True)
            sys.exit(1)

    if entity_type == "lesson":
        # Validate lesson-specific requirements
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

    elif entity_type == "rule":
        # Validate rule-specific requirements
        if not rationale:
            click.echo("Error: --rationale is required for rules", err=True)
            sys.exit(1)

        # Verify linked lessons exist
        for lesson_id in linked_lessons:
            lesson = core.get_lesson(lesson_id)
            if not lesson:
                click.echo(f"Error: Lesson not found: {lesson_id}", err=True)
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


@contribute.command("update")
@click.argument("id")
# Universal options
@click.option("--title", "-t", help="New title")
@click.option("--tags", help="New comma-separated tags (replaces existing)")
# Lesson options
@click.option("--lesson-content", help="New lesson content")
@click.option("--lesson-confidence", type=click.Choice(["very-low", "low", "medium", "high", "very-high"]), help="New confidence level")
@click.option("--lesson-source", type=click.Choice(["inferred", "tested", "documented", "observed", "hearsay"]), help="New source type")
@click.option("--lesson-source-notes", help="New source notes")
# Resource options
@click.option("--resource-version", "resource_versions", multiple=True, help="New version(s)")
# Rule options
@click.option("--rule-content", help="New rule content")
@click.option("--rule-rationale", help="New rationale")
def update_cmd(
    id: str,
    title: Optional[str],
    tags: Optional[str],
    # Lesson options
    lesson_content: Optional[str],
    lesson_confidence: Optional[str],
    lesson_source: Optional[str],
    lesson_source_notes: Optional[str],
    # Resource options
    resource_versions: tuple,
    # Rule options
    rule_content: Optional[str],
    rule_rationale: Optional[str],
):
    """Update any entity by ID. Type detected from prefix.

    Examples:
      ai-lessons contribute update LSN01KCP... --title "New title"
      ai-lessons contribute update RES01KCP... --tags new,tags --resource-version v4
      ai-lessons contribute update RUL01KCP... --rule-rationale "Better reasoning"
    """
    # Detect type from ID prefix
    try:
        entity_type, _ = core.parse_entity_id(id)
    except ValueError:
        click.echo(f"Unknown ID format: {id}", err=True)
        sys.exit(1)

    tag_list = parse_tags(tags)

    if entity_type == "chunk":
        click.echo("Error: Chunks are updated via their parent resource.", err=True)
        click.echo("Use `refresh RES...` to reload content from filesystem.", err=True)
        sys.exit(1)

    elif entity_type == "lesson":
        success = core.update_lesson(
            lesson_id=id,
            title=title,
            content=lesson_content,
            tags=tag_list,
            confidence=lesson_confidence,
            source=lesson_source,
            source_notes=lesson_source_notes,
        )
        if success:
            click.echo(f"Updated lesson: {id}")
        else:
            click.echo(f"Lesson not found: {id}", err=True)
            sys.exit(1)

    elif entity_type == "resource":
        success = core.update_resource(
            resource_id=id,
            tags=tag_list,
            versions=list(resource_versions) if resource_versions else None,
        )
        if success:
            click.echo(f"Updated resource: {id}")
            click.echo("Note: To update content, use `refresh` to reload from filesystem.")
        else:
            click.echo(f"Resource not found: {id}", err=True)
            sys.exit(1)

    elif entity_type == "rule":
        success = core.update_rule(
            rule_id=id,
            title=title,
            content=rule_content,
            rationale=rule_rationale,
            tags=tag_list,
        )
        if success:
            click.echo(f"Updated rule: {id}")
        else:
            click.echo(f"Rule not found: {id}", err=True)
            sys.exit(1)

    else:
        click.echo(f"Unknown entity type: {entity_type}", err=True)
        sys.exit(1)


@contribute.command("delete")
@click.argument("id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete_cmd(id: str, yes: bool):
    """Delete any entity by ID. Type detected from prefix.

    Examples:
      ai-lessons contribute delete LSN01KCP...
      ai-lessons contribute delete RES01KCP... --yes
      ai-lessons contribute delete RUL01KCP...
    """
    # Detect type from ID prefix
    try:
        entity_type, _ = core.parse_entity_id(id)
    except ValueError:
        click.echo(f"Unknown ID format: {id}", err=True)
        sys.exit(1)

    if entity_type == "chunk":
        click.echo("Error: Chunks are deleted with their parent resource.", err=True)
        click.echo("Use `delete RES...` to delete the parent resource and all its chunks.", err=True)
        sys.exit(1)

    # Confirm deletion
    type_name = entity_type.capitalize()
    if not yes:
        if not click.confirm(f"Are you sure you want to delete this {entity_type}?"):
            click.echo("Aborted.")
            return

    if entity_type == "lesson":
        success = core.delete_lesson(id)
        if success:
            click.echo(f"Deleted lesson: {id}")
        else:
            click.echo(f"Lesson not found: {id}", err=True)
            sys.exit(1)

    elif entity_type == "resource":
        success = core.delete_resource(id)
        if success:
            click.echo(f"Deleted resource: {id}")
        else:
            click.echo(f"Resource not found: {id}", err=True)
            sys.exit(1)

    elif entity_type == "rule":
        success = core.delete_rule(id)
        if success:
            click.echo(f"Deleted rule: {id}")
        else:
            click.echo(f"Rule not found: {id}", err=True)
            sys.exit(1)

    else:
        click.echo(f"Unknown entity type: {entity_type}", err=True)
        sys.exit(1)


@contribute.command("link")
@click.argument("from_id")
@click.argument("to_id")
@click.option("--relation", "-r", default="related_to", help="Relationship type (default: related_to)")
def link_cmd(from_id: str, to_id: str, relation: str):
    """Link any entity to any other entity.

    Type is auto-detected from ID prefixes (LSN, RES, RUL).

    Examples:
      # Lesson to lesson
      ai-lessons contribute link LSN111... LSN222... --relation derived_from

      # Lesson to resource
      ai-lessons contribute link LSN111... RES222... --relation documents

      # Rule to lesson
      ai-lessons contribute link RUL111... LSN222... --relation based_on
    """
    success = core.link_entities(from_id, to_id, relation)

    if success:
        click.echo(f"Linked {from_id[:ID_DISPLAY_LENGTH]} --[{relation}]--> {to_id[:ID_DISPLAY_LENGTH]}")
    else:
        click.echo("Link already exists or invalid IDs.", err=True)
        sys.exit(1)


@contribute.command("unlink")
@click.argument("from_id")
@click.argument("to_id")
@click.option("--relation", "-r", help="Specific relation to remove (all if not specified)")
def unlink_cmd(from_id: str, to_id: str, relation: Optional[str]):
    """Remove link(s) between any two entities.

    Type is auto-detected from ID prefixes (LSN, RES, RUL).

    Examples:
      ai-lessons contribute unlink LSN111... LSN222...
      ai-lessons contribute unlink LSN111... RES222... --relation documents
    """
    count = core.unlink_entities(from_id, to_id, relation)

    if count > 0:
        click.echo(f"Removed {count} link(s)")
    else:
        click.echo("No matching links found.", err=True)
        sys.exit(1)


# --- Resource commands ---


@contribute.command("import")
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
    """Import doc or script resource(s).

    Titles are auto-generated from the file path relative to the root directory.
    The root directory is determined by: --root flag > git repo root > common ancestor.

    \b
    Examples:
      # Import a single doc (title: jira-cloud-rest-api/v3/Apis/IssueVotesApi.md)
      ai-lessons contribute import -t doc v3/Apis/IssueVotesApi.md --version v3

    \b
      # Import multiple docs with glob
      ai-lessons contribute import -t doc v3/Apis/*.md --version v3 --tags api,jira

    \b
      # Import with explicit root
      ai-lessons contribute import -t doc --root /path/to/project src/**/*.py

    \b
      # Preview chunking before import
      ai-lessons contribute import -t doc myfile.md --preview

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

        click.echo(f"Added: {resource_id[:ID_DISPLAY_LENGTH]} {title}")

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
                        click.echo(f"  Warning: Failed for {resource_id[:ID_DISPLAY_LENGTH]}: {e}", err=True)
                click.echo(f"  Generated {total_summaries} summaries.")
        else:
            config = get_config()
            if config.summaries.enabled:
                click.echo("  Tip: Use --generate-summaries to create searchable summaries.")


@contribute.command("refresh")
@click.argument("id")
def refresh_cmd(id: str):
    """Refresh a resource's content from its source path.

    Only applies to resources - other entity types don't have source paths.

    Example:
      ai-lessons contribute refresh RES01KCP...
    """
    # Detect type from ID prefix
    try:
        entity_type, _ = core.parse_entity_id(id)
    except ValueError:
        click.echo(f"Unknown ID format: {id}", err=True)
        sys.exit(1)

    if entity_type != "resource":
        click.echo(f"Error: refresh only applies to resources (got {entity_type}).", err=True)
        if entity_type == "chunk":
            click.echo("Hint: Refresh the parent resource to update chunks.", err=True)
        sys.exit(1)

    success = core.refresh_resource(id)

    if success:
        click.echo(f"Refreshed resource: {id}")
    else:
        click.echo(f"Resource not found or has no path: {id}", err=True)
        sys.exit(1)


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
