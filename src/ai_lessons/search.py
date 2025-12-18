"""Search functionality for ai-lessons."""

from __future__ import annotations

import math
import re
import sqlite3
from dataclasses import dataclass
from typing import Optional

from .config import Config, get_config
from .db import get_db
from .embeddings import embed_text


from dataclasses import field


# --- Scoring Constants ---
#
# These constants were tuned based on empirical testing to provide good
# differentiation between relevant and irrelevant results.

# Keyword scoring weights
# Rationale: Title matches are most indicative (3x), tags are explicit metadata (2.5x),
# content matches are baseline (1x)
KEYWORD_TITLE_WEIGHT = 3.0
KEYWORD_CONTENT_WEIGHT = 1.0
KEYWORD_TAG_WEIGHT = 2.5

# Semantic scoring sigmoid parameters
# Rationale: These values map cosine distances to intuitive relevance scores:
# - STEEPNESS=6.0: Creates sharp distinction around the center point
# - CENTER=1.15: Distance < 1.0 → score > 0.7 (relevant), distance > 1.3 → score < 0.3
SIGMOID_STEEPNESS = 6.0
SIGMOID_CENTER = 1.15

# Hybrid search weights
# Rationale: Semantic similarity is primary (85%), keywords boost exact matches (15%)
HYBRID_SEMANTIC_WEIGHT = 0.85
HYBRID_KEYWORD_WEIGHT = 0.15

# Link boosting parameters
# Rationale: LINK_BOOST_FACTOR=0.25 gives 25% boost for strongly related results,
# MIN_LINKED_SCORE=0.65 ensures only reasonably relevant links boost scores
LINK_BOOST_FACTOR = 0.25
MIN_LINKED_SCORE = 0.65
MATCH_BONUS = 0.1

# Chunk scoring
# Rationale: Small boost (3%) for chunk matches to prefer specific content over general
CHUNK_SPECIFICITY_MULT = 1.03

# Rule default score
# Rationale: Neutral score (0.5) for tag-matched rules without keyword hits
RULE_DEFAULT_SCORE = 0.5


@dataclass
class SearchResult:
    """Base class for all search results."""
    id: str
    title: str
    content: str
    score: float
    result_type: str
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not (0.0 <= self.score <= 1.0):
            raise ValueError(f"Score must be between 0.0 and 1.0, got {self.score}")


@dataclass
class LessonResult(SearchResult):
    """Search result for a lesson."""
    confidence: Optional[str] = None
    source: Optional[str] = None
    source_notes: Optional[str] = None
    contexts: list[str] = field(default_factory=list)
    anti_contexts: list[str] = field(default_factory=list)

    def __post_init__(self):
        super().__post_init__()
        self.result_type = "lesson"


@dataclass
class ResourceResult(SearchResult):
    """Search result for a resource (doc or script)."""
    resource_type: Optional[str] = None  # 'doc' or 'script'
    versions: list[str] = field(default_factory=list)
    path: Optional[str] = None

    def __post_init__(self):
        super().__post_init__()
        self.result_type = "resource"


@dataclass
class ChunkResult(SearchResult):
    """Search result for a document chunk."""
    chunk_index: Optional[int] = None
    breadcrumb: Optional[str] = None
    resource_id: Optional[str] = None
    resource_title: Optional[str] = None
    versions: list[str] = field(default_factory=list)
    summary: Optional[str] = None
    sections: list[str] = field(default_factory=list)
    # Parent resource metadata
    resource_type: Optional[str] = None  # 'doc' or 'script'
    path: Optional[str] = None

    def __post_init__(self):
        super().__post_init__()
        self.result_type = "chunk"


@dataclass
class RuleResult(SearchResult):
    """Search result for a rule."""
    rationale: Optional[str] = None
    approved: Optional[bool] = None

    def __post_init__(self):
        super().__post_init__()
        self.result_type = "rule"


@dataclass
class GroupedResourceResult:
    """A resource with its matching chunks for grouped search display."""
    resource_id: str
    resource_title: str
    resource_type: str  # 'doc' or 'script'
    versions: list[str]
    tags: list[str]
    path: Optional[str]
    best_score: float  # Highest chunk score (or resource-level score if no chunks)
    chunks: list[ChunkResult]  # Matching chunks, sorted by score descending

    @property
    def chunk_count(self) -> int:
        """Number of matching chunks."""
        return len(self.chunks)


# --- Helper Functions ---


def _fetch_lesson_properties(
    conn: sqlite3.Connection,
    lesson_id: str,
) -> tuple[list[str], list[str], list[str]]:
    """Fetch tags, contexts, and anti_contexts for a lesson.

    Args:
        conn: Database connection.
        lesson_id: The lesson ID.

    Returns:
        Tuple of (tags, contexts, anti_contexts).
    """
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

    return tags, contexts, anti_contexts


def _build_lesson_filter_clauses(
    tag_filter: Optional[list[str]] = None,
    context_filter: Optional[list[str]] = None,
    confidence_min: Optional[str] = None,
    source: Optional[str] = None,
) -> tuple[list[str], list]:
    """Build SQL WHERE clauses for lesson filtering.

    Args:
        tag_filter: Filter by tags (ANY match).
        context_filter: Filter by contexts.
        confidence_min: Minimum confidence level.
        source: Filter by source type.

    Returns:
        Tuple of (list of SQL clause strings, list of parameters).
        Clauses do NOT include "WHERE" or "AND" prefix.
    """
    clauses = []
    params: list = []

    if tag_filter:
        placeholders = ",".join("?" * len(tag_filter))
        clauses.append(f"""
            l.id IN (
                SELECT lesson_id FROM lesson_tags
                WHERE tag IN ({placeholders})
            )
        """)
        params.extend(tag_filter)

    if context_filter:
        placeholders = ",".join("?" * len(context_filter))
        clauses.append(f"""
            l.id IN (
                SELECT lesson_id FROM lesson_contexts
                WHERE context IN ({placeholders}) AND applies = TRUE
            )
        """)
        params.extend(context_filter)

    if confidence_min:
        clauses.append("""
            l.confidence IN (
                SELECT name FROM confidence_levels
                WHERE ordinal >= (SELECT ordinal FROM confidence_levels WHERE name = ?)
            )
        """)
        params.append(confidence_min)

    if source:
        clauses.append("l.source = ?")
        params.append(source)

    return clauses, params


def _build_resource_filter_clauses(
    tag_filter: Optional[list[str]] = None,
    resource_type: Optional[str] = None,
    versions: Optional[list[str]] = None,
) -> tuple[list[str], list]:
    """Build SQL WHERE clauses for resource filtering.

    Args:
        tag_filter: Filter by tags (ANY match).
        resource_type: Filter by type ('doc' or 'script').
        versions: Filter by versions.

    Returns:
        Tuple of (list of SQL clause strings, list of parameters).
    """
    clauses = []
    params: list = []

    if tag_filter:
        placeholders = ",".join("?" * len(tag_filter))
        clauses.append(f"""
            r.id IN (
                SELECT resource_id FROM resource_tags
                WHERE tag IN ({placeholders})
            )
        """)
        params.extend(tag_filter)

    if resource_type:
        clauses.append("r.type = ?")
        params.append(resource_type)

    if versions:
        placeholders = ",".join("?" * len(versions))
        clauses.append(f"""
            r.id IN (
                SELECT resource_id FROM resource_versions
                WHERE version IN ({placeholders})
            )
        """)
        params.extend(versions)

    return clauses, params


def _fetch_resource_metadata(
    conn: sqlite3.Connection,
    resource_id: str,
) -> tuple[set[str], list[str]]:
    """Fetch versions and tags for a resource.

    Args:
        conn: Database connection.
        resource_id: The resource ID.

    Returns:
        Tuple of (versions_set, tags_list).
    """
    cursor = conn.execute(
        "SELECT version FROM resource_versions WHERE resource_id = ?",
        (resource_id,),
    )
    versions = {r["version"] for r in cursor.fetchall()}

    cursor = conn.execute(
        "SELECT tag FROM resource_tags WHERE resource_id = ?",
        (resource_id,),
    )
    tags = [r["tag"] for r in cursor.fetchall()]

    return versions, tags


def _normalize_text(text: str) -> str:
    """Normalize text for keyword matching."""
    # Lowercase, collapse whitespace
    text = text.lower()
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _keyword_score(
    query: str,
    title: str,
    content: str,
    tags: Optional[list[str]] = None,
) -> float:
    """Calculate keyword relevance score.

    Weights:
    - Title matches: 3.0
    - Tag matches: 2.5 (if tags provided)
    - Content matches: 1.0

    Args:
        query: Search query
        title: Result title
        content: Result content (first 500 chars used for efficiency)
        tags: Result tags (optional)

    Returns:
        Keyword score normalized by query term count
    """
    query_terms = set(_normalize_text(query).split())
    if not query_terms:
        return 0.0

    title_norm = _normalize_text(title)
    content_norm = _normalize_text(content[:500])
    tags_lower = {t.lower() for t in tags} if tags else set()

    score = 0.0
    for term in query_terms:
        if term in title_norm:
            score += KEYWORD_TITLE_WEIGHT
        if tags_lower and term in tags_lower:
            score += KEYWORD_TAG_WEIGHT
        if term in content_norm:
            score += KEYWORD_CONTENT_WEIGHT

    return score / len(query_terms)


# --- v6: Improved Scoring Functions ---


def _distance_to_score(distance: float, steepness: float = SIGMOID_STEEPNESS, center: float = SIGMOID_CENTER) -> float:
    """Convert cosine distance to score using sigmoid function.

    This provides much better differentiation than 1/(1+d):
    - Distances < 1.0: scores 0.7-0.95 (highly relevant)
    - Distances 1.0-1.2: scores 0.4-0.7 (moderately relevant)
    - Distances > 1.3: scores < 0.3 (less relevant)

    Args:
        distance: Cosine distance (0-2, lower is better)
        steepness: Steepness of sigmoid curve (default 6.0)
        center: Distance value that maps to 0.5 score (default 1.15)

    Returns:
        Score between 0 and 1
    """
    return 1.0 / (1.0 + math.exp(steepness * (distance - center)))


def _compute_resource_score(
    distance: float,
    title: str,
    content: str,
    tags: list[str],
    query: str,
    version_score: float = 1.0,
    chunk_boost: bool = False,
) -> float:
    """Compute score for a resource/chunk result.

    Combines:
    - Sigmoid-based distance score
    - Keyword/tag boost
    - Version score multiplier
    - Optional chunk specificity boost

    Args:
        distance: Cosine distance
        title: Resource title
        content: Resource content
        tags: Resource tags
        query: Search query
        version_score: Version match score (0-1)
        chunk_boost: Apply chunk specificity boost

    Returns:
        Final score (0-1)
    """
    # Base score from distance
    base = _distance_to_score(distance)

    # Keyword boost (scaled to max 0.15)
    keyword_raw = _keyword_score(query, title, content, tags)
    keyword_boost = min(0.15, keyword_raw * 0.025)

    # Chunk specificity boost
    specificity_mult = CHUNK_SPECIFICITY_MULT if chunk_boost else 1.0

    # Combine
    score = (base + keyword_boost) * version_score * specificity_mult
    return min(1.0, score)


def vector_search(
    query: str,
    limit: int = 10,
    tag_filter: Optional[list[str]] = None,
    context_filter: Optional[list[str]] = None,
    confidence_min: Optional[str] = None,
    source_filter: Optional[str] = None,
    config: Optional[Config] = None,
) -> list[SearchResult]:
    """Search lessons using vector similarity only."""
    if config is None:
        config = get_config()

    # Generate query embedding
    query_embedding = embed_text(query, config)

    with get_db(config) as conn:
        # Build the query with filters
        results = _execute_vector_search(
            conn,
            query_embedding,
            limit,
            tag_filter,
            context_filter,
            confidence_min,
            source_filter,
        )

        return [_row_to_result(conn, row, row["distance"], query) for row in results]


def keyword_search(
    query: str,
    limit: int = 10,
    tag_filter: Optional[list[str]] = None,
    context_filter: Optional[list[str]] = None,
    confidence_min: Optional[str] = None,
    source_filter: Optional[str] = None,
    config: Optional[Config] = None,
) -> list[SearchResult]:
    """Search lessons using keyword matching only."""
    if config is None:
        config = get_config()

    with get_db(config) as conn:
        # Get all lessons (filtered)
        lessons = _get_filtered_lessons(
            conn,
            tag_filter,
            context_filter,
            confidence_min,
            source_filter,
        )

        # Score each lesson
        scored = []
        for row in lessons:
            score = _keyword_score(query, row["title"], row["content"])
            if score > 0:
                # Cap at 1.0 for consistent result scoring
                scored.append((row, min(1.0, score)))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)

        # Return top results
        return [_row_to_result(conn, row, score) for row, score in scored[:limit]]


def hybrid_search(
    query: str,
    limit: int = 10,
    tag_filter: Optional[list[str]] = None,
    context_filter: Optional[list[str]] = None,
    confidence_min: Optional[str] = None,
    source_filter: Optional[str] = None,
    config: Optional[Config] = None,
) -> list[SearchResult]:
    """Search lessons using hybrid (semantic + keyword) ranking.

    Uses improved sigmoid-based scoring with keyword boosting.
    The vector_search already includes keyword boosting in the score,
    so we primarily use its results but may include additional results
    from pure keyword matching.
    """
    if config is None:
        config = get_config()

    # Get results from vector search (already uses improved scoring)
    fetch_limit = limit * 2
    vector_results = vector_search(
        query, fetch_limit, tag_filter, context_filter,
        confidence_min, source_filter, config
    )

    # Get keyword-only results for items that might be missed by vector search
    keyword_results = keyword_search(
        query, fetch_limit, tag_filter, context_filter,
        confidence_min, source_filter, config
    )

    # Build result map - vector results take priority since they have better scores
    result_map = {r.id: r for r in vector_results}

    # Add keyword results not in vector results (with scaled scores)
    # Keyword-only matches are less reliable, so scale their scores down
    for kr in keyword_results:
        if kr.id not in result_map:
            # Scale keyword score to 0-0.5 range since it lacks semantic signal
            kr.score = min(0.5, kr.score * 0.1)
            result_map[kr.id] = kr

    # Sort by score
    results = sorted(result_map.values(), key=lambda x: x.score, reverse=True)
    return results[:limit]


def _execute_vector_search(
    conn: sqlite3.Connection,
    query_embedding: list[float],
    limit: int,
    tag_filter: Optional[list[str]],
    context_filter: Optional[list[str]],
    confidence_min: Optional[str],
    source_filter: Optional[str],
) -> list[sqlite3.Row]:
    """Execute a vector search with optional filters."""
    import struct

    # Serialize embedding for sqlite-vec
    embedding_blob = struct.pack(f"{len(query_embedding)}f", *query_embedding)

    # Build base query
    query = """
        SELECT l.*, le.distance
        FROM lessons l
        JOIN lesson_embeddings le ON l.id = le.lesson_id
        WHERE le.embedding MATCH ?
        AND k = ?
    """
    params: list = [embedding_blob, limit * 2]  # Fetch extra for filtering

    # Add filters using helper
    filter_clauses, filter_params = _build_lesson_filter_clauses(
        tag_filter=tag_filter,
        context_filter=context_filter,
        confidence_min=confidence_min,
        source=source_filter,
    )
    if filter_clauses:
        query += " AND " + " AND ".join(filter_clauses)
        params.extend(filter_params)

    query += " ORDER BY le.distance LIMIT ?"
    params.append(limit)

    cursor = conn.execute(query, params)
    return cursor.fetchall()


def _get_filtered_lessons(
    conn: sqlite3.Connection,
    tag_filter: Optional[list[str]],
    context_filter: Optional[list[str]],
    confidence_min: Optional[str],
    source_filter: Optional[str],
) -> list[sqlite3.Row]:
    """Get lessons with optional filters applied."""
    query = "SELECT * FROM lessons l WHERE 1=1"

    # Build filters using helper
    filter_clauses, params = _build_lesson_filter_clauses(
        tag_filter=tag_filter,
        context_filter=context_filter,
        confidence_min=confidence_min,
        source=source_filter,
    )
    if filter_clauses:
        query += " AND " + " AND ".join(filter_clauses)

    cursor = conn.execute(query, params)
    return cursor.fetchall()


def _row_to_result(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    score_or_distance: float,
    query: str = "",
) -> LessonResult:
    """Convert a database row to a LessonResult.

    Args:
        conn: Database connection.
        row: Database row.
        score_or_distance: Either a precomputed score (from keyword search)
            or a distance value (from vector search). If query is provided,
            this is treated as distance and converted using sigmoid scoring.
        query: Search query (if provided, enables improved scoring).
    """
    lesson_id = row["id"]

    # Get tags, contexts, and anti_contexts
    tags, contexts, anti_contexts = _fetch_lesson_properties(conn, lesson_id)

    # Compute score
    if query:
        # Use improved scoring: sigmoid distance + keyword boost
        base_score = _distance_to_score(score_or_distance)
        keyword_raw = _keyword_score(query, row["title"], row["content"], tags)
        keyword_boost = min(0.15, keyword_raw * 0.025)
        final_score = min(1.0, base_score + keyword_boost)
    else:
        # Use precomputed score (from keyword search)
        final_score = score_or_distance

    return LessonResult(
        id=lesson_id,
        title=row["title"],
        content=row["content"],
        score=final_score,
        result_type="lesson",
        tags=tags,
        confidence=row["confidence"],
        source=row["source"],
        source_notes=row["source_notes"],
        contexts=contexts,
        anti_contexts=anti_contexts,
    )


# --- v2: Version Matching ---


def compute_version_score(
    resource_versions: set[str],
    query_versions: set[str],
) -> float:
    """Compute version match score based on set relationships.

    Score modifiers:
    - Exact match: 1.0
    - Superset (resource has more): 0.95
    - Subset (resource has fewer): 0.85
    - Partial overlap: 0.75
    - Unversioned resource: 0.70
    - Disjoint (no overlap): 0.0 (excluded)

    Args:
        resource_versions: Versions the resource supports.
        query_versions: Versions the user is searching for.

    Returns:
        Score modifier (0.0-1.0).
    """
    # Handle unversioned resources
    if resource_versions == {"unversioned"}:
        return 0.70

    # Handle no query versions (match all)
    if not query_versions:
        return 1.0

    # Check for disjoint (no overlap)
    overlap = resource_versions & query_versions
    if not overlap:
        return 0.0  # Excluded

    # Exact match
    if resource_versions == query_versions:
        return 1.0

    # Superset (resource has all query versions plus more)
    if query_versions <= resource_versions:
        return 0.95

    # Subset (resource has fewer than query)
    if resource_versions <= query_versions:
        return 0.85

    # Partial overlap
    return 0.75


# --- v2: Resource Search ---


def search_resources(
    query: str,
    limit: int = 10,
    resource_type: Optional[str] = None,  # 'doc' or 'script'
    versions: Optional[list[str]] = None,
    tag_filter: Optional[list[str]] = None,
    include_chunks: bool = True,
    config: Optional[Config] = None,
) -> list[SearchResult]:
    """Search resources using hybrid ranking with version scoring.

    Searches both whole resource embeddings and chunk embeddings for
    finer-grained results. Results are deduplicated by resource, keeping
    the best-scoring match (either whole resource or specific chunk).

    Args:
        query: Search query.
        limit: Maximum results.
        resource_type: Filter by 'doc' or 'script'.
        versions: Filter by versions (with scoring).
        tag_filter: Filter by tags.
        include_chunks: If True, also search chunk embeddings.
        config: Configuration.

    Returns:
        List of SearchResult objects.
    """
    if config is None:
        config = get_config()

    import struct

    query_embedding = embed_text(query, config)
    embedding_blob = struct.pack(f"{len(query_embedding)}f", *query_embedding)
    query_versions = set(versions) if versions else set()

    with get_db(config) as conn:
        # Track best result per resource for deduplication
        best_by_resource: dict[str, SearchResult] = {}

        # --- Search whole resource embeddings ---
        sql = """
            SELECT r.*, re.distance
            FROM resources r
            JOIN resource_embeddings re ON r.id = re.resource_id
            WHERE re.embedding MATCH ?
            AND k = ?
        """
        params: list = [embedding_blob, limit * 3]

        if resource_type:
            sql += " AND r.type = ?"
            params.append(resource_type)

        if tag_filter:
            placeholders = ",".join("?" * len(tag_filter))
            sql += f"""
                AND r.id IN (
                    SELECT resource_id FROM resource_tags
                    WHERE tag IN ({placeholders})
                )
            """
            params.extend(tag_filter)

        sql += " ORDER BY re.distance LIMIT ?"
        params.append(limit * 3)

        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()

        for row in rows:
            result = _process_resource_row(conn, row, query_versions, tag_filter, query)
            if result:
                best_by_resource[result.id] = result

        # --- Search chunk embeddings ---
        if include_chunks:
            chunk_sql = """
                SELECT c.*, ce.distance, r.id as resource_id, r.title as resource_title,
                       r.type as resource_type, r.path as resource_path
                FROM resource_chunks c
                JOIN chunk_embeddings ce ON c.id = ce.chunk_id
                JOIN resources r ON c.resource_id = r.id
                WHERE ce.embedding MATCH ?
                AND k = ?
            """
            chunk_params: list = [embedding_blob, limit * 5]

            if resource_type:
                chunk_sql += " AND r.type = ?"
                chunk_params.append(resource_type)

            if tag_filter:
                placeholders = ",".join("?" * len(tag_filter))
                chunk_sql += f"""
                    AND r.id IN (
                        SELECT resource_id FROM resource_tags
                        WHERE tag IN ({placeholders})
                    )
                """
                chunk_params.extend(tag_filter)

            chunk_sql += " ORDER BY ce.distance LIMIT ?"
            chunk_params.append(limit * 5)

            cursor = conn.execute(chunk_sql, chunk_params)
            chunk_rows = cursor.fetchall()

            for chunk_row in chunk_rows:
                result = _process_chunk_row(conn, chunk_row, query_versions, query)
                if result:
                    resource_id = result.resource_id
                    # Keep better scoring result
                    if resource_id not in best_by_resource or result.score > best_by_resource[resource_id].score:
                        best_by_resource[resource_id] = result

        # Sort by score descending
        results = list(best_by_resource.values())
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]


def _process_resource_row(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    query_versions: set[str],
    tag_filter: Optional[list[str]],
    query: str = "",
) -> Optional[ResourceResult]:
    """Process a resource row into a ResourceResult."""
    # Get versions and tags for this resource
    resource_versions, tags = _fetch_resource_metadata(conn, row["id"])

    # Apply version scoring
    version_score = compute_version_score(resource_versions, query_versions)
    if math.isclose(version_score, 0.0):
        return None  # Skip disjoint versions

    # Calculate final score using improved scoring
    final_score = _compute_resource_score(
        distance=row["distance"],
        title=row["title"],
        content=row["content"] or "",
        tags=tags,
        query=query,
        version_score=version_score,
        chunk_boost=False,
    )

    return ResourceResult(
        id=row["id"],
        title=row["title"],
        content=row["content"][:500] if row["content"] else "",  # Snippet
        score=final_score,
        result_type="resource",
        tags=tags,
        resource_type=row["type"],
        versions=list(resource_versions),
        path=row["path"],
    )


def _process_chunk_row(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    query_versions: set[str],
    query: str = "",
) -> Optional[ChunkResult]:
    """Process a chunk row into a ChunkResult."""
    resource_id = row["resource_id"]

    # Get versions and tags for parent resource
    resource_versions, tags = _fetch_resource_metadata(conn, resource_id)

    # Apply version scoring
    version_score = compute_version_score(resource_versions, query_versions)
    if math.isclose(version_score, 0.0):
        return None  # Skip disjoint versions

    # Build display title including breadcrumb
    display_title = row["resource_title"]
    if row["breadcrumb"]:
        display_title = f"{row['resource_title']} > {row['breadcrumb']}"
    elif row["title"]:
        display_title = f"{row['resource_title']} > {row['title']}"

    # Calculate final score using improved scoring
    final_score = _compute_resource_score(
        distance=row["distance"],
        title=display_title,
        content=row["content"] or "",
        tags=tags,
        query=query,
        version_score=version_score,
        chunk_boost=True,  # Small boost for chunk-level matches
    )

    # Parse sections from JSON
    sections = []
    if row["sections"]:
        import json
        sections = json.loads(row["sections"])

    return ChunkResult(
        id=row["id"],  # Chunk ID
        title=display_title,
        content=row["content"][:500] if row["content"] else "",
        score=final_score,
        result_type="chunk",
        tags=tags,
        # Chunk-specific fields
        chunk_index=row["chunk_index"],
        breadcrumb=row["breadcrumb"],
        resource_id=resource_id,
        resource_title=row["resource_title"],
        versions=list(resource_versions),
        summary=row["summary"],
        sections=sections,
        # Parent resource metadata
        resource_type=row["resource_type"],
        path=row["resource_path"],
    )


def search_resources_grouped(
    query: str,
    limit: int = 10,
    resource_type: Optional[str] = None,
    versions: Optional[list[str]] = None,
    tag_filter: Optional[list[str]] = None,
    top_chunks_count: int = 5,
    config: Optional[Config] = None,
) -> tuple[list[ChunkResult], list[GroupedResourceResult]]:
    """Search resources and return grouped results with top matches.

    Unlike search_resources() which deduplicates to one result per resource,
    this function returns ALL matching chunks grouped by their parent resource,
    plus a summary of the top N chunks across all resources.

    Args:
        query: Search query.
        limit: Maximum number of resources to return.
        resource_type: Filter by 'doc' or 'script'.
        versions: Filter by versions.
        tag_filter: Filter by tags.
        top_chunks_count: Number of top chunks to return in the summary.
        config: Configuration.

    Returns:
        Tuple of (top_chunks, grouped_resources):
        - top_chunks: Top N chunks across all resources, sorted by score
        - grouped_resources: Resources with their matching chunks, sorted by best chunk score
    """
    if config is None:
        config = get_config()

    import struct

    query_embedding = embed_text(query, config)
    embedding_blob = struct.pack(f"{len(query_embedding)}f", *query_embedding)
    query_versions = set(versions) if versions else set()

    with get_db(config) as conn:
        # Collect ALL chunk results (not deduplicated)
        all_chunks: list[ChunkResult] = []

        # Track resources that matched at resource-level but not chunk-level
        resource_level_matches: dict[str, ResourceResult] = {}

        # --- Search chunk embeddings first (primary) ---
        chunk_sql = """
            SELECT c.*, ce.distance, r.id as resource_id, r.title as resource_title,
                   r.type as resource_type, r.path as resource_path
            FROM resource_chunks c
            JOIN chunk_embeddings ce ON c.id = ce.chunk_id
            JOIN resources r ON c.resource_id = r.id
            WHERE ce.embedding MATCH ?
            AND k = ?
        """
        chunk_params: list = [embedding_blob, limit * 10]

        if resource_type:
            chunk_sql += " AND r.type = ?"
            chunk_params.append(resource_type)

        if tag_filter:
            placeholders = ",".join("?" * len(tag_filter))
            chunk_sql += f"""
                AND r.id IN (
                    SELECT resource_id FROM resource_tags
                    WHERE tag IN ({placeholders})
                )
            """
            chunk_params.extend(tag_filter)

        chunk_sql += " ORDER BY ce.distance LIMIT ?"
        chunk_params.append(limit * 10)

        cursor = conn.execute(chunk_sql, chunk_params)
        chunk_rows = cursor.fetchall()

        resources_with_chunks: set[str] = set()
        for chunk_row in chunk_rows:
            result = _process_chunk_row(conn, chunk_row, query_versions, query)
            if result:
                all_chunks.append(result)
                resources_with_chunks.add(result.resource_id)

        # --- Search resource embeddings for resources without chunk matches ---
        resource_sql = """
            SELECT r.*, re.distance
            FROM resources r
            JOIN resource_embeddings re ON r.id = re.resource_id
            WHERE re.embedding MATCH ?
            AND k = ?
        """
        resource_params: list = [embedding_blob, limit * 3]

        if resource_type:
            resource_sql += " AND r.type = ?"
            resource_params.append(resource_type)

        if tag_filter:
            placeholders = ",".join("?" * len(tag_filter))
            resource_sql += f"""
                AND r.id IN (
                    SELECT resource_id FROM resource_tags
                    WHERE tag IN ({placeholders})
                )
            """
            resource_params.extend(tag_filter)

        resource_sql += " ORDER BY re.distance LIMIT ?"
        resource_params.append(limit * 3)

        cursor = conn.execute(resource_sql, resource_params)
        resource_rows = cursor.fetchall()

        for row in resource_rows:
            if row["id"] not in resources_with_chunks:
                result = _process_resource_row(conn, row, query_versions, tag_filter, query)
                if result:
                    resource_level_matches[result.id] = result

        # --- Group chunks by resource ---
        chunks_by_resource: dict[str, list[ChunkResult]] = {}
        for chunk in all_chunks:
            if chunk.resource_id not in chunks_by_resource:
                chunks_by_resource[chunk.resource_id] = []
            chunks_by_resource[chunk.resource_id].append(chunk)

        # Sort chunks within each resource by score
        for chunks in chunks_by_resource.values():
            chunks.sort(key=lambda x: x.score, reverse=True)

        # --- Build grouped results ---
        grouped_results: list[GroupedResourceResult] = []

        # Resources with chunk matches
        for resource_id, chunks in chunks_by_resource.items():
            if not chunks:
                continue
            first_chunk = chunks[0]  # Best scoring chunk
            grouped_results.append(GroupedResourceResult(
                resource_id=resource_id,
                resource_title=first_chunk.resource_title or "",
                resource_type=first_chunk.resource_type or "doc",
                versions=first_chunk.versions,
                tags=first_chunk.tags,
                path=first_chunk.path,
                best_score=first_chunk.score,
                chunks=chunks,
            ))

        # Resources with only resource-level matches (no specific chunk match)
        for resource_id, result in resource_level_matches.items():
            grouped_results.append(GroupedResourceResult(
                resource_id=resource_id,
                resource_title=result.title,
                resource_type=result.resource_type or "doc",
                versions=result.versions,
                tags=result.tags,
                path=result.path,
                best_score=result.score,
                chunks=[],  # No specific chunk matched
            ))

        # Sort grouped results by best_score
        grouped_results.sort(key=lambda x: x.best_score, reverse=True)
        grouped_results = grouped_results[:limit]

        # Get top chunks across all resources
        all_chunks.sort(key=lambda x: x.score, reverse=True)
        top_chunks = all_chunks[:top_chunks_count]

        return top_chunks, grouped_results


# --- v2: Unified Search ---


def unified_search(
    query: str,
    limit: int = 10,
    include_lessons: bool = True,
    include_resources: bool = True,
    include_rules: bool = True,
    resource_type: Optional[str] = None,
    versions: Optional[list[str]] = None,
    tag_filter: Optional[list[str]] = None,
    context_filter: Optional[list[str]] = None,
    context_tags: Optional[dict[str, Optional[float]]] = None,
    confidence_min: Optional[str] = None,
    source_filter: Optional[str] = None,
    config: Optional[Config] = None,
) -> list[SearchResult]:
    """Search across lessons, resources, and rules.

    Args:
        query: Search query.
        limit: Maximum total results.
        include_lessons: Include lessons in search.
        include_resources: Include resources in search.
        include_rules: Include approved rules in search.
        resource_type: Filter resources by type.
        versions: Filter resources by versions.
        tag_filter: Filter all results by tags.
        context_filter: Filter lessons by contexts.
        context_tags: Tag weights for boosting (e.g., {"jira": 1.5, "api": None}).
        confidence_min: Minimum confidence for lessons.
        source_filter: Filter lessons by source.
        config: Configuration.

    Returns:
        List of SearchResult objects sorted by score.
    """
    if config is None:
        config = get_config()

    all_results = []

    # Search lessons
    if include_lessons:
        lesson_results = hybrid_search(
            query,
            limit=limit,
            tag_filter=tag_filter,
            context_filter=context_filter,
            confidence_min=confidence_min,
            source_filter=source_filter,
            config=config,
        )
        all_results.extend(lesson_results)

    # Search resources
    if include_resources:
        resource_results = search_resources(
            query,
            limit=limit,
            resource_type=resource_type,
            versions=versions,
            tag_filter=tag_filter,
            config=config,
        )
        all_results.extend(resource_results)

    # Search approved rules (with tag overlap requirement)
    if include_rules:
        rule_results = search_rules(
            query,
            limit=limit,
            tag_filter=tag_filter,
            context_tags=context_tags,
            config=config,
        )
        all_results.extend(rule_results)

    # Apply link boosting (lessons linked to high-scoring resources get boosted)
    if include_lessons and include_resources:
        all_results = _apply_link_boosting(all_results, config)

    # Apply context tag boosting
    if context_tags:
        all_results = _apply_context_boosting(all_results, context_tags)

    # Sort by final score
    all_results.sort(key=lambda x: x.score, reverse=True)

    return all_results[:limit]


def search_rules(
    query: str,
    limit: int = 10,
    tag_filter: Optional[list[str]] = None,
    context_tags: Optional[dict[str, Optional[float]]] = None,
    config: Optional[Config] = None,
) -> list[SearchResult]:
    """Search approved rules that have tag overlap with context.

    Rules only surface when:
    1. approved = True
    2. At least one tag overlaps with tag_filter or context_tags

    Args:
        query: Search query.
        limit: Maximum results.
        tag_filter: Tags to match.
        context_tags: Context tags for overlap requirement.
        config: Configuration.

    Returns:
        List of SearchResult objects for matching rules.
    """
    if config is None:
        config = get_config()

    # Combine tag_filter and context_tags keys for overlap check
    relevant_tags = set(tag_filter or [])
    if context_tags:
        relevant_tags.update(context_tags.keys())

    # If no tags specified, rules won't surface (prevents false positives)
    if not relevant_tags:
        return []

    with get_db(config) as conn:
        # Get approved rules that have tag overlap
        placeholders = ",".join("?" * len(relevant_tags))
        sql = f"""
            SELECT DISTINCT r.* FROM rules r
            JOIN rule_tags rt ON r.id = rt.rule_id
            WHERE r.approved = 1
            AND rt.tag IN ({placeholders})
        """
        params = list(relevant_tags)

        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()

        results = []
        for row in rows:
            # Simple keyword scoring for rules
            score = _keyword_score(query, row["title"], row["content"])
            if score == 0:
                score = RULE_DEFAULT_SCORE  # Default score for tag-matched rules
            else:
                score = min(1.0, score)  # Cap at 1.0 for consistent result scoring

            # Get tags
            cursor = conn.execute(
                "SELECT tag FROM rule_tags WHERE rule_id = ?",
                (row["id"],)
            )
            tags = [r["tag"] for r in cursor.fetchall()]

            results.append(RuleResult(
                id=row["id"],
                title=row["title"],
                content=row["content"],
                score=score,
                result_type="rule",
                tags=tags,
                rationale=row["rationale"],
                approved=bool(row["approved"]),
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]


def _apply_link_boosting(
    results: list[SearchResult],
    config: Config,
    link_boost_factor: float = LINK_BOOST_FACTOR,
    min_linked_score: float = MIN_LINKED_SCORE,
) -> list[SearchResult]:
    """Apply link-based score boosting to results.

    If a lesson is linked to a resource that scored highly, boost the lesson's score.
    This helps surface relevant lessons when their linked documentation is highly relevant.

    Args:
        results: Search results (mixed lessons, resources, chunks).
        config: Configuration.
        link_boost_factor: How much linked resource score boosts lesson (0-1).
        min_linked_score: Minimum score for linked resource to trigger boost.
            This prevents boosting from tangentially related linked resources.

    Returns:
        Results with link boosting applied to lessons.
    """
    # Build map of resource_id -> best score
    resource_scores: dict[str, float] = {}
    for result in results:
        if result.result_type in ("resource", "chunk"):
            rid = result.resource_id if result.result_type == "chunk" else result.id
            if rid:
                resource_scores[rid] = max(resource_scores.get(rid, 0), result.score)

    # If no resources in results, nothing to boost with
    if not resource_scores:
        return results

    # Get lesson -> linked resources mapping from database
    with get_db(config) as conn:
        for result in results:
            if result.result_type == "lesson":
                # Check for linked resources (lesson→resource edges)
                cursor = conn.execute(
                    """SELECT to_id FROM edges
                       WHERE from_id = ? AND from_type = 'lesson' AND to_type = 'resource'""",
                    (result.id,)
                )
                linked_resource_ids = [row["to_id"] for row in cursor.fetchall()]

                # Find best score from linked resources (only if above threshold)
                best_linked_score = 0.0
                for rid in linked_resource_ids:
                    if rid in resource_scores and resource_scores[rid] >= min_linked_score:
                        best_linked_score = max(best_linked_score, resource_scores[rid])

                # Apply boost only if linked resource is highly relevant
                if best_linked_score > 0:
                    link_boost = best_linked_score * link_boost_factor
                    result.score = min(1.0, result.score + link_boost)

    return results


def _apply_context_boosting(
    results: list[SearchResult],
    context_tags: dict[str, Optional[float]],
) -> list[SearchResult]:
    """Apply context tag boosting to search results.

    Args:
        results: Search results to boost.
        context_tags: Tag weights. None values get default weight.

    Returns:
        Results with boosted scores.
    """
    # Calculate default weight (average of explicit weights, or 1.5)
    explicit_weights = [w for w in context_tags.values() if w is not None]
    default_weight = sum(explicit_weights) / len(explicit_weights) if explicit_weights else 1.5

    # Resolve weights
    weights = {
        tag: (weight if weight is not None else default_weight)
        for tag, weight in context_tags.items()
    }

    # Apply boosting
    match_bonus = MATCH_BONUS
    for result in results:
        boost = 0.0
        for tag in result.tags:
            if tag in weights:
                boost += weights[tag] * match_bonus
        result.score = result.score * (1 + boost)

    return results
