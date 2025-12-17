"""Core API for ai-lessons."""

import struct
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from ulid import ULID

from .config import Config, get_config
from .db import get_db, init_db
from .embeddings import embed_text
from .search import SearchResult, hybrid_search, keyword_search, vector_search

if TYPE_CHECKING:
    from .chunking import ChunkingConfig, ChunkingResult


@dataclass
class Lesson:
    """A lesson with all its metadata.

    Lessons are objective observations of causality: "If X, then Y happens."
    They do not include rationale (subjective value judgments belong to Rules).
    """
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
class Resource:
    """A resource (doc or script) with all its metadata."""
    id: str
    type: str  # 'doc' or 'script'
    title: str
    path: Optional[str] = None
    content: Optional[str] = None
    content_hash: Optional[str] = None
    source_ref: Optional[str] = None  # Git commit ref
    versions: list[str] = None
    tags: list[str] = None
    indexed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.versions is None:
            self.versions = []
        if self.tags is None:
            self.tags = []


@dataclass
class ResourceChunk:
    """A chunk of a resource document."""
    id: str
    resource_id: str
    chunk_index: int
    title: Optional[str] = None
    content: str = ""
    breadcrumb: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    token_count: Optional[int] = None
    summary: Optional[str] = None
    summary_generated_at: Optional[datetime] = None
    # Populated when fetching with parent info
    resource_title: Optional[str] = None
    resource_versions: list[str] = None
    resource_tags: list[str] = None

    def __post_init__(self):
        if self.resource_versions is None:
            self.resource_versions = []
        if self.resource_tags is None:
            self.resource_tags = []


@dataclass
class Rule:
    """A rule (prescriptive guidance) with all its metadata."""
    id: str
    title: str
    content: str
    rationale: str  # Required: why we want this outcome
    approved: bool = False
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    suggested_by: Optional[str] = None
    tags: list[str] = None
    linked_lessons: list[str] = None  # IDs of linked lessons
    linked_resources: list[str] = None  # IDs of linked resources
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.linked_lessons is None:
            self.linked_lessons = []
        if self.linked_resources is None:
            self.linked_resources = []


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


# --- Resource Operations (v2) ---


def _get_git_ref(path: str) -> Optional[str]:
    """Get the current git commit ref for a file path."""
    import subprocess
    from pathlib import Path

    try:
        # Check if path is in a git repo
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(path).parent,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()[:12]  # Short hash
    except Exception:
        pass
    return None


def _compute_content_hash(content: str) -> str:
    """Compute a hash of content for change detection."""
    import hashlib
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _store_chunks(
    conn,
    resource_id: str,
    content: str,
    path: Optional[str],
    chunking_config: Optional["ChunkingConfig"],
    config: Config,
) -> int:
    """Chunk content and store chunks with embeddings.

    Args:
        conn: Database connection (within transaction).
        resource_id: ID of the parent resource.
        content: Document content to chunk.
        path: Source file path (for context).
        chunking_config: Chunking configuration.
        config: Application config.

    Returns:
        Number of chunks stored.
    """
    from .chunking import ChunkingConfig, chunk_document

    # Use default config if none provided
    if chunking_config is None:
        chunking_config = ChunkingConfig()

    # Chunk the document
    result = chunk_document(content, chunking_config, source_path=path)

    # Store each chunk
    for chunk in result.chunks:
        chunk_id = _generate_id()

        # Insert chunk
        conn.execute(
            """
            INSERT INTO resource_chunks
                (id, resource_id, chunk_index, title, content, breadcrumb, start_line, end_line, token_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk_id,
                resource_id,
                chunk.index,
                chunk.title,
                chunk.content,
                chunk.breadcrumb,
                chunk.start_line,
                chunk.end_line,
                chunk.token_count,
            ),
        )

        # Generate and store chunk embedding
        # Use breadcrumb + title + content for better context
        embed_text_parts = []
        if chunk.breadcrumb:
            embed_text_parts.append(chunk.breadcrumb)
        if chunk.title and chunk.title not in (chunk.breadcrumb or ""):
            embed_text_parts.append(chunk.title)
        embed_text_parts.append(chunk.content)
        embed_input = "\n\n".join(embed_text_parts)

        embedding = embed_text(embed_input, config)
        embedding_blob = struct.pack(f"{len(embedding)}f", *embedding)

        conn.execute(
            "INSERT INTO chunk_embeddings (chunk_id, embedding) VALUES (?, ?)",
            (chunk_id, embedding_blob),
        )

    return len(result.chunks)


def add_resource(
    type: str,
    title: str,
    path: Optional[str] = None,
    content: Optional[str] = None,
    versions: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
    chunking_config: Optional["ChunkingConfig"] = None,
    config: Optional[Config] = None,
) -> str:
    """Add a new resource (doc or script) to the database.

    Args:
        type: Resource type ('doc' or 'script').
        title: Resource title.
        path: Filesystem path (required for scripts).
        content: Content (required for docs if no path).
        versions: List of versions this resource applies to.
        tags: Optional list of tags.
        chunking_config: Configuration for document chunking (docs only).
        config: Configuration to use.

    Returns:
        The generated resource ID.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    if type not in ('doc', 'script'):
        raise ValueError(f"Invalid resource type: {type}")

    if type == 'script' and not path:
        raise ValueError("Scripts require a path")

    # Read content from path if not provided
    if content is None and path:
        from pathlib import Path as PathLib
        content = PathLib(path).read_text()

    if not content:
        raise ValueError("Content is required")

    # Default to 'unversioned' if no versions specified
    if not versions:
        versions = ['unversioned']

    # Resolve tag aliases
    if tags:
        tags = _resolve_tag_aliases(tags, config)

    # Generate ID and metadata
    resource_id = _generate_id()
    content_hash = _compute_content_hash(content)
    source_ref = _get_git_ref(path) if path else None

    # Generate embedding for the whole resource
    embedding = embed_text(f"{title}\n\n{content}", config)
    embedding_blob = struct.pack(f"{len(embedding)}f", *embedding)

    with get_db(config) as conn:
        # Insert resource
        conn.execute(
            """
            INSERT INTO resources (id, type, title, path, content, content_hash, source_ref, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (resource_id, type, title, path, content, content_hash, source_ref),
        )

        # Insert versions
        conn.executemany(
            "INSERT INTO resource_versions (resource_id, version) VALUES (?, ?)",
            [(resource_id, v) for v in versions],
        )

        # Insert tags
        if tags:
            conn.executemany(
                "INSERT INTO resource_tags (resource_id, tag) VALUES (?, ?)",
                [(resource_id, tag) for tag in tags],
            )

        # Insert embedding
        conn.execute(
            "INSERT INTO resource_embeddings (resource_id, embedding) VALUES (?, ?)",
            (resource_id, embedding_blob),
        )

        # Chunk and store chunks for docs
        if type == 'doc':
            _store_chunks(conn, resource_id, content, path, chunking_config, config)

        conn.commit()

    return resource_id


def get_resource(resource_id: str, config: Optional[Config] = None) -> Optional[Resource]:
    """Get a resource by ID.

    For scripts, checks if content is stale and re-reads from disk if needed.

    Args:
        resource_id: The resource ID.
        config: Configuration to use.

    Returns:
        The resource if found, None otherwise.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    with get_db(config) as conn:
        # Get resource
        cursor = conn.execute(
            "SELECT * FROM resources WHERE id = ?",
            (resource_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        # Get versions
        cursor = conn.execute(
            "SELECT version FROM resource_versions WHERE resource_id = ?",
            (resource_id,),
        )
        versions = [r["version"] for r in cursor.fetchall()]

        # Get tags
        cursor = conn.execute(
            "SELECT tag FROM resource_tags WHERE resource_id = ?",
            (resource_id,),
        )
        tags = [r["tag"] for r in cursor.fetchall()]

        content = row["content"]

        # For scripts, check if file has changed
        if row["type"] == "script" and row["path"]:
            from pathlib import Path as PathLib
            path = PathLib(row["path"])
            if path.exists():
                current_content = path.read_text()
                current_hash = _compute_content_hash(current_content)
                if current_hash != row["content_hash"]:
                    # Content has changed, update cache
                    content = current_content
                    _refresh_resource_content(conn, resource_id, content, config)

        return Resource(
            id=row["id"],
            type=row["type"],
            title=row["title"],
            path=row["path"],
            content=content,
            content_hash=row["content_hash"],
            source_ref=row["source_ref"],
            versions=versions,
            tags=tags,
            indexed_at=row["indexed_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def _refresh_resource_content(
    conn, resource_id: str, content: str, config: Config
) -> None:
    """Refresh a resource's cached content and embedding."""
    content_hash = _compute_content_hash(content)

    # Get title for embedding
    cursor = conn.execute(
        "SELECT title FROM resources WHERE id = ?",
        (resource_id,),
    )
    row = cursor.fetchone()
    title = row["title"] if row else ""

    # Update content and hash
    conn.execute(
        """
        UPDATE resources
        SET content = ?, content_hash = ?, indexed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (content, content_hash, resource_id),
    )

    # Re-generate embedding
    embedding = embed_text(f"{title}\n\n{content}", config)
    embedding_blob = struct.pack(f"{len(embedding)}f", *embedding)

    conn.execute(
        "DELETE FROM resource_embeddings WHERE resource_id = ?",
        (resource_id,),
    )
    conn.execute(
        "INSERT INTO resource_embeddings (resource_id, embedding) VALUES (?, ?)",
        (resource_id, embedding_blob),
    )

    conn.commit()


def delete_resource(resource_id: str, config: Optional[Config] = None) -> bool:
    """Delete a resource by ID.

    Args:
        resource_id: The resource ID to delete.
        config: Configuration to use.

    Returns:
        True if resource was deleted, False if not found.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    with get_db(config) as conn:
        # Check if exists
        cursor = conn.execute(
            "SELECT id FROM resources WHERE id = ?",
            (resource_id,),
        )
        if cursor.fetchone() is None:
            return False

        # Delete (cascades to versions, tags via FK)
        conn.execute("DELETE FROM resources WHERE id = ?", (resource_id,))
        # Manually delete embedding (vec0 tables don't support FK cascades)
        conn.execute("DELETE FROM resource_embeddings WHERE resource_id = ?", (resource_id,))
        conn.commit()

    return True


def refresh_resource(resource_id: str, config: Optional[Config] = None) -> bool:
    """Refresh a resource's content from its source path.

    Args:
        resource_id: The resource ID to refresh.
        config: Configuration to use.

    Returns:
        True if refreshed, False if not found or no path.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    with get_db(config) as conn:
        cursor = conn.execute(
            "SELECT path FROM resources WHERE id = ?",
            (resource_id,),
        )
        row = cursor.fetchone()
        if row is None or not row["path"]:
            return False

        from pathlib import Path as PathLib
        path = PathLib(row["path"])
        if not path.exists():
            return False

        content = path.read_text()
        _refresh_resource_content(conn, resource_id, content, config)

    return True


def get_chunk(
    chunk_id: str,
    include_parent: bool = True,
    config: Optional[Config] = None,
) -> Optional[ResourceChunk]:
    """Get a chunk by ID.

    Args:
        chunk_id: The chunk ID.
        include_parent: Include parent resource metadata (title, versions, tags).
        config: Configuration to use.

    Returns:
        The chunk if found, None otherwise.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    with get_db(config) as conn:
        # Get chunk
        cursor = conn.execute(
            "SELECT * FROM resource_chunks WHERE id = ?",
            (chunk_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        resource_title = None
        resource_versions = []
        resource_tags = []

        if include_parent:
            # Get parent resource info
            cursor = conn.execute(
                "SELECT title FROM resources WHERE id = ?",
                (row["resource_id"],),
            )
            parent = cursor.fetchone()
            if parent:
                resource_title = parent["title"]

            # Get versions
            cursor = conn.execute(
                "SELECT version FROM resource_versions WHERE resource_id = ?",
                (row["resource_id"],),
            )
            resource_versions = [r["version"] for r in cursor.fetchall()]

            # Get tags
            cursor = conn.execute(
                "SELECT tag FROM resource_tags WHERE resource_id = ?",
                (row["resource_id"],),
            )
            resource_tags = [r["tag"] for r in cursor.fetchall()]

        return ResourceChunk(
            id=row["id"],
            resource_id=row["resource_id"],
            chunk_index=row["chunk_index"],
            title=row["title"],
            content=row["content"],
            breadcrumb=row["breadcrumb"],
            start_line=row["start_line"],
            end_line=row["end_line"],
            token_count=row["token_count"],
            summary=row["summary"],
            summary_generated_at=row["summary_generated_at"],
            resource_title=resource_title,
            resource_versions=resource_versions,
            resource_tags=resource_tags,
        )


def list_chunks(
    resource_id: str,
    config: Optional[Config] = None,
) -> list[ResourceChunk]:
    """List all chunks for a resource.

    Args:
        resource_id: The resource ID.
        config: Configuration to use.

    Returns:
        List of chunks ordered by chunk_index.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    with get_db(config) as conn:
        # Get parent resource info first
        cursor = conn.execute(
            "SELECT title FROM resources WHERE id = ?",
            (resource_id,),
        )
        parent = cursor.fetchone()
        if parent is None:
            return []

        resource_title = parent["title"]

        # Get versions
        cursor = conn.execute(
            "SELECT version FROM resource_versions WHERE resource_id = ?",
            (resource_id,),
        )
        resource_versions = [r["version"] for r in cursor.fetchall()]

        # Get tags
        cursor = conn.execute(
            "SELECT tag FROM resource_tags WHERE resource_id = ?",
            (resource_id,),
        )
        resource_tags = [r["tag"] for r in cursor.fetchall()]

        # Get all chunks
        cursor = conn.execute(
            "SELECT * FROM resource_chunks WHERE resource_id = ? ORDER BY chunk_index",
            (resource_id,),
        )

        return [
            ResourceChunk(
                id=row["id"],
                resource_id=row["resource_id"],
                chunk_index=row["chunk_index"],
                title=row["title"],
                content=row["content"],
                breadcrumb=row["breadcrumb"],
                start_line=row["start_line"],
                end_line=row["end_line"],
                token_count=row["token_count"],
                summary=row["summary"],
                summary_generated_at=row["summary_generated_at"],
                resource_title=resource_title,
                resource_versions=resource_versions,
                resource_tags=resource_tags,
            )
            for row in cursor.fetchall()
        ]


def list_resources(
    pattern: Optional[str] = None,
    resource_type: Optional[str] = None,
    version: Optional[str] = None,
    tags: Optional[list[str]] = None,
    config: Optional[Config] = None,
) -> list[Resource]:
    """List resources with optional filtering.

    Args:
        pattern: Case-insensitive substring match on title.
        resource_type: Filter by type ('doc' or 'script').
        version: Filter by version.
        tags: Filter by tags (matches any).
        config: Configuration to use.

    Returns:
        List of matching resources.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    # Resolve tag aliases
    if tags:
        tags = _resolve_tag_aliases(tags, config)

    with get_db(config) as conn:
        # Build query with filters
        query = "SELECT DISTINCT r.id FROM resources r"
        joins = []
        conditions = []
        params = []

        if version:
            joins.append("JOIN resource_versions rv ON r.id = rv.resource_id")
            conditions.append("rv.version = ?")
            params.append(version)

        if tags:
            joins.append("JOIN resource_tags rt ON r.id = rt.resource_id")
            placeholders = ",".join("?" * len(tags))
            conditions.append(f"rt.tag IN ({placeholders})")
            params.extend(tags)

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
        query += " ORDER BY r.title"

        cursor = conn.execute(query, params)
        resource_ids = [row["id"] for row in cursor.fetchall()]

    # Fetch full resources
    return [get_resource(rid, config) for rid in resource_ids if get_resource(rid, config)]


# --- Rule Operations (v2) ---


def suggest_rule(
    title: str,
    content: str,
    rationale: str,
    tags: Optional[list[str]] = None,
    linked_lessons: Optional[list[str]] = None,
    linked_resources: Optional[list[str]] = None,
    suggested_by: Optional[str] = None,
    config: Optional[Config] = None,
) -> str:
    """Suggest a new rule for approval.

    Rules are created with approved=False and must be approved by a human.

    Args:
        title: Rule title.
        content: Rule content (the prescription).
        rationale: Why this rule exists (required).
        tags: Optional list of tags.
        linked_lessons: Optional list of lesson IDs this rule relates to.
        linked_resources: Optional list of resource IDs this rule relates to.
        suggested_by: Optional identifier of who/what suggested this rule.
        config: Configuration to use.

    Returns:
        The generated rule ID.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    if not rationale:
        raise ValueError("Rationale is required for rules")

    # Resolve tag aliases
    if tags:
        tags = _resolve_tag_aliases(tags, config)

    rule_id = _generate_id()

    with get_db(config) as conn:
        # Insert rule (approved=False by default)
        conn.execute(
            """
            INSERT INTO rules (id, title, content, rationale, suggested_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (rule_id, title, content, rationale, suggested_by),
        )

        # Insert tags
        if tags:
            conn.executemany(
                "INSERT INTO rule_tags (rule_id, tag) VALUES (?, ?)",
                [(rule_id, tag) for tag in tags],
            )

        # Insert links to lessons
        if linked_lessons:
            conn.executemany(
                "INSERT INTO rule_links (rule_id, target_id, target_type) VALUES (?, ?, 'lesson')",
                [(rule_id, lid) for lid in linked_lessons],
            )

        # Insert links to resources
        if linked_resources:
            conn.executemany(
                "INSERT INTO rule_links (rule_id, target_id, target_type) VALUES (?, ?, 'resource')",
                [(rule_id, rid) for rid in linked_resources],
            )

        conn.commit()

    return rule_id


def get_rule(rule_id: str, config: Optional[Config] = None) -> Optional[Rule]:
    """Get a rule by ID.

    Args:
        rule_id: The rule ID.
        config: Configuration to use.

    Returns:
        The rule if found, None otherwise.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    with get_db(config) as conn:
        # Get rule
        cursor = conn.execute(
            "SELECT * FROM rules WHERE id = ?",
            (rule_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        # Get tags
        cursor = conn.execute(
            "SELECT tag FROM rule_tags WHERE rule_id = ?",
            (rule_id,),
        )
        tags = [r["tag"] for r in cursor.fetchall()]

        # Get linked lessons
        cursor = conn.execute(
            "SELECT target_id FROM rule_links WHERE rule_id = ? AND target_type = 'lesson'",
            (rule_id,),
        )
        linked_lessons = [r["target_id"] for r in cursor.fetchall()]

        # Get linked resources
        cursor = conn.execute(
            "SELECT target_id FROM rule_links WHERE rule_id = ? AND target_type = 'resource'",
            (rule_id,),
        )
        linked_resources = [r["target_id"] for r in cursor.fetchall()]

        return Rule(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            rationale=row["rationale"],
            approved=bool(row["approved"]),
            approved_at=row["approved_at"],
            approved_by=row["approved_by"],
            suggested_by=row["suggested_by"],
            tags=tags,
            linked_lessons=linked_lessons,
            linked_resources=linked_resources,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def approve_rule(
    rule_id: str,
    approved_by: Optional[str] = None,
    config: Optional[Config] = None,
) -> bool:
    """Approve a rule, making it visible in search results.

    Args:
        rule_id: The rule ID to approve.
        approved_by: Optional identifier of who approved.
        config: Configuration to use.

    Returns:
        True if approved, False if not found.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    with get_db(config) as conn:
        cursor = conn.execute(
            """
            UPDATE rules
            SET approved = 1, approved_at = CURRENT_TIMESTAMP, approved_by = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (approved_by, rule_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def reject_rule(rule_id: str, config: Optional[Config] = None) -> bool:
    """Reject (delete) a suggested rule.

    Args:
        rule_id: The rule ID to reject.
        config: Configuration to use.

    Returns:
        True if deleted, False if not found.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    with get_db(config) as conn:
        cursor = conn.execute(
            "DELETE FROM rules WHERE id = ?",
            (rule_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


def list_pending_rules(config: Optional[Config] = None) -> list[Rule]:
    """List all rules pending approval.

    Args:
        config: Configuration to use.

    Returns:
        List of unapproved rules.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    with get_db(config) as conn:
        cursor = conn.execute(
            "SELECT id FROM rules WHERE approved = 0 ORDER BY created_at DESC"
        )
        rule_ids = [row["id"] for row in cursor.fetchall()]

    return [get_rule(rid, config) for rid in rule_ids if get_rule(rid, config)]


def link_to_rule(
    rule_id: str,
    target_id: str,
    target_type: str,
    config: Optional[Config] = None,
) -> bool:
    """Link a lesson or resource to a rule.

    Args:
        rule_id: The rule ID.
        target_id: The lesson or resource ID to link.
        target_type: 'lesson' or 'resource'.
        config: Configuration to use.

    Returns:
        True if linked, False if already exists.
    """
    if config is None:
        config = get_config()

    ensure_initialized(config)

    if target_type not in ('lesson', 'resource'):
        raise ValueError(f"Invalid target type: {target_type}")

    with get_db(config) as conn:
        try:
            conn.execute(
                "INSERT INTO rule_links (rule_id, target_id, target_type) VALUES (?, ?, ?)",
                (rule_id, target_id, target_type),
            )
            conn.commit()
            return True
        except Exception:
            return False
