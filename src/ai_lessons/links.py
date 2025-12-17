"""Link extraction and resolution for ai-lessons resources."""

import json
import re
from pathlib import Path
from typing import NamedTuple, Optional

# Try to use pysqlite3 which has extension loading enabled,
# fall back to standard sqlite3
try:
    import pysqlite3 as sqlite3
except ImportError:
    import sqlite3

from .chunking import Chunk


class ExtractedLink(NamedTuple):
    """A link extracted from markdown content."""

    link_text: str  # The display text from [text](path)
    path: str  # Original path from markdown
    fragment: Optional[str]  # Without # prefix
    absolute_path: str  # Resolved absolute path
    line_number: int  # For determining which chunk


def extract_links(content: str, source_path: str) -> list[ExtractedLink]:
    """Extract markdown links from content and resolve to absolute paths.

    Args:
        content: Document content.
        source_path: Absolute path of the source file (for resolving relative links).

    Returns:
        List of extracted links with resolved paths.
    """
    # Pattern: [text](path) or [text](path#fragment)
    # Excludes URLs (http://, https://, mailto:, #-only)
    pattern = r"\[([^\]]+)\]\((?!https?://|mailto:|#)([^)#\s]+)(#[^)\s]+)?\)"

    source_dir = Path(source_path).parent
    links = []

    for line_num, line in enumerate(content.split("\n"), 1):
        for match in re.finditer(pattern, line):
            link_text = match.group(1)
            path = match.group(2)
            fragment_with_hash = match.group(3)

            # Resolve relative path to absolute
            if path.startswith("/"):
                absolute_path = path
            else:
                absolute_path = str((source_dir / path).resolve())

            # Extract fragment without #
            fragment = None
            if fragment_with_hash:
                fragment = fragment_with_hash[1:]  # Remove leading #

            links.append(
                ExtractedLink(
                    link_text=link_text,
                    path=path,
                    fragment=fragment,
                    absolute_path=absolute_path,
                    line_number=line_num,
                )
            )

    # Also extract same-file fragment links: [text](#section)
    fragment_pattern = r"\[([^\]]+)\]\((#[^)\s]+)\)"
    for line_num, line in enumerate(content.split("\n"), 1):
        for match in re.finditer(fragment_pattern, line):
            link_text = match.group(1)
            fragment = match.group(2)[1:]  # Remove #

            links.append(
                ExtractedLink(
                    link_text=link_text,
                    path="",  # Same file
                    fragment=fragment,
                    absolute_path=source_path,  # Same file
                    line_number=line_num,
                )
            )

    return links


def find_chunk_for_line(chunks: list[Chunk], line_number: int) -> Optional[str]:
    """Find which chunk contains a given line number.

    Args:
        chunks: List of chunks with start_line and end_line.
        line_number: 1-indexed line number.

    Returns:
        Chunk ID if found, None otherwise.
    """
    # Convert to 0-indexed for comparison with chunk.start_line/end_line
    line_idx = line_number - 1

    for chunk in chunks:
        if chunk.start_line <= line_idx <= chunk.end_line:
            # Chunks don't have an ID until stored - return index as string
            # The caller will map this to actual chunk IDs
            return str(chunk.index)

    return None


def resolve_link_to_resource(conn: sqlite3.Connection, to_path: str) -> Optional[str]:
    """Find a resource matching the given path.

    Args:
        conn: Database connection.
        to_path: Absolute path to look up.

    Returns:
        Resource ID if found, None otherwise.
    """
    cursor = conn.execute("SELECT id FROM resources WHERE path = ?", (to_path,))
    row = cursor.fetchone()
    return row["id"] if row else None


def resolve_fragment_to_chunk(
    conn: sqlite3.Connection,
    resource_id: str,
    fragment: str,
) -> Optional[str]:
    """Find a chunk within a resource that contains the given section.

    Args:
        conn: Database connection.
        resource_id: Parent resource ID.
        fragment: Section name to find (without #).

    Returns:
        Chunk ID if found, None otherwise.
    """
    cursor = conn.execute(
        "SELECT id, sections FROM resource_chunks WHERE resource_id = ?",
        (resource_id,),
    )

    # Normalize fragment for comparison (lowercase, hyphen-to-space)
    fragment_normalized = fragment.lower().replace("-", " ").replace("_", " ")

    for row in cursor.fetchall():
        if row["sections"]:
            sections = json.loads(row["sections"])
            for section in sections:
                section_normalized = section.lower().replace("-", " ").replace("_", " ")
                if fragment_normalized == section_normalized:
                    return row["id"]

    return None
