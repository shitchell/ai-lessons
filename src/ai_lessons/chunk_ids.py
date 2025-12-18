"""Chunk ID utilities.

Chunk IDs follow the format: <resource_id>.<chunk_index>
Example: RES01KCPN9VWAZNSKYVHPCWVPXA2C.1

This makes the parent relationship structural and allows easy parsing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedChunkId:
    """Parsed chunk ID components."""
    resource_id: str
    chunk_index: int

    @property
    def chunk_id(self) -> str:
        """Reconstruct the full chunk ID."""
        return f"{self.resource_id}.{self.chunk_index}"


def generate_chunk_id(resource_id: str, chunk_index: int) -> str:
    """Generate a chunk ID from resource ID and index.

    Args:
        resource_id: Parent resource ULID.
        chunk_index: Zero-based chunk index.

    Returns:
        Chunk ID in format "<resource_id>.<chunk_index>".
    """
    return f"{resource_id}.{chunk_index}"


def parse_chunk_id(chunk_id: str) -> Optional[ParsedChunkId]:
    """Parse a chunk ID into components.

    Args:
        chunk_id: Chunk ID to parse (e.g., "RES01KCPN9V...0").

    Returns:
        ParsedChunkId if valid, None if invalid format.
    """
    if "." not in chunk_id:
        return None

    parts = chunk_id.rsplit(".", 1)
    if len(parts) != 2:
        return None

    resource_id, index_str = parts

    # Resource ID must not be empty or contain dots (ULIDs don't have dots)
    if not resource_id or "." in resource_id:
        return None

    try:
        chunk_index = int(index_str)
    except ValueError:
        return None

    if chunk_index < 0:
        return None

    return ParsedChunkId(resource_id=resource_id, chunk_index=chunk_index)


def is_chunk_id(id_str: str) -> bool:
    """Check if a string is a chunk ID (contains .N suffix).

    Args:
        id_str: ID string to check.

    Returns:
        True if looks like a chunk ID, False otherwise.
    """
    return parse_chunk_id(id_str) is not None


def is_resource_id(id_str: str) -> bool:
    """Check if a string is a resource ID (has RES prefix, no .N suffix).

    Args:
        id_str: ID string to check.

    Returns:
        True if looks like a resource ID, False otherwise.
    """
    return id_str.startswith("RES") and "." not in id_str
