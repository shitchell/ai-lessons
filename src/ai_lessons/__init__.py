"""AI Lessons - Knowledge management system with semantic search and graph relationships."""

__version__ = "0.1.0"

from .core import (
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
)

__all__ = [
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
]
