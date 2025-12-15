"""Search functionality for ai-lessons."""

import re
import sqlite3
from dataclasses import dataclass
from typing import Optional

from .config import Config, get_config
from .db import get_db
from .embeddings import embed_text


@dataclass
class SearchResult:
    """A search result with score and metadata."""
    id: str
    title: str
    content: str
    score: float
    confidence: Optional[str] = None
    source: Optional[str] = None
    source_notes: Optional[str] = None
    tags: list[str] = None
    contexts: list[str] = None
    anti_contexts: list[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.contexts is None:
            self.contexts = []
        if self.anti_contexts is None:
            self.anti_contexts = []


def _normalize_text(text: str) -> str:
    """Normalize text for keyword matching."""
    # Lowercase, collapse whitespace
    text = text.lower()
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _keyword_score(query: str, title: str, content: str) -> float:
    """Calculate a simple keyword relevance score.

    Uses a basic TF-like scoring where:
    - Title matches are weighted 3x
    - Content matches are weighted 1x
    - Score normalized by query term count
    """
    query_terms = _normalize_text(query).split()
    if not query_terms:
        return 0.0

    title_norm = _normalize_text(title)
    content_norm = _normalize_text(content)

    score = 0.0
    for term in query_terms:
        # Title match (weighted 3x)
        if term in title_norm:
            score += 3.0
        # Content match
        if term in content_norm:
            score += 1.0

    # Normalize by number of terms
    return score / len(query_terms)


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

        return [_row_to_result(conn, row, row["distance"]) for row in results]


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
                scored.append((row, score))

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

    Uses reciprocal rank fusion to combine results from both methods.
    """
    if config is None:
        config = get_config()

    # Get weights from config
    semantic_weight = config.search.hybrid_weight_semantic
    keyword_weight = config.search.hybrid_weight_keyword

    # Get results from both methods (fetch more to allow fusion)
    fetch_limit = limit * 3

    vector_results = vector_search(
        query, fetch_limit, tag_filter, context_filter,
        confidence_min, source_filter, config
    )
    keyword_results = keyword_search(
        query, fetch_limit, tag_filter, context_filter,
        confidence_min, source_filter, config
    )

    # Build rank maps
    vector_ranks = {r.id: i + 1 for i, r in enumerate(vector_results)}
    keyword_ranks = {r.id: i + 1 for i, r in enumerate(keyword_results)}

    # Get all unique IDs
    all_ids = set(vector_ranks.keys()) | set(keyword_ranks.keys())

    # Calculate RRF scores
    k = 60  # RRF constant
    rrf_scores = {}
    for lesson_id in all_ids:
        score = 0.0
        if lesson_id in vector_ranks:
            score += semantic_weight / (k + vector_ranks[lesson_id])
        if lesson_id in keyword_ranks:
            score += keyword_weight / (k + keyword_ranks[lesson_id])
        rrf_scores[lesson_id] = score

    # Sort by RRF score
    sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

    # Build result map for easy lookup
    result_map = {r.id: r for r in vector_results + keyword_results}

    # Return top results with RRF scores
    results = []
    for lesson_id in sorted_ids[:limit]:
        result = result_map[lesson_id]
        result.score = rrf_scores[lesson_id]
        results.append(result)

    return results


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

    # Add filters
    filter_clauses = []
    if tag_filter:
        placeholders = ",".join("?" * len(tag_filter))
        filter_clauses.append(f"""
            l.id IN (
                SELECT lesson_id FROM lesson_tags
                WHERE tag IN ({placeholders})
            )
        """)
        params.extend(tag_filter)

    if context_filter:
        placeholders = ",".join("?" * len(context_filter))
        filter_clauses.append(f"""
            l.id IN (
                SELECT lesson_id FROM lesson_contexts
                WHERE context IN ({placeholders}) AND applies = TRUE
            )
        """)
        params.extend(context_filter)

    if confidence_min:
        filter_clauses.append("""
            l.confidence IN (
                SELECT name FROM confidence_levels
                WHERE ordinal >= (SELECT ordinal FROM confidence_levels WHERE name = ?)
            )
        """)
        params.append(confidence_min)

    if source_filter:
        filter_clauses.append("l.source = ?")
        params.append(source_filter)

    if filter_clauses:
        query += " AND " + " AND ".join(filter_clauses)

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
    params: list = []

    if tag_filter:
        placeholders = ",".join("?" * len(tag_filter))
        query += f"""
            AND l.id IN (
                SELECT lesson_id FROM lesson_tags
                WHERE tag IN ({placeholders})
            )
        """
        params.extend(tag_filter)

    if context_filter:
        placeholders = ",".join("?" * len(context_filter))
        query += f"""
            AND l.id IN (
                SELECT lesson_id FROM lesson_contexts
                WHERE context IN ({placeholders}) AND applies = TRUE
            )
        """
        params.extend(context_filter)

    if confidence_min:
        query += """
            AND l.confidence IN (
                SELECT name FROM confidence_levels
                WHERE ordinal >= (SELECT ordinal FROM confidence_levels WHERE name = ?)
            )
        """
        params.append(confidence_min)

    if source_filter:
        query += " AND l.source = ?"
        params.append(source_filter)

    cursor = conn.execute(query, params)
    return cursor.fetchall()


def _row_to_result(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    score: float,
) -> SearchResult:
    """Convert a database row to a SearchResult."""
    lesson_id = row["id"]

    # Get tags
    cursor = conn.execute(
        "SELECT tag FROM lesson_tags WHERE lesson_id = ?",
        (lesson_id,)
    )
    tags = [r["tag"] for r in cursor.fetchall()]

    # Get contexts
    cursor = conn.execute(
        "SELECT context, applies FROM lesson_contexts WHERE lesson_id = ?",
        (lesson_id,)
    )
    contexts = []
    anti_contexts = []
    for r in cursor.fetchall():
        if r["applies"]:
            contexts.append(r["context"])
        else:
            anti_contexts.append(r["context"])

    return SearchResult(
        id=lesson_id,
        title=row["title"],
        content=row["content"],
        score=score,
        confidence=row["confidence"],
        source=row["source"],
        source_notes=row["source_notes"],
        tags=tags,
        contexts=contexts,
        anti_contexts=anti_contexts,
    )
