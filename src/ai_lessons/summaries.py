"""LLM-based summary generation for resource chunks."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from .config import Config, get_config
from .db import get_db

logger = logging.getLogger(__name__)


# System prompt for summary generation (inspired by jira-docs MCP)
SUMMARY_SYSTEM_PROMPT = """You are a documentation assistant that creates concise summaries.

Write a 1-2 sentence summary that captures:
- What this content does or explains
- Key parameters, options, or concepts
- When you would use or need this information

Be specific and technical. Avoid vague phrases like "this section covers" or "documentation for".
Focus on the essential information that would help someone decide if this content is relevant."""


def generate_summary(content: str, title: Optional[str] = None, config: Optional[Config] = None) -> str:
    """Generate a summary for a chunk of content using an LLM.

    Args:
        content: The content to summarize.
        title: Optional title for context.
        config: Configuration to use.

    Returns:
        Generated summary string.

    Raises:
        ValueError: If summary generation is not configured.
        RuntimeError: If the LLM call fails.
    """
    if config is None:
        config = get_config()

    if not config.summaries.enabled:
        raise ValueError(
            "Summary generation not configured. Add 'summaries' section to config.yaml with "
            "'backend' (anthropic/openai) and 'model' settings."
        )

    # Prepare the content with optional title context
    if title:
        user_content = f"Title: {title}\n\nContent:\n{content}"
    else:
        user_content = content

    # Truncate if too long (keep to ~4000 chars for small model efficiency)
    if len(user_content) > 4000:
        user_content = user_content[:4000] + "\n\n[Content truncated...]"

    backend = config.summaries.backend
    model = config.summaries.model

    if backend == "anthropic":
        return _generate_anthropic(user_content, model, config)
    elif backend == "openai":
        return _generate_openai(user_content, model, config)
    else:
        raise ValueError(f"Unknown summary backend: {backend}")


def _generate_anthropic(content: str, model: str, config: Config) -> str:
    """Generate summary using Anthropic API."""
    try:
        import anthropic
    except ImportError:
        raise ImportError(
            "anthropic package not installed. Run: pip install anthropic"
        ) from None

    api_key = config.summaries.api_key
    if not api_key:
        # Try environment variable
        import os
        api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        raise ValueError(
            "Anthropic API key not found. Set 'api_key' in summaries config or "
            "ANTHROPIC_API_KEY environment variable."
        )

    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=model,
        max_tokens=256,
        system=SUMMARY_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": content}
        ],
    )

    return response.content[0].text.strip()


def _generate_openai(content: str, model: str, config: Config) -> str:
    """Generate summary using OpenAI API."""
    try:
        import openai
    except ImportError:
        raise ImportError(
            "openai package not installed. Run: pip install openai"
        ) from None

    api_key = config.summaries.api_key
    if not api_key:
        # Try environment variable
        import os
        api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        raise ValueError(
            "OpenAI API key not found. Set 'api_key' in summaries config or "
            "OPENAI_API_KEY environment variable."
        )

    client = openai.OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model=model,
        max_tokens=256,
        messages=[
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
    )

    return response.choices[0].message.content.strip()


def generate_chunk_summaries(
    resource_id: Optional[str] = None,
    chunk_ids: Optional[list[str]] = None,
    force: bool = False,
    config: Optional[Config] = None,
) -> dict[str, str]:
    """Generate summaries for chunks and store them in the database.

    Args:
        resource_id: Generate summaries for all chunks of this resource.
        chunk_ids: Generate summaries for specific chunks.
        force: Regenerate even if summary already exists.
        config: Configuration to use.

    Returns:
        Dict mapping chunk_id to generated summary.
    """
    if config is None:
        config = get_config()

    if not config.summaries.enabled:
        raise ValueError(
            "Summary generation not configured. Add 'summaries' section to config.yaml."
        )

    summaries = {}

    with get_db(config) as conn:
        # Build query to get chunks
        if chunk_ids:
            placeholders = ",".join("?" * len(chunk_ids))
            query = f"SELECT id, title, content, summary FROM resource_chunks WHERE id IN ({placeholders})"
            cursor = conn.execute(query, chunk_ids)
        elif resource_id:
            query = "SELECT id, title, content, summary FROM resource_chunks WHERE resource_id = ? ORDER BY chunk_index"
            cursor = conn.execute(query, (resource_id,))
        else:
            raise ValueError("Either resource_id or chunk_ids must be provided")

        chunks = cursor.fetchall()

        for chunk in chunks:
            chunk_id = chunk["id"]

            # Skip if already has summary and not forcing
            if chunk["summary"] and not force:
                summaries[chunk_id] = chunk["summary"]
                continue

            # Generate summary
            try:
                summary = generate_summary(
                    content=chunk["content"],
                    title=chunk["title"],
                    config=config,
                )
            except (RuntimeError, ValueError, OSError) as e:
                # Log error but continue with other chunks
                # RuntimeError: API/model errors, ValueError: invalid input, OSError: network issues
                logger.warning("Failed to generate summary for %s: %s", chunk_id, e)
                continue

            # Store in database
            conn.execute(
                """
                UPDATE resource_chunks
                SET summary = ?, summary_generated_at = ?
                WHERE id = ?
                """,
                (summary, datetime.utcnow().isoformat(), chunk_id),
            )
            conn.commit()

            summaries[chunk_id] = summary

    return summaries


def needs_summary_update(chunk_id: str, config: Optional[Config] = None) -> bool:
    """Check if a chunk's summary needs to be regenerated.

    A summary needs update if:
    - No summary exists
    - summary_generated_at is older than resource's updated_at

    Args:
        chunk_id: The chunk ID to check.
        config: Configuration to use.

    Returns:
        True if summary should be regenerated.
    """
    if config is None:
        config = get_config()

    with get_db(config) as conn:
        cursor = conn.execute(
            """
            SELECT c.summary, c.summary_generated_at, r.updated_at
            FROM resource_chunks c
            JOIN resources r ON c.resource_id = r.id
            WHERE c.id = ?
            """,
            (chunk_id,),
        )
        row = cursor.fetchone()

        if row is None:
            return False  # Chunk doesn't exist

        if not row["summary"]:
            return True  # No summary exists

        if not row["summary_generated_at"]:
            return True  # No timestamp (legacy)

        # Compare timestamps
        summary_time = datetime.fromisoformat(row["summary_generated_at"])
        if row["updated_at"]:
            resource_time = datetime.fromisoformat(row["updated_at"])
            return summary_time < resource_time

        return False
