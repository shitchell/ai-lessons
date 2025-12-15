"""Core API for ai-lessons."""

import struct
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ulid import ULID

from .config import Config, get_config
from .db import get_db, init_db
from .embeddings import embed_text
from .search import SearchResult, hybrid_search, keyword_search, vector_search


@dataclass
class Lesson:
    """A lesson with all its metadata."""
    id: str
    title: str
    content: str
    confidence: Optional[str] = None
    source: Optional[str] = None
    source_notes: Optional[str] = None
    tags: list[str] = None
    contexts: list[str] = None
    anti_contexts: list[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.contexts is None:
            self.contexts = []
        if self.anti_contexts is None:
            self.anti_contexts = []


@dataclass
class SourceType:
    """A source type with its metadata."""
    name: str
    description: Optional[str] = None
    typical_confidence: Optional[str] = None


@dataclass
class ConfidenceLevel:
    """A confidence level with its ordinal."""
    name: str
    ordinal: int


@dataclass
class Tag:
    """A tag with optional count."""
    name: str
    count: int = 0


def ensure_initialized(config: Optional[Config] = None) -> None:
    """Ensure the database is initialized."""
    if config is None:
        config = get_config()
    if not config.db_path.exists():
        init_db(config)


def _resolve_tag_aliases(tags: list[str], config: Config) -> list[str]:
    """Resolve tag aliases to canonical forms."""
    resolved = []
    for tag in tags:
        tag_lower = tag.lower().strip()
        # Check aliases
        canonical = config.tag_aliases.get(tag_lower, tag_lower)
        resolved.append(canonical)
    return list(set(resolved))  # Deduplicate


def _generate_id() -> str:
    """Generate a new ULID for a lesson."""
    return str(ULID())


# --- CRUD Operations ---


def add_lesson(
    title: str,
    content: str,
    tags: Optional[list[str]] = None,
    contexts: Optional[list[str]] = None,
    anti_contexts: Optional[list[str]] = None,
    confidence: Optional[str] = None,
    source: Optional[str] = None,
    source_notes: Optional[str] = None,
    config: Optional[Config] = None,
) -> str:
    """Add a new lesson to the database.

    Args:
        title: The lesson title (keyword searchable).
        content: The lesson content (semantic searchable).
        tags: Optional list of tags.
        contexts: Optional list of contexts where this applies.
        anti_contexts: Optional list of contexts where this does NOT apply.
        confidence: Confidence level (very-low to very-high).
        source: Source type (inferred, tested, documented, observed, hearsay).
        source_notes: Optional notes about the source.
        config: Configuration to use.

    Returns:
        The generated lesson ID.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    # Resolve tag aliases
    if tags:
        tags = _resolve_tag_aliases(tags, config)

    # Generate ID and embedding
    lesson_id = _generate_id()
    embedding = embed_text(f"{title}\n\n{content}", config)
    embedding_blob = struct.pack(f"{len(embedding)}f", *embedding)

    with get_db(config) as conn:
        # Insert lesson
        conn.execute(
            """
            INSERT INTO lessons (id, title, content, confidence, source, source_notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (lesson_id, title, content, confidence, source, source_notes),
        )

        # Insert tags
        if tags:
            conn.executemany(
                "INSERT INTO lesson_tags (lesson_id, tag) VALUES (?, ?)",
                [(lesson_id, tag) for tag in tags],
            )

        # Insert contexts
        if contexts:
            conn.executemany(
                "INSERT INTO lesson_contexts (lesson_id, context, applies) VALUES (?, ?, TRUE)",
                [(lesson_id, ctx) for ctx in contexts],
            )

        # Insert anti-contexts
        if anti_contexts:
            conn.executemany(
                "INSERT INTO lesson_contexts (lesson_id, context, applies) VALUES (?, ?, FALSE)",
                [(lesson_id, ctx) for ctx in anti_contexts],
            )

        # Insert embedding
        conn.execute(
            "INSERT INTO lesson_embeddings (lesson_id, embedding) VALUES (?, ?)",
            (lesson_id, embedding_blob),
        )

        conn.commit()

    return lesson_id


def get_lesson(lesson_id: str, config: Optional[Config] = None) -> Optional[Lesson]:
    """Get a lesson by ID.

    Args:
        lesson_id: The lesson ID.
        config: Configuration to use.

    Returns:
        The lesson if found, None otherwise.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    with get_db(config) as conn:
        # Get lesson
        cursor = conn.execute(
            "SELECT * FROM lessons WHERE id = ?",
            (lesson_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        # Get tags
        cursor = conn.execute(
            "SELECT tag FROM lesson_tags WHERE lesson_id = ?",
            (lesson_id,),
        )
        tags = [r["tag"] for r in cursor.fetchall()]

        # Get contexts
        cursor = conn.execute(
            "SELECT context, applies FROM lesson_contexts WHERE lesson_id = ?",
            (lesson_id,),
        )
        contexts = []
        anti_contexts = []
        for r in cursor.fetchall():
            if r["applies"]:
                contexts.append(r["context"])
            else:
                anti_contexts.append(r["context"])

        return Lesson(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            confidence=row["confidence"],
            source=row["source"],
            source_notes=row["source_notes"],
            tags=tags,
            contexts=contexts,
            anti_contexts=anti_contexts,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def update_lesson(
    lesson_id: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    tags: Optional[list[str]] = None,
    contexts: Optional[list[str]] = None,
    anti_contexts: Optional[list[str]] = None,
    confidence: Optional[str] = None,
    source: Optional[str] = None,
    source_notes: Optional[str] = None,
    config: Optional[Config] = None,
) -> bool:
    """Update an existing lesson.

    Args:
        lesson_id: The lesson ID to update.
        title: New title (optional).
        content: New content (optional).
        tags: New tags (replaces existing).
        contexts: New contexts (replaces existing).
        anti_contexts: New anti-contexts (replaces existing).
        confidence: New confidence level.
        source: New source type.
        source_notes: New source notes.
        config: Configuration to use.

    Returns:
        True if lesson was updated, False if not found.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    # Check if lesson exists
    existing = get_lesson(lesson_id, config)
    if existing is None:
        return False

    # Resolve tag aliases
    if tags is not None:
        tags = _resolve_tag_aliases(tags, config)

    with get_db(config) as conn:
        # Build update query
        updates = []
        params = []

        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if content is not None:
            updates.append("content = ?")
            params.append(content)
        if confidence is not None:
            updates.append("confidence = ?")
            params.append(confidence)
        if source is not None:
            updates.append("source = ?")
            params.append(source)
        if source_notes is not None:
            updates.append("source_notes = ?")
            params.append(source_notes)

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            query = f"UPDATE lessons SET {', '.join(updates)} WHERE id = ?"
            params.append(lesson_id)
            conn.execute(query, params)

        # Update tags if provided
        if tags is not None:
            conn.execute("DELETE FROM lesson_tags WHERE lesson_id = ?", (lesson_id,))
            if tags:
                conn.executemany(
                    "INSERT INTO lesson_tags (lesson_id, tag) VALUES (?, ?)",
                    [(lesson_id, tag) for tag in tags],
                )

        # Update contexts if provided
        if contexts is not None or anti_contexts is not None:
            conn.execute("DELETE FROM lesson_contexts WHERE lesson_id = ?", (lesson_id,))
            if contexts:
                conn.executemany(
                    "INSERT INTO lesson_contexts (lesson_id, context, applies) VALUES (?, ?, TRUE)",
                    [(lesson_id, ctx) for ctx in contexts],
                )
            if anti_contexts:
                conn.executemany(
                    "INSERT INTO lesson_contexts (lesson_id, context, applies) VALUES (?, ?, FALSE)",
                    [(lesson_id, ctx) for ctx in anti_contexts],
                )

        # Re-embed if title or content changed
        if title is not None or content is not None:
            new_title = title if title is not None else existing.title
            new_content = content if content is not None else existing.content
            embedding = embed_text(f"{new_title}\n\n{new_content}", config)
            embedding_blob = struct.pack(f"{len(embedding)}f", *embedding)

            conn.execute(
                "DELETE FROM lesson_embeddings WHERE lesson_id = ?",
                (lesson_id,),
            )
            conn.execute(
                "INSERT INTO lesson_embeddings (lesson_id, embedding) VALUES (?, ?)",
                (lesson_id, embedding_blob),
            )

        conn.commit()

    return True


def delete_lesson(lesson_id: str, config: Optional[Config] = None) -> bool:
    """Delete a lesson by ID.

    Args:
        lesson_id: The lesson ID to delete.
        config: Configuration to use.

    Returns:
        True if lesson was deleted, False if not found.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    with get_db(config) as conn:
        # Check if exists
        cursor = conn.execute(
            "SELECT id FROM lessons WHERE id = ?",
            (lesson_id,),
        )
        if cursor.fetchone() is None:
            return False

        # Delete (cascades to tags, contexts, edges via FK)
        conn.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
        # Manually delete embedding (vec0 tables don't support FK cascades)
        conn.execute("DELETE FROM lesson_embeddings WHERE lesson_id = ?", (lesson_id,))
        conn.commit()

    return True


# --- Search Operations ---


def recall(
    query: str,
    tags: Optional[list[str]] = None,
    contexts: Optional[list[str]] = None,
    confidence_min: Optional[str] = None,
    source: Optional[str] = None,
    limit: Optional[int] = None,
    strategy: str = "hybrid",
    config: Optional[Config] = None,
) -> list[SearchResult]:
    """Search for relevant lessons.

    Args:
        query: The search query.
        tags: Optional tag filter.
        contexts: Optional context filter.
        confidence_min: Minimum confidence level.
        source: Filter by source type.
        limit: Maximum results to return.
        strategy: Search strategy (hybrid, semantic, keyword).
        config: Configuration to use.

    Returns:
        List of search results sorted by relevance.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    if limit is None:
        limit = config.search.default_limit

    # Resolve tag aliases
    if tags:
        tags = _resolve_tag_aliases(tags, config)

    if strategy == "hybrid":
        return hybrid_search(
            query, limit, tags, contexts, confidence_min, source, config
        )
    elif strategy == "semantic":
        return vector_search(
            query, limit, tags, contexts, confidence_min, source, config
        )
    elif strategy == "keyword":
        return keyword_search(
            query, limit, tags, contexts, confidence_min, source, config
        )
    else:
        raise ValueError(f"Unknown search strategy: {strategy}")


# --- Graph Operations ---


def get_related(
    lesson_id: str,
    depth: int = 1,
    relations: Optional[list[str]] = None,
    config: Optional[Config] = None,
) -> list[Lesson]:
    """Get lessons related to the given lesson via graph edges.

    Args:
        lesson_id: The starting lesson ID.
        depth: Maximum traversal depth (default 1).
        relations: Optional filter for relation types.
        config: Configuration to use.

    Returns:
        List of related lessons.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    with get_db(config) as conn:
        # Build recursive CTE query
        relation_filter = ""
        params: list = [lesson_id, depth]

        if relations:
            placeholders = ",".join("?" * len(relations))
            relation_filter = f"AND e.relation IN ({placeholders})"
            params = [lesson_id] + relations + [depth]

        query = f"""
            WITH RECURSIVE related AS (
                SELECT to_id, 1 as depth
                FROM edges e
                WHERE from_id = ? {relation_filter}

                UNION

                SELECT e.to_id, r.depth + 1
                FROM edges e
                JOIN related r ON e.from_id = r.to_id
                WHERE r.depth < ? {relation_filter}
            )
            SELECT DISTINCT to_id FROM related
        """

        cursor = conn.execute(query, params)
        related_ids = [row["to_id"] for row in cursor.fetchall()]

    # Fetch full lessons
    return [get_lesson(rid, config) for rid in related_ids if get_lesson(rid, config)]


def link_lessons(
    from_id: str,
    to_id: str,
    relation: str,
    config: Optional[Config] = None,
) -> bool:
    """Create an edge between two lessons.

    Args:
        from_id: Source lesson ID.
        to_id: Target lesson ID.
        relation: Relationship type (e.g., "related_to", "derived_from").
        config: Configuration to use.

    Returns:
        True if edge was created, False if already exists.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    with get_db(config) as conn:
        try:
            conn.execute(
                "INSERT INTO edges (from_id, to_id, relation) VALUES (?, ?, ?)",
                (from_id, to_id, relation),
            )
            conn.commit()
            return True
        except Exception:
            # Edge already exists
            return False


def unlink_lessons(
    from_id: str,
    to_id: str,
    relation: Optional[str] = None,
    config: Optional[Config] = None,
) -> int:
    """Remove edge(s) between two lessons.

    Args:
        from_id: Source lesson ID.
        to_id: Target lesson ID.
        relation: Optional relation type (if None, removes all edges).
        config: Configuration to use.

    Returns:
        Number of edges removed.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    with get_db(config) as conn:
        if relation:
            cursor = conn.execute(
                "DELETE FROM edges WHERE from_id = ? AND to_id = ? AND relation = ?",
                (from_id, to_id, relation),
            )
        else:
            cursor = conn.execute(
                "DELETE FROM edges WHERE from_id = ? AND to_id = ?",
                (from_id, to_id),
            )
        conn.commit()
        return cursor.rowcount


# --- Reference Table Operations ---


def list_tags(with_counts: bool = False, config: Optional[Config] = None) -> list[Tag]:
    """List all tags in the database.

    Args:
        with_counts: Include usage counts.
        config: Configuration to use.

    Returns:
        List of tags.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    with get_db(config) as conn:
        if with_counts:
            cursor = conn.execute(
                """
                SELECT tag, COUNT(*) as count
                FROM lesson_tags
                GROUP BY tag
                ORDER BY count DESC, tag
                """
            )
            return [Tag(name=row["tag"], count=row["count"]) for row in cursor.fetchall()]
        else:
            cursor = conn.execute(
                "SELECT DISTINCT tag FROM lesson_tags ORDER BY tag"
            )
            return [Tag(name=row["tag"]) for row in cursor.fetchall()]


def list_sources(config: Optional[Config] = None) -> list[SourceType]:
    """List all source types.

    Args:
        config: Configuration to use.

    Returns:
        List of source types.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    with get_db(config) as conn:
        cursor = conn.execute(
            "SELECT name, description, typical_confidence FROM source_types ORDER BY name"
        )
        return [
            SourceType(
                name=row["name"],
                description=row["description"],
                typical_confidence=row["typical_confidence"],
            )
            for row in cursor.fetchall()
        ]


def list_confidence_levels(config: Optional[Config] = None) -> list[ConfidenceLevel]:
    """List all confidence levels.

    Args:
        config: Configuration to use.

    Returns:
        List of confidence levels sorted by ordinal.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    with get_db(config) as conn:
        cursor = conn.execute(
            "SELECT name, ordinal FROM confidence_levels ORDER BY ordinal"
        )
        return [
            ConfidenceLevel(name=row["name"], ordinal=row["ordinal"])
            for row in cursor.fetchall()
        ]


def add_source(
    name: str,
    description: Optional[str] = None,
    typical_confidence: Optional[str] = None,
    config: Optional[Config] = None,
) -> bool:
    """Add a new source type.

    Args:
        name: Source type name.
        description: Optional description.
        typical_confidence: Optional typical confidence level.
        config: Configuration to use.

    Returns:
        True if created, False if already exists.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    with get_db(config) as conn:
        try:
            conn.execute(
                "INSERT INTO source_types (name, description, typical_confidence) VALUES (?, ?, ?)",
                (name, description, typical_confidence),
            )
            conn.commit()
            return True
        except Exception:
            return False


def merge_tags(
    from_tag: str,
    to_tag: str,
    config: Optional[Config] = None,
) -> int:
    """Merge one tag into another.

    Args:
        from_tag: Tag to merge from (will be deleted).
        to_tag: Tag to merge into.
        config: Configuration to use.

    Returns:
        Number of lessons affected.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    with get_db(config) as conn:
        # Update all usages of from_tag to to_tag
        cursor = conn.execute(
            """
            UPDATE OR IGNORE lesson_tags
            SET tag = ?
            WHERE tag = ?
            """,
            (to_tag, from_tag),
        )
        affected = cursor.rowcount

        # Delete any remaining from_tag entries (duplicates after merge)
        conn.execute("DELETE FROM lesson_tags WHERE tag = ?", (from_tag,))

        conn.commit()
        return affected
