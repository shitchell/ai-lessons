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
from .utils import parse_tags, show_feedback_reminder, warn_deprecation


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
# Universal options
@click.option("--type", "types", multiple=True, help="Filter to type(s): lesson, resource, chunk, rule")
@click.option("--tags", help="Filter by comma-separated tags")
@click.option("--limit", "-n", default=10, help="Maximum results per type")
@click.option("--verbose", "-v", is_flag=True, help="Show content preview")
# Lesson options
@click.option("--lesson-context", help="Filter by lesson context")
@click.option("--lesson-confidence-min", type=click.Choice(["very-low", "low", "medium", "high", "very-high"]), help="Minimum confidence level")
@click.option("--lesson-source", help="Filter by lesson source type")
@click.option("--lesson-strategy", type=click.Choice(["hybrid", "semantic", "keyword"]), default="hybrid", help="Search strategy")
# Resource options
@click.option("--resource-type", type=click.Choice(["doc", "script"]), help="Filter by doc/script")
@click.option("--resource-version", "resource_versions", multiple=True, help="Filter by version(s)")
@click.option("--resource-grouped", "-g", is_flag=True, help="Group chunks by parent resource")
# Rule options
@click.option("--rule-pending", is_flag=True, help="Include pending rules")
@click.option("--rule-approved/--no-rule-approved", default=True, help="Include approved rules (default: true)")
def search(
    query: str,
    types: tuple,
    tags: Optional[str],
    limit: int,
    verbose: bool,
    # Lesson options
    lesson_context: Optional[str],
    lesson_confidence_min: Optional[str],
    lesson_source: Optional[str],
    lesson_strategy: str,
    # Resource options
    resource_type: Optional[str],
    resource_versions: tuple,
    resource_grouped: bool,
    # Rule options
    rule_pending: bool,
    rule_approved: bool,
):
    """Search across lessons, resources, and rules with namespaced options.

    Universal options (--type, --tags, --limit) apply to all types.
    Type-specific options (--lesson-*, --resource-*, --rule-*) only apply to their type.

    Examples:
      # Search all types
      ai-lessons recall search "OAuth2"

      # Search only lessons with high confidence
      ai-lessons recall search "OAuth2" --type lesson --lesson-confidence-min high

      # Search resources and filter by version
      ai-lessons recall search "OAuth2" --type resource --resource-version v3

      # Search all but filter lessons by confidence (resources unaffected)
      ai-lessons recall search "OAuth2" --lesson-confidence-min high
    """
    tag_list = parse_tags(tags)
    has_results = False

    # Determine which types to search
    types_to_search = set(types) if types else {"lesson", "resource", "rule"}

    # Search lessons
    if "lesson" in types_to_search:
        context_list = [lesson_context] if lesson_context else None
        lessons = core.recall(
            query=query,
            tags=tag_list,
            contexts=context_list,
            confidence_min=lesson_confidence_min,
            source=lesson_source,
            limit=limit,
            strategy=lesson_strategy,
        )
        if lessons:
            has_results = True
            click.echo(f"=== Lessons ({len(lessons)}) ===")
            click.echo()
            for result in lessons:
                click.echo(format_search_result(result, verbose))
                click.echo()

    # Search resources (chunks)
    if "resource" in types_to_search or "chunk" in types_to_search:
        if resource_grouped:
            top_matches, grouped_results = search_resources_grouped(
                query=query,
                tag_filter=tag_list,
                resource_type=resource_type,
                versions=list(resource_versions) if resource_versions else None,
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
                resource_type=resource_type,
                versions=list(resource_versions) if resource_versions else None,
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
    if "rule" in types_to_search:
        # Fetch rules based on approval status
        if rule_pending and rule_approved:
            all_rules = core.list_rules(tags=tag_list, pending=True, approved=True, limit=limit)
        elif rule_pending:
            all_rules = core.list_rules(tags=tag_list, pending=True, approved=False, limit=limit)
        elif rule_approved:
            all_rules = core.list_rules(tags=tag_list, pending=False, approved=True, limit=limit)
        else:
            all_rules = []

        # Simple keyword filtering for rules (they don't have embeddings)
        from ..search import _keyword_score, RuleResult
        scored_rules = []
        for rule in all_rules:
            score = _keyword_score(query, rule.title, rule.content)
            if score > 0:
                scored_rules.append((rule, score))

        scored_rules.sort(key=lambda x: x[1], reverse=True)
        top_rules = scored_rules[:limit]

        if top_rules:
            has_results = True
            click.echo(f"=== Rules ({len(top_rules)}) ===")
            click.echo()
            for rule, score in top_rules:
                result = RuleResult(
                    id=rule.id,
                    title=rule.title,
                    content=rule.content,
                    score=score,
                    result_type="rule",
                    tags=rule.tags,
                    rationale=rule.rationale,
                    approved=rule.approved,
                )
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
    warn_deprecation("search-lesson", "search --type lesson")
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
@click.option("--type", "type_hint", type=click.Choice(["lesson", "resource", "chunk", "rule"]),
              help="Explicit type hint (rarely needed with prefixed IDs)")
def show(id: str, verbose: bool, type_hint: Optional[str]):
    """Show any entity by ID. Type detected from prefix.

    IDs are auto-detected from their prefix:
    - LSN... → lesson
    - RES... → resource
    - RES....N → chunk (has .N suffix)
    - RUL... → rule

    Use --type for legacy/unprefixed IDs.
    """
    # Detect type from ID prefix
    try:
        entity_type, _ = core.parse_entity_id(id)
    except ValueError:
        # Invalid prefix - use hint or fail
        if type_hint:
            entity_type = type_hint
        else:
            click.echo(f"Unknown ID format: {id}", err=True)
            click.echo("Use --type to specify entity type for legacy IDs.", err=True)
            sys.exit(1)

    # Override with type hint if provided
    if type_hint:
        entity_type = type_hint

    if entity_type == "chunk":
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
                        target = f"[{link.resolved_resource_id[:15]}...] {resource.title}"
                    else:
                        target = f"[{link.resolved_resource_id[:15]}...] (deleted)"
                else:
                    target = "(not imported)"
                fragment = f"#{link.to_fragment}" if link.to_fragment else ""
                click.echo(f"  [{link.link_text}](...{fragment}) -> {target}")

    elif entity_type == "resource":
        resource = core.get_resource(id)
        if resource is None:
            click.echo(f"Resource not found: {id}", err=True)
            sys.exit(1)
        click.echo(format_resource(resource, verbose=verbose))

    elif entity_type == "lesson":
        lesson = core.get_lesson(id)
        if lesson is None:
            click.echo(f"Lesson not found: {id}", err=True)
            sys.exit(1)
        click.echo(format_lesson(lesson, verbose=verbose))

    elif entity_type == "rule":
        rule = core.get_rule(id)
        if rule is None:
            click.echo(f"Rule not found: {id}", err=True)
            sys.exit(1)
        click.echo(format_rule(rule, verbose=verbose))

    else:
        click.echo(f"Unknown entity type: {entity_type}", err=True)
        sys.exit(1)


@recall.command("related")
@click.argument("id")
@click.option("--depth", "-d", default=1, help="Traversal depth")
@click.option("--relation", "-r", multiple=True, help="Filter by relation type")
def related(id: str, depth: int, relation: tuple):
    """Show entities related to the given ID via graph edges.

    Type is auto-detected from ID prefix (LSN, RES, RUL).
    Shows all outgoing edges from this entity to others.
    """
    # Detect type from ID prefix
    try:
        entity_type, _ = core.parse_entity_id(id)
    except ValueError:
        click.echo(f"Unknown ID format: {id}", err=True)
        sys.exit(1)

    config = get_config()
    core.ensure_initialized(config)

    relations_list = list(relation) if relation else None

    if entity_type == "lesson":
        # Use existing get_related for lesson→lesson
        lessons = core.get_related(
            lesson_id=id,
            depth=depth,
            relations=relations_list,
        )
        if lessons:
            click.echo(f"Related lessons ({len(lessons)}):\n")
            for lesson in lessons:
                click.echo(format_lesson(lesson))
                click.echo()
        else:
            click.echo("No related lessons found.")

    elif entity_type == "resource":
        # Show related resources via links
        outgoing, incoming = core.get_related_resources(id)
        resource = core.get_resource(id)
        if resource is None:
            click.echo(f"Resource not found: {id}", err=True)
            sys.exit(1)

        has_any = False
        if outgoing:
            has_any = True
            click.echo(f"Links from \"{resource.title}\":")
            for link in outgoing:
                if link.resolved_resource_id:
                    target = core.get_resource(link.resolved_resource_id)
                    if target:
                        click.echo(f"  -> [{link.resolved_resource_id[:15]}...] {target.title}")
                    else:
                        click.echo(f"  -> [{link.resolved_resource_id[:15]}...] (deleted)")
                else:
                    click.echo(f"  -> {link.to_path} (not imported)")
            click.echo()

        if incoming:
            has_any = True
            click.echo(f"Links to \"{resource.title}\":")
            for link in incoming:
                source = core.get_resource(link.from_resource_id)
                if source:
                    click.echo(f"  <- [{link.from_resource_id[:15]}...] {source.title}")
                else:
                    click.echo(f"  <- [{link.from_resource_id[:15]}...] (deleted)")

        if not has_any:
            click.echo("No related resources found.")

    elif entity_type == "rule":
        # Show linked lessons and resources
        rule = core.get_rule(id)
        if rule is None:
            click.echo(f"Rule not found: {id}", err=True)
            sys.exit(1)

        has_any = False
        if rule.linked_lessons:
            has_any = True
            click.echo(f"Linked lessons ({len(rule.linked_lessons)}):")
            for lesson_id in rule.linked_lessons:
                lesson = core.get_lesson(lesson_id)
                if lesson:
                    click.echo(f"  -> [{lesson_id[:15]}...] {lesson.title}")
                else:
                    click.echo(f"  -> [{lesson_id[:15]}...] (deleted)")
            click.echo()

        if rule.linked_resources:
            has_any = True
            click.echo(f"Linked resources ({len(rule.linked_resources)}):")
            for resource_id in rule.linked_resources:
                resource = core.get_resource(resource_id)
                if resource:
                    click.echo(f"  -> [{resource_id[:15]}...] {resource.title}")
                else:
                    click.echo(f"  -> [{resource_id[:15]}...] (deleted)")

        if not has_any:
            click.echo("No related entities found.")

    elif entity_type == "chunk":
        click.echo("Chunks don't have direct relations. Use the parent resource ID instead.", err=True)
        sys.exit(1)

    else:
        click.echo(f"Unknown entity type: {entity_type}", err=True)
        sys.exit(1)


@recall.command("related-lesson")
@click.argument("lesson_id")
@click.option("--depth", "-d", default=1, help="Traversal depth")
@click.option("--relation", "-r", multiple=True, help="Filter by relation type")
def related_lesson(lesson_id: str, depth: int, relation: tuple):
    """Show lessons related to a given lesson."""
    warn_deprecation("related-lesson", "related LSN...")
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
    warn_deprecation("search-resources", "search --type resource")
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
    warn_deprecation("show-resource", "show RES...")
    ctx.invoke(show, id=resource_id)


@recall.command("show-chunk")
@click.argument("chunk_id")
@click.pass_context
def show_chunk(ctx, chunk_id: str):
    """Show a resource chunk by ID (alias for 'show')."""
    warn_deprecation("show-chunk", "show RES....N")
    ctx.invoke(show, id=chunk_id)


@recall.command("related-resource")
@click.argument("resource_id")
def related_resource(resource_id: str):
    """Show resources related to the given resource via links.

    Displays both outgoing links (from this resource) and incoming links
    (to this resource from other resources).
    """
    warn_deprecation("related-resource", "related RES...")
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
                    click.echo(f"  -> [{link.resolved_resource_id[:15]}...] {target.title}")
                else:
                    click.echo(f"  -> [{link.resolved_resource_id[:15]}...] (deleted)")
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
                click.echo(f"  <- [{link.from_resource_id[:15]}...] {source.title}")
            else:
                click.echo(f"  <- [{link.from_resource_id[:15]}...] (deleted)")
    else:
        click.echo("  (none)")


@recall.command("list")
@click.option("--type", "entity_type", required=True,
              type=click.Choice(["lesson", "resource", "chunk", "rule"]),
              help="Entity type to list (required)")
# Universal options
@click.option("--pattern", "-p", help="Filter by title (case-insensitive substring)")
@click.option("--tags", help="Filter by comma-separated tags")
@click.option("--limit", "-n", default=100, help="Maximum results")
# Resource options
@click.option("--resource-type", type=click.Choice(["doc", "script"]), help="Filter by doc/script")
@click.option("--resource-version", help="Filter by version")
# Rule options
@click.option("--rule-pending", is_flag=True, help="Include pending rules")
@click.option("--rule-approved/--no-rule-approved", default=True, help="Include approved rules")
# Chunk options
@click.option("--chunk-parent", help="Parent resource ID (required for --type chunk)")
# Lesson options
@click.option("--lesson-confidence", type=click.Choice(["very-low", "low", "medium", "high", "very-high"]), help="Filter by confidence")
@click.option("--lesson-source", help="Filter by source")
def list_cmd(
    entity_type: str,
    pattern: Optional[str],
    tags: Optional[str],
    limit: int,
    resource_type: Optional[str],
    resource_version: Optional[str],
    rule_pending: bool,
    rule_approved: bool,
    chunk_parent: Optional[str],
    lesson_confidence: Optional[str],
    lesson_source: Optional[str],
):
    """List entities by type with filtering.

    Examples:
      ai-lessons recall list --type lesson
      ai-lessons recall list --type resource --resource-type script
      ai-lessons recall list --type rule --rule-pending
      ai-lessons recall list --type chunk --chunk-parent RES01KCP...
    """
    config = get_config()
    core.ensure_initialized(config)
    tag_list = parse_tags(tags)

    if entity_type == "lesson":
        lessons = core.list_lessons(
            pattern=pattern,
            tags=tag_list,
            confidence=lesson_confidence,
            source=lesson_source,
            limit=limit,
            config=config,
        )
        if not lessons:
            click.echo("No lessons found.")
            return

        click.echo(f"Found {len(lessons)} lesson(s):\n")
        for lesson in lessons:
            click.echo(format_lesson(lesson))
            click.echo()

    elif entity_type == "resource":
        resources = core.list_resources(
            pattern=pattern,
            resource_type=resource_type,
            version=resource_version,
            tags=tag_list,
            config=config,
        )
        if not resources:
            click.echo("No resources found.")
            return

        # Get chunk counts
        with get_db(config) as conn:
            chunk_counts = {}
            for resource in resources:
                cursor = conn.execute(
                    "SELECT COUNT(*) as count FROM resource_chunks WHERE resource_id = ?",
                    (resource.id,)
                )
                chunk_counts[resource.id] = cursor.fetchone()["count"]

        click.echo(f"Found {len(resources)} resource(s):\n")
        for resource in resources:
            type_indicator = f"[{resource.type}]" if resource.type else "[resource]"
            chunk_count = chunk_counts.get(resource.id, 0)
            chunk_info = f", {chunk_count} chunk(s)" if chunk_count > 0 else ""
            versions_str = ", ".join(resource.versions) if resource.versions else "unversioned"
            click.echo(f"{type_indicator} [{resource.id[:15]}...] {resource.title}")
            click.echo(f"  versions: {versions_str}{chunk_info}")
            if resource.tags:
                click.echo(f"  tags: {', '.join(resource.tags)}")
            click.echo()

    elif entity_type == "rule":
        rules = core.list_rules(
            pattern=pattern,
            tags=tag_list,
            pending=rule_pending,
            approved=rule_approved,
            limit=limit,
            config=config,
        )
        if not rules:
            click.echo("No rules found.")
            return

        click.echo(f"Found {len(rules)} rule(s):\n")
        for rule in rules:
            click.echo(format_rule(rule))
            click.echo()

    elif entity_type == "chunk":
        if not chunk_parent:
            click.echo("Error: --chunk-parent is required for --type chunk", err=True)
            click.echo("Chunks belong to resources. Specify the parent resource ID.", err=True)
            sys.exit(1)

        resource = core.get_resource(chunk_parent)
        if resource is None:
            click.echo(f"Resource not found: {chunk_parent}", err=True)
            sys.exit(1)

        chunks = core.list_chunks(chunk_parent)
        if not chunks:
            click.echo(f"No chunks found for resource '{resource.title}'.")
            return

        click.echo(f"Chunks in \"{resource.title}\" ({len(chunks)} total):\n")
        for chunk in chunks:
            title = chunk.title or chunk.breadcrumb or "(no title)"
            line_info = ""
            if chunk.start_line is not None and chunk.end_line is not None:
                line_info = f"lines {chunk.start_line + 1}-{chunk.end_line + 1}, "
            token_info = f"{chunk.token_count} tokens" if chunk.token_count else "? tokens"
            summary_marker = " [S]" if chunk.summary else ""
            click.echo(f"  {chunk.chunk_index}. [{chunk.id[:15]}...] ({line_info}{token_info}){summary_marker}")
            click.echo(f"     {title}")

        click.echo()
        click.echo("Legend: [S] = has summary")


@recall.command("list-resources")
@click.option("--pattern", "-p", help="Filter by title (case-insensitive substring)")
@click.option("--type", "-t", "resource_type", type=click.Choice(["doc", "script"]),
              help="Filter by resource type")
@click.option("--version", "-v", help="Filter by version")
@click.option("--tags", help="Filter by tags (comma-separated, matches any)")
def list_resources_cmd(pattern: Optional[str], resource_type: Optional[str],
                       version: Optional[str], tags: Optional[str]):
    """List resources with optional filtering."""
    warn_deprecation("list-resources", "list --type resource")
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
    warn_deprecation("list-chunks", "list --type chunk --chunk-parent RES...")
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

        click.echo(f"  {chunk.chunk_index}. [{chunk.id[:15]}...] ({line_info}{token_info}){summary_marker}")
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
    warn_deprecation("show-rule", "show RUL...")
    rule = core.get_rule(rule_id)

    if rule is None:
        click.echo(f"Rule not found: {rule_id}", err=True)
        sys.exit(1)

    click.echo(format_rule(rule, verbose=True))
