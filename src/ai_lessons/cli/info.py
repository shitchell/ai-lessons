"""Info CLI commands for schema discovery and database statistics."""

from __future__ import annotations

import json
from typing import Optional

import click

from .. import core


@click.group()
def info():
    """Schema discovery and database statistics."""
    pass


@info.command("tags")
@click.option("--counts", is_flag=True, help="Show usage counts per entity type")
@click.option(
    "--type",
    "entity_type",
    type=click.Choice(["lesson", "resource", "rule"]),
    help="Filter by entity type",
)
@click.option("--pattern", "-p", help="Filter tags by substring (case-insensitive)")
@click.option(
    "--sort",
    type=click.Choice(["name", "count"]),
    default="name",
    help="Sort order (default: name)",
)
@click.option("--json", "json_output", is_flag=True, help="Machine-readable JSON output")
def tags(
    counts: bool,
    entity_type: Optional[str],
    pattern: Optional[str],
    sort: str,
    json_output: bool,
):
    """List all tags with usage information.

    Shows active tags across all entity types, plus any defined tag aliases.
    """
    tags_list = core.list_tags_detailed(entity_type=entity_type, pattern=pattern)
    aliases = core.list_tag_aliases()

    # Sort by count if requested
    if sort == "count":
        tags_list.sort(key=lambda t: t.total_count, reverse=True)

    if json_output:
        output = {
            "tags": [
                {
                    "name": t.name,
                    "lesson_count": t.lesson_count,
                    "resource_count": t.resource_count,
                    "rule_count": t.rule_count,
                    "total_count": t.total_count,
                }
                for t in tags_list
            ],
            "aliases": [{"alias": a, "canonical": c} for a, c in aliases],
        }
        click.echo(json.dumps(output, indent=2))
        return

    if not tags_list and not aliases:
        click.echo("No tags found.")
        return

    if tags_list:
        click.echo("Active tags:")
        for tag in tags_list:
            if counts:
                parts = []
                if tag.lesson_count:
                    parts.append(f"{tag.lesson_count} lesson{'s' if tag.lesson_count != 1 else ''}")
                if tag.resource_count:
                    parts.append(f"{tag.resource_count} resource{'s' if tag.resource_count != 1 else ''}")
                if tag.rule_count:
                    parts.append(f"{tag.rule_count} rule{'s' if tag.rule_count != 1 else ''}")
                click.echo(f"  {tag.name} ({', '.join(parts)})")
            else:
                click.echo(f"  {tag.name}")

    if aliases:
        click.echo("\nTag aliases:")
        for alias, canonical in aliases:
            click.echo(f"  {alias} \u2192 {canonical}")


@info.command("confidence")
@click.option("--counts", is_flag=True, help="Show how many lessons at each level")
@click.option("--json", "json_output", is_flag=True, help="Machine-readable JSON output")
def confidence(counts: bool, json_output: bool):
    """List confidence levels."""
    levels = core.list_confidence_levels(with_counts=counts)

    if json_output:
        output = {
            "confidence_levels": [
                {"name": lvl.name, "ordinal": lvl.ordinal, "count": lvl.count}
                for lvl in levels
            ]
        }
        click.echo(json.dumps(output, indent=2))
        return

    if not levels:
        click.echo("No confidence levels defined.")
        return

    click.echo("Confidence levels:")
    for level in levels:
        if counts:
            lesson_word = "lesson" if level.count == 1 else "lessons"
            click.echo(f"  {level.ordinal}. {level.name} ({level.count} {lesson_word})")
        else:
            click.echo(f"  {level.ordinal}. {level.name}")


@info.command("lesson-sources")
@click.option("--counts", is_flag=True, help="Show how many lessons use each source")
@click.option("--verbose", "-v", is_flag=True, help="Show descriptions and typical confidence")
@click.option("--json", "json_output", is_flag=True, help="Machine-readable JSON output")
def lesson_sources(counts: bool, verbose: bool, json_output: bool):
    """List source types for lessons."""
    sources = core.list_sources(with_counts=counts or json_output)

    if json_output:
        output = {
            "source_types": [
                {
                    "name": src.name,
                    "description": src.description,
                    "typical_confidence": src.typical_confidence,
                    "count": src.count,
                }
                for src in sources
            ]
        }
        click.echo(json.dumps(output, indent=2))
        return

    if not sources:
        click.echo("No source types defined.")
        return

    click.echo("Source types:")
    for src in sources:
        parts = [f"  {src.name}"]
        if verbose and src.description:
            parts.append(f" - {src.description}")
        if verbose and src.typical_confidence:
            parts.append(f" (typical: {src.typical_confidence})")
        if counts:
            lesson_word = "lesson" if src.count == 1 else "lessons"
            parts.append(f" [{src.count} {lesson_word}]")
        click.echo("".join(parts))


@info.command("relations")
@click.option("--counts", is_flag=True, help="Show edge counts per relation type")
@click.option(
    "--type",
    "entity_type",
    type=click.Choice(["lesson", "resource", "rule"]),
    help="Filter by from/to entity type",
)
@click.option("--json", "json_output", is_flag=True, help="Machine-readable JSON output")
def relations(counts: bool, entity_type: Optional[str], json_output: bool):
    """List edge relation types used in the graph."""
    relation_list = core.list_relations(entity_type=entity_type)

    if json_output:
        output = {
            "relations": [
                {"name": rel.name, "count": rel.count} for rel in relation_list
            ]
        }
        click.echo(json.dumps(output, indent=2))
        return

    if not relation_list:
        click.echo("No edge relations found.")
        return

    click.echo("Edge relations:")
    for rel in relation_list:
        if counts:
            edge_word = "edge" if rel.count == 1 else "edges"
            click.echo(f"  {rel.name} ({rel.count} {edge_word})")
        else:
            click.echo(f"  {rel.name}")


@info.command("stats")
@click.option("--json", "json_output", is_flag=True, help="Machine-readable JSON output")
@click.option("--verbose", "-v", is_flag=True, help="Detailed breakdown")
def stats(json_output: bool, verbose: bool):
    """Show database statistics."""
    from ..config import get_config

    config = get_config()
    db_stats = core.get_database_stats(config)

    if json_output:
        db_stats["database"] = str(config.db_path)
        click.echo(json.dumps(db_stats, indent=2))
        return

    click.echo(f"Database: {config.db_path}")

    click.echo(f"\nLessons: {db_stats['lessons']['count']}")
    click.echo(f"Resources: {db_stats['resources']['count']} ({db_stats['resources']['chunks']} chunks)")
    click.echo(f"Rules: {db_stats['rules']['count']}")
    click.echo(f"Edges: {db_stats['edges']['count']}")
    click.echo(f"Tags: {db_stats['tags']['count']}")

    if verbose:
        if db_stats.get("confidence_distribution"):
            click.echo("\nLessons by confidence:")
            for conf, count in db_stats["confidence_distribution"].items():
                click.echo(f"  {conf or 'unset'}: {count}")

        if db_stats.get("source_distribution"):
            click.echo("\nLessons by source:")
            for src, count in db_stats["source_distribution"].items():
                click.echo(f"  {src or 'unset'}: {count}")
