"""MCP server for ai-lessons."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from . import core
from .config import get_config
from .db import init_db
from .search import search_resources, unified_search

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


def _search_result_to_dict(result) -> dict:
    """Convert a SearchResult to a dictionary for JSON serialization."""
    base = {
        "id": result.id,
        "title": result.title,
        "content": result.content,
        "score": result.score,
        "result_type": result.result_type,
        "tags": result.tags,
    }

    # Add type-specific fields
    if result.result_type == "lesson":
        base.update({
            "confidence": result.confidence,
            "source": result.source,
            "contexts": result.contexts,
            "anti_contexts": result.anti_contexts,
        })
    elif result.result_type == "resource":
        base.update({
            "resource_type": result.resource_type,
            "versions": result.versions,
            "path": result.path,
        })
    elif result.result_type == "chunk":
        base.update({
            "resource_type": result.resource_type,
            "versions": result.versions,
            "path": result.path,
            "chunk_id": result.id,  # Chunk ID is in the base id field
            "chunk_index": result.chunk_index,
            "chunk_breadcrumb": result.breadcrumb,
            "resource_id": result.resource_id,
            "resource_title": result.resource_title,
        })
    elif result.result_type == "rule":
        base.update({
            "rationale": result.rationale,
            "approved": result.approved,
        })

    return base


def _resource_to_dict(resource: core.Resource) -> dict:
    """Convert a Resource to a dictionary for JSON serialization."""
    return {
        "id": resource.id,
        "type": resource.type,
        "title": resource.title,
        "path": resource.path,
        "content": resource.content,
        "content_hash": resource.content_hash,
        "source_ref": resource.source_ref,
        "versions": resource.versions,
        "tags": resource.tags,
        "indexed_at": str(resource.indexed_at) if resource.indexed_at else None,
        "created_at": str(resource.created_at) if resource.created_at else None,
        "updated_at": str(resource.updated_at) if resource.updated_at else None,
    }


def _rule_to_dict(rule: core.Rule) -> dict:
    """Convert a Rule to a dictionary for JSON serialization."""
    return {
        "id": rule.id,
        "title": rule.title,
        "content": rule.content,
        "rationale": rule.rationale,
        "approved": rule.approved,
        "approved_at": str(rule.approved_at) if rule.approved_at else None,
        "approved_by": rule.approved_by,
        "suggested_by": rule.suggested_by,
        "tags": rule.tags,
        "linked_lessons": rule.linked_lessons,
        "linked_resources": rule.linked_resources,
        "created_at": str(rule.created_at) if rule.created_at else None,
        "updated_at": str(rule.updated_at) if rule.updated_at else None,
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
        # --- Resource tools ---
        Tool(
            name="add_resource",
            description="Add a doc or script resource with optional chunking. Docs are automatically chunked for better search. Use preview=true to see chunking results without storing.",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["doc", "script"],
                        "description": "Resource type",
                    },
                    "path": {
                        "type": "string",
                        "description": "Filesystem path to the resource",
                    },
                    "title": {
                        "type": "string",
                        "description": "Resource title",
                    },
                    "versions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Version(s) this resource applies to (e.g., ['v2', 'v3'])",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for categorization",
                    },
                    "chunking": {
                        "type": "object",
                        "description": "Chunking configuration (docs only)",
                        "properties": {
                            "strategy": {
                                "type": "string",
                                "enum": ["auto", "headers", "delimiter", "fixed", "none"],
                                "description": "Chunking strategy (default: auto)",
                            },
                            "min_size": {
                                "type": "integer",
                                "description": "Minimum chunk size in tokens (default: 100)",
                            },
                            "max_size": {
                                "type": "integer",
                                "description": "Maximum chunk size in tokens (default: 800)",
                            },
                            "header_levels": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "Header levels to split on (default: [2, 3])",
                            },
                            "delimiter_pattern": {
                                "type": "string",
                                "description": "Regex pattern for delimiter-based chunking",
                            },
                        },
                    },
                    "preview": {
                        "type": "boolean",
                        "description": "If true, return chunking preview without storing",
                    },
                },
                "required": ["type", "path", "title"],
            },
        ),
        Tool(
            name="search_resources",
            description="Search for docs and scripts with semantic search and version filtering.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "type": {
                        "type": "string",
                        "enum": ["doc", "script"],
                        "description": "Filter by resource type",
                    },
                    "versions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by versions",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by tags",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_resource",
            description="Get full resource content by ID. For scripts, automatically refreshes if file has changed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_id": {
                        "type": "string",
                        "description": "The resource ID",
                    },
                },
                "required": ["resource_id"],
            },
        ),
        Tool(
            name="run_script",
            description="Execute a script resource with optional arguments.",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_id": {
                        "type": "string",
                        "description": "The script resource ID",
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Arguments to pass to the script",
                    },
                },
                "required": ["resource_id"],
            },
        ),
        Tool(
            name="delete_resource",
            description="Delete a resource.",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_id": {
                        "type": "string",
                        "description": "The resource ID to delete",
                    },
                },
                "required": ["resource_id"],
            },
        ),
        # --- Rule tools ---
        Tool(
            name="suggest_rule",
            description="Suggest a rule for human approval. Rules are prescriptive guidance that require rationale.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Rule title (e.g., 'Always GET before PUT on Jira workflows')",
                    },
                    "content": {
                        "type": "string",
                        "description": "Rule content (the prescription)",
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Why this rule exists (required)",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for surfacing the rule in relevant contexts",
                    },
                    "linked_lessons": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lesson IDs this rule relates to",
                    },
                    "linked_resources": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Resource IDs this rule relates to",
                    },
                },
                "required": ["title", "content", "rationale"],
            },
        ),
        Tool(
            name="get_rule",
            description="Get a rule by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "rule_id": {
                        "type": "string",
                        "description": "The rule ID",
                    },
                },
                "required": ["rule_id"],
            },
        ),
        Tool(
            name="unified_search",
            description="Search across lessons, resources, and rules with optional context-weighted boosting.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "include_lessons": {
                        "type": "boolean",
                        "description": "Include lessons in search",
                        "default": True,
                    },
                    "include_resources": {
                        "type": "boolean",
                        "description": "Include resources in search",
                        "default": True,
                    },
                    "include_rules": {
                        "type": "boolean",
                        "description": "Include approved rules in search",
                        "default": True,
                    },
                    "resource_type": {
                        "type": "string",
                        "enum": ["doc", "script"],
                        "description": "Filter resources by type",
                    },
                    "versions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter resources by versions",
                    },
                    "context_tags": {
                        "type": "object",
                        "description": "Tag weights for context boosting (e.g., {'jira': 1.5, 'api': null})",
                        "additionalProperties": {"type": "number", "nullable": True},
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by tags",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results",
                        "default": 10,
                    },
                },
                "required": ["query"],
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

        # --- Resource handlers ---

        elif name == "add_resource":
            from pathlib import Path
            path = arguments["path"]
            if not Path(path).exists():
                return [TextContent(type="text", text=f"Error: Path does not exist: {path}")]

            # Build chunking config if provided
            chunking_config = None
            if arguments.get("chunking") and arguments["type"] == "doc":
                from .chunking import ChunkingConfig
                chunking_opts = arguments["chunking"]
                chunking_config = ChunkingConfig(
                    strategy=chunking_opts.get("strategy", "auto"),
                    min_chunk_size=chunking_opts.get("min_size", 100),
                    max_chunk_size=chunking_opts.get("max_size", 800),
                    header_split_levels=chunking_opts.get("header_levels", [2, 3]),
                    delimiter_pattern=chunking_opts.get("delimiter_pattern"),
                )

            # Handle preview mode
            if arguments.get("preview") and arguments["type"] == "doc":
                from .chunking import ChunkingConfig, chunk_document
                content = Path(path).read_text()

                # Use provided config or default
                preview_config = chunking_config or ChunkingConfig()
                result = chunk_document(content, preview_config, source_path=path)

                # Format preview
                import json
                preview = {
                    "document_path": result.document_path,
                    "total_tokens": result.total_tokens,
                    "strategy": result.strategy,
                    "strategy_reason": result.strategy_reason,
                    "chunk_count": len(result.chunks),
                    "chunks": [
                        {
                            "index": c.index,
                            "title": c.title,
                            "breadcrumb": c.breadcrumb,
                            "token_count": c.token_count,
                            "start_line": c.start_line,
                            "end_line": c.end_line,
                            "warnings": c.warnings,
                        }
                        for c in result.chunks
                    ],
                    "summary": result.summary(),
                    "warnings": result.warnings,
                }
                return [TextContent(
                    type="text",
                    text=json.dumps(preview, indent=2),
                )]

            resource_id = core.add_resource(
                type=arguments["type"],
                title=arguments["title"],
                path=path,
                versions=arguments.get("versions"),
                tags=arguments.get("tags"),
                chunking_config=chunking_config,
            )

            # Include chunk count in response for docs
            response_text = f"Resource added with ID: {resource_id}"
            if arguments["type"] == "doc":
                from .db import get_db
                with get_db(config) as conn:
                    cursor = conn.execute(
                        "SELECT COUNT(*) FROM resource_chunks WHERE resource_id = ?",
                        (resource_id,),
                    )
                    chunk_count = cursor.fetchone()[0]
                response_text += f"\nChunks created: {chunk_count}"

            return [TextContent(
                type="text",
                text=response_text,
            )]

        elif name == "search_resources":
            results = search_resources(
                query=arguments["query"],
                resource_type=arguments.get("type"),
                versions=arguments.get("versions"),
                tag_filter=arguments.get("tags"),
                limit=arguments.get("limit", 10),
            )

            if not results:
                return [TextContent(type="text", text="No resources found.")]

            import json
            formatted = [_search_result_to_dict(r) for r in results]
            return [TextContent(
                type="text",
                text=json.dumps(formatted, indent=2),
            )]

        elif name == "get_resource":
            resource = core.get_resource(arguments["resource_id"])
            if resource is None:
                return [TextContent(type="text", text="Resource not found.")]

            import json
            return [TextContent(
                type="text",
                text=json.dumps(_resource_to_dict(resource), indent=2),
            )]

        elif name == "run_script":
            resource = core.get_resource(arguments["resource_id"])
            if resource is None:
                return [TextContent(type="text", text="Resource not found.")]

            if resource.type != "script":
                return [TextContent(type="text", text=f"Error: Resource is not a script (type: {resource.type})")]

            if not resource.path:
                return [TextContent(type="text", text="Error: Script has no path")]

            from pathlib import Path
            if not Path(resource.path).exists():
                return [TextContent(type="text", text=f"Error: Script file not found: {resource.path}")]

            try:
                args = arguments.get("args", [])
                result = subprocess.run(
                    [resource.path] + args,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                output = f"Exit code: {result.returncode}\n"
                if result.stdout:
                    output += f"\nstdout:\n{result.stdout}"
                if result.stderr:
                    output += f"\nstderr:\n{result.stderr}"
                return [TextContent(type="text", text=output)]
            except subprocess.TimeoutExpired:
                return [TextContent(type="text", text="Error: Script execution timed out (60s limit)")]
            except PermissionError:
                return [TextContent(type="text", text=f"Error: Script is not executable: {resource.path}")]
            except OSError as e:
                return [TextContent(type="text", text=f"Error running script: {str(e)}")]

        elif name == "delete_resource":
            success = core.delete_resource(arguments["resource_id"])
            if success:
                return [TextContent(type="text", text="Resource deleted.")]
            else:
                return [TextContent(type="text", text="Resource not found.")]

        # --- Rule handlers ---

        elif name == "suggest_rule":
            rule_id = core.suggest_rule(
                title=arguments["title"],
                content=arguments["content"],
                rationale=arguments["rationale"],
                tags=arguments.get("tags"),
                linked_lessons=arguments.get("linked_lessons"),
                linked_resources=arguments.get("linked_resources"),
            )
            return [TextContent(
                type="text",
                text=f"Rule suggested with ID: {rule_id}\nNote: Rule requires human approval before it will appear in search results.",
            )]

        elif name == "get_rule":
            rule = core.get_rule(arguments["rule_id"])
            if rule is None:
                return [TextContent(type="text", text="Rule not found.")]

            import json
            return [TextContent(
                type="text",
                text=json.dumps(_rule_to_dict(rule), indent=2),
            )]

        elif name == "unified_search":
            results = unified_search(
                query=arguments["query"],
                include_lessons=arguments.get("include_lessons", True),
                include_resources=arguments.get("include_resources", True),
                include_rules=arguments.get("include_rules", True),
                resource_type=arguments.get("resource_type"),
                versions=arguments.get("versions"),
                tag_filter=arguments.get("tags"),
                context_tags=arguments.get("context_tags"),
                limit=arguments.get("limit", 10),
            )

            if not results:
                return [TextContent(type="text", text="No results found.")]

            import json
            formatted = [_search_result_to_dict(r) for r in results]
            return [TextContent(
                type="text",
                text=json.dumps(formatted, indent=2),
            )]

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
