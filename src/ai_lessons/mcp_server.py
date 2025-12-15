"""MCP server for ai-lessons."""

import asyncio
import logging
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from . import core
from .config import get_config
from .db import init_db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-lessons-mcp")

# Create MCP server
server = Server("ai-lessons")


def _lesson_to_dict(lesson: core.Lesson) -> dict:
    """Convert a Lesson to a dictionary for JSON serialization."""
    return {
        "id": lesson.id,
        "title": lesson.title,
        "content": lesson.content,
        "confidence": lesson.confidence,
        "source": lesson.source,
        "source_notes": lesson.source_notes,
        "tags": lesson.tags,
        "contexts": lesson.contexts,
        "anti_contexts": lesson.anti_contexts,
        "created_at": str(lesson.created_at) if lesson.created_at else None,
        "updated_at": str(lesson.updated_at) if lesson.updated_at else None,
    }


def _search_result_to_dict(result: core.search.SearchResult) -> dict:
    """Convert a SearchResult to a dictionary for JSON serialization."""
    return {
        "id": result.id,
        "title": result.title,
        "content": result.content,
        "score": result.score,
        "confidence": result.confidence,
        "source": result.source,
        "tags": result.tags,
        "contexts": result.contexts,
        "anti_contexts": result.anti_contexts,
    }


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="learn",
            description="Save a new lesson learned. Use when you discover something non-obvious through debugging, experimentation, or problem-solving.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short, descriptive title for the lesson",
                    },
                    "content": {
                        "type": "string",
                        "description": "Detailed explanation of the lesson",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for categorization (e.g., ['jira', 'api', 'gotcha'])",
                    },
                    "contexts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Contexts where this lesson applies",
                    },
                    "anti_contexts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Contexts where this lesson does NOT apply",
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["very-low", "low", "medium", "high", "very-high"],
                        "description": "How confident are you in this lesson?",
                    },
                    "source": {
                        "type": "string",
                        "enum": ["inferred", "tested", "documented", "observed", "hearsay"],
                        "description": "How was this knowledge obtained?",
                    },
                    "source_notes": {
                        "type": "string",
                        "description": "Additional notes about the source",
                    },
                },
                "required": ["title", "content"],
            },
        ),
        Tool(
            name="recall",
            description="Search for relevant lessons. Use before attempting tasks to check for existing knowledge.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query describing what you're looking for",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by tags",
                    },
                    "contexts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by contexts",
                    },
                    "confidence_min": {
                        "type": "string",
                        "enum": ["very-low", "low", "medium", "high", "very-high"],
                        "description": "Minimum confidence level",
                    },
                    "source": {
                        "type": "string",
                        "description": "Filter by source type",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_lesson",
            description="Get a specific lesson by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "lesson_id": {
                        "type": "string",
                        "description": "The lesson ID",
                    },
                },
                "required": ["lesson_id"],
            },
        ),
        Tool(
            name="update_lesson",
            description="Update an existing lesson.",
            inputSchema={
                "type": "object",
                "properties": {
                    "lesson_id": {
                        "type": "string",
                        "description": "The lesson ID to update",
                    },
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["very-low", "low", "medium", "high", "very-high"],
                    },
                    "source": {
                        "type": "string",
                        "enum": ["inferred", "tested", "documented", "observed", "hearsay"],
                    },
                    "source_notes": {"type": "string"},
                },
                "required": ["lesson_id"],
            },
        ),
        Tool(
            name="delete_lesson",
            description="Delete a lesson.",
            inputSchema={
                "type": "object",
                "properties": {
                    "lesson_id": {
                        "type": "string",
                        "description": "The lesson ID to delete",
                    },
                },
                "required": ["lesson_id"],
            },
        ),
        Tool(
            name="related",
            description="Get lessons related to a given lesson via graph edges.",
            inputSchema={
                "type": "object",
                "properties": {
                    "lesson_id": {
                        "type": "string",
                        "description": "The starting lesson ID",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Maximum traversal depth",
                        "default": 1,
                    },
                    "relations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by relation types",
                    },
                },
                "required": ["lesson_id"],
            },
        ),
        Tool(
            name="link",
            description="Create a relationship between two lessons.",
            inputSchema={
                "type": "object",
                "properties": {
                    "from_id": {
                        "type": "string",
                        "description": "Source lesson ID",
                    },
                    "to_id": {
                        "type": "string",
                        "description": "Target lesson ID",
                    },
                    "relation": {
                        "type": "string",
                        "description": "Relationship type (e.g., 'related_to', 'derived_from', 'contradicts')",
                    },
                },
                "required": ["from_id", "to_id", "relation"],
            },
        ),
        Tool(
            name="tags",
            description="List all tags with optional usage counts.",
            inputSchema={
                "type": "object",
                "properties": {
                    "with_counts": {
                        "type": "boolean",
                        "description": "Include usage counts",
                        "default": False,
                    },
                },
            },
        ),
        Tool(
            name="sources",
            description="List all source types.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="confidence_levels",
            description="List all confidence levels.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    try:
        # Ensure database is initialized
        config = get_config()
        init_db(config)

        if name == "learn":
            lesson_id = core.add_lesson(
                title=arguments["title"],
                content=arguments["content"],
                tags=arguments.get("tags"),
                contexts=arguments.get("contexts"),
                anti_contexts=arguments.get("anti_contexts"),
                confidence=arguments.get("confidence"),
                source=arguments.get("source"),
                source_notes=arguments.get("source_notes"),
            )
            return [TextContent(
                type="text",
                text=f"Lesson saved with ID: {lesson_id}",
            )]

        elif name == "recall":
            results = core.recall(
                query=arguments["query"],
                tags=arguments.get("tags"),
                contexts=arguments.get("contexts"),
                confidence_min=arguments.get("confidence_min"),
                source=arguments.get("source"),
                limit=arguments.get("limit", 10),
            )

            if not results:
                return [TextContent(type="text", text="No relevant lessons found.")]

            # Format results
            formatted = []
            for r in results:
                formatted.append(_search_result_to_dict(r))

            import json
            return [TextContent(
                type="text",
                text=json.dumps(formatted, indent=2),
            )]

        elif name == "get_lesson":
            lesson = core.get_lesson(arguments["lesson_id"])
            if lesson is None:
                return [TextContent(type="text", text="Lesson not found.")]

            import json
            return [TextContent(
                type="text",
                text=json.dumps(_lesson_to_dict(lesson), indent=2),
            )]

        elif name == "update_lesson":
            success = core.update_lesson(
                lesson_id=arguments["lesson_id"],
                title=arguments.get("title"),
                content=arguments.get("content"),
                tags=arguments.get("tags"),
                confidence=arguments.get("confidence"),
                source=arguments.get("source"),
                source_notes=arguments.get("source_notes"),
            )

            if success:
                return [TextContent(type="text", text="Lesson updated.")]
            else:
                return [TextContent(type="text", text="Lesson not found.")]

        elif name == "delete_lesson":
            success = core.delete_lesson(arguments["lesson_id"])
            if success:
                return [TextContent(type="text", text="Lesson deleted.")]
            else:
                return [TextContent(type="text", text="Lesson not found.")]

        elif name == "related":
            lessons = core.get_related(
                lesson_id=arguments["lesson_id"],
                depth=arguments.get("depth", 1),
                relations=arguments.get("relations"),
            )

            if not lessons:
                return [TextContent(type="text", text="No related lessons found.")]

            import json
            formatted = [_lesson_to_dict(l) for l in lessons]
            return [TextContent(
                type="text",
                text=json.dumps(formatted, indent=2),
            )]

        elif name == "link":
            success = core.link_lessons(
                from_id=arguments["from_id"],
                to_id=arguments["to_id"],
                relation=arguments["relation"],
            )

            if success:
                return [TextContent(
                    type="text",
                    text=f"Linked {arguments['from_id']} --[{arguments['relation']}]--> {arguments['to_id']}",
                )]
            else:
                return [TextContent(type="text", text="Link already exists or lessons not found.")]

        elif name == "tags":
            tags = core.list_tags(with_counts=arguments.get("with_counts", False))

            if not tags:
                return [TextContent(type="text", text="No tags found.")]

            if arguments.get("with_counts"):
                lines = [f"{t.name} ({t.count})" for t in tags]
            else:
                lines = [t.name for t in tags]

            return [TextContent(type="text", text="\n".join(lines))]

        elif name == "sources":
            sources = core.list_sources()
            lines = []
            for s in sources:
                lines.append(f"{s.name}: {s.description or 'No description'}")
            return [TextContent(type="text", text="\n".join(lines))]

        elif name == "confidence_levels":
            levels = core.list_confidence_levels()
            lines = [f"{l.ordinal}. {l.name}" for l in levels]
            return [TextContent(type="text", text="\n".join(lines))]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.exception(f"Error in tool {name}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """Run the MCP server."""
    config = get_config()
    init_db(config)
    logger.info(f"AI Lessons MCP server started (db: {config.db_path})")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def run():
    """Entry point for the MCP server."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
