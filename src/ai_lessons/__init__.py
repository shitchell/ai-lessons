"""AI Lessons - Knowledge management system with semantic search and graph relationships."""

__version__ = "0.1.0"

from .core import (
    # Lessons
    add_lesson,
    get_lesson,
    update_lesson,
    delete_lesson,
    recall,
    get_related,
    link_lessons,
    unlink_lessons,
    list_tags,
    list_sources,
    list_confidence_levels,
    # Resources and chunks
    get_chunk,
    list_chunks,
    list_resources,
    # Dataclasses
    ResourceChunk,
)

__all__ = [
    # Lessons
    "add_lesson",
    "get_lesson",
    "update_lesson",
    "delete_lesson",
    "recall",
    "get_related",
    "link_lessons",
    "unlink_lessons",
    "list_tags",
    "list_sources",
    "list_confidence_levels",
    # Resources and chunks
    "get_chunk",
    "list_chunks",
    "list_resources",
    # Dataclasses
    "ResourceChunk",
]
