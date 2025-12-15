"""Command-line interface for ai-lessons."""

import sys
from typing import Optional

import click

from . import core
from .config import Config, get_config, DEFAULT_LESSONS_DIR
from .db import init_db
from .search import SearchResult


def _parse_tags(tags: Optional[str]) -> Optional[list[str]]:
    """Parse comma-separated tags string."""
    if not tags:
        return None
    return [t.strip() for t in tags.split(",") if t.strip()]


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


@click.group()
@click.version_option()
def main():
    """AI Lessons - Knowledge management with semantic search."""
    pass


@main.command()
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


@main.command()
@click.option("--title", "-t", required=True, help="Lesson title")
@click.option("--content", "-c", help="Lesson content (or use stdin)")
@click.option("--tags", help="Comma-separated tags")
@click.option("--context", "contexts", multiple=True, help="Context where this applies")
@click.option("--anti-context", "anti_contexts", multiple=True, help="Context where this does NOT apply")
@click.option("--confidence", type=click.Choice(["very-low", "low", "medium", "high", "very-high"]))
@click.option("--source", type=click.Choice(["inferred", "tested", "documented", "observed", "hearsay"]))
@click.option("--source-notes", help="Notes about the source")
def add(
    title: str,
    content: Optional[str],
    tags: Optional[str],
    contexts: tuple,
    anti_contexts: tuple,
    confidence: Optional[str],
    source: Optional[str],
    source_notes: Optional[str],
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

    click.echo(f"Added lesson: {lesson_id}")


@main.command()
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


@main.command()
@click.argument("lesson_id")
def show(lesson_id: str):
    """Show a lesson by ID."""
    lesson = core.get_lesson(lesson_id)

    if lesson is None:
        click.echo(f"Lesson not found: {lesson_id}", err=True)
        sys.exit(1)

    click.echo(_format_lesson(lesson, verbose=True))


@main.command()
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


@main.command()
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


@main.command()
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


@main.command()
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


@main.command()
@click.argument("from_id")
@click.argument("to_id")
@click.option("--relation", "-r", help="Specific relation to remove (all if not specified)")
def unlink(from_id: str, to_id: str, relation: Optional[str]):
    """Remove link(s) between two lessons."""
    count = core.unlink_lessons(from_id, to_id, relation)
    click.echo(f"Removed {count} link(s)")


@main.command("tags")
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


@main.command("sources")
def list_sources():
    """List all source types."""
    sources = core.list_sources()

    for source in sources:
        click.echo(f"{source.name}")
        if source.description:
            click.echo(f"  {source.description}")
        if source.typical_confidence:
            click.echo(f"  typical confidence: {source.typical_confidence}")


@main.command("confidence")
def list_confidence():
    """List all confidence levels."""
    levels = core.list_confidence_levels()

    for level in levels:
        click.echo(f"{level.ordinal}. {level.name}")


@main.group()
def manage():
    """Management commands for tags, sources, etc."""
    pass


@manage.command("merge-tags")
@click.argument("from_tag")
@click.argument("to_tag")
def merge_tags(from_tag: str, to_tag: str):
    """Merge one tag into another."""
    count = core.merge_tags(from_tag, to_tag)
    click.echo(f"Merged '{from_tag}' into '{to_tag}' ({count} lessons affected)")


@manage.command("add-source")
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


@main.command()
def stats():
    """Show database statistics."""
    config = get_config()
    core.ensure_initialized(config)

    from .db import get_db

    with get_db(config) as conn:
        # Count lessons
        cursor = conn.execute("SELECT COUNT(*) FROM lessons")
        lesson_count = cursor.fetchone()[0]

        # Count tags
        cursor = conn.execute("SELECT COUNT(DISTINCT tag) FROM lesson_tags")
        tag_count = cursor.fetchone()[0]

        # Count edges
        cursor = conn.execute("SELECT COUNT(*) FROM edges")
        edge_count = cursor.fetchone()[0]

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
    click.echo(f"Lessons: {lesson_count}")
    click.echo(f"Tags: {tag_count}")
    click.echo(f"Edges: {edge_count}")

    if confidence_counts:
        click.echo("\nBy confidence:")
        for conf, count in confidence_counts.items():
            click.echo(f"  {conf or 'unset'}: {count}")

    if source_counts:
        click.echo("\nBy source:")
        for src, count in source_counts.items():
            click.echo(f"  {src or 'unset'}: {count}")


if __name__ == "__main__":
    main()
