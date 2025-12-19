"""Tests for chunk ID utilities."""

import pytest
from ai_lessons.chunk_ids import (
    generate_chunk_id,
    parse_chunk_id,
    is_chunk_id,
    is_resource_id,
    ParsedChunkId,
)


class TestChunkIdGeneration:
    def test_generate_basic(self):
        assert generate_chunk_id("ABC123", 0) == "ABC123.0"
        assert generate_chunk_id("ABC123", 5) == "ABC123.5"

    def test_generate_full_ulid(self):
        ulid = "01KCPN9VWAZNSKYVHPCWVPXA2C"
        assert generate_chunk_id(ulid, 0) == f"{ulid}.0"
        assert generate_chunk_id(ulid, 99) == f"{ulid}.99"

    def test_generate_large_index(self):
        """Chunk indices can be large for heavily chunked documents."""
        assert generate_chunk_id("ABC123", 100) == "ABC123.100"
        assert generate_chunk_id("ABC123", 999) == "ABC123.999"


class TestChunkIdParsing:
    def test_parse_valid(self):
        result = parse_chunk_id("ABC123.5")
        assert result == ParsedChunkId(resource_id="ABC123", chunk_index=5)

    def test_parse_zero_index(self):
        result = parse_chunk_id("ABC123.0")
        assert result is not None
        assert result.resource_id == "ABC123"
        assert result.chunk_index == 0

    def test_parse_full_ulid(self):
        ulid = "01KCPN9VWAZNSKYVHPCWVPXA2C"
        result = parse_chunk_id(f"{ulid}.42")
        assert result is not None
        assert result.resource_id == ulid
        assert result.chunk_index == 42

    def test_parse_invalid_no_dot(self):
        assert parse_chunk_id("ABC123") is None

    def test_parse_invalid_non_numeric(self):
        assert parse_chunk_id("ABC123.xyz") is None

    def test_parse_invalid_negative_index(self):
        assert parse_chunk_id("ABC123.-1") is None

    def test_parse_invalid_empty_resource_id(self):
        assert parse_chunk_id(".5") is None

    def test_parse_invalid_float_index(self):
        assert parse_chunk_id("ABC123.5.5") is None

    def test_chunk_id_property(self):
        """ParsedChunkId.chunk_id should reconstruct the original ID."""
        parsed = parse_chunk_id("ABC123.5")
        assert parsed is not None
        assert parsed.chunk_id == "ABC123.5"


class TestIdTypeChecks:
    def test_is_chunk_id_valid(self):
        assert is_chunk_id("ABC123.0") is True
        assert is_chunk_id("ABC123.5") is True
        assert is_chunk_id("01KCPN9VWAZNSKYVHPCWVPXA2C.99") is True

    def test_is_chunk_id_invalid(self):
        assert is_chunk_id("ABC123") is False
        assert is_chunk_id("ABC123.xyz") is False
        assert is_chunk_id("") is False

    def test_is_resource_id_valid(self):
        assert is_resource_id("RES01KCPN9VWAZNSKYVHPCWVPXA2C") is True
        assert is_resource_id("RESABC123") is True

    def test_is_resource_id_invalid(self):
        assert is_resource_id("ABC123") is False  # Missing RES prefix
        assert is_resource_id("RES01KCPN9VWAZNSKYVHPCWVPXA2C.0") is False  # Has chunk suffix
        assert is_resource_id("RES01KCPN9VWAZNSKYVHPCWVPXA2C.5") is False  # Has chunk suffix


class TestRoundTrip:
    def test_generate_then_parse(self):
        """Generated IDs should be parseable."""
        resource_id = "01KCPN9VWAZNSKYVHPCWVPXA2C"
        chunk_index = 42

        chunk_id = generate_chunk_id(resource_id, chunk_index)
        parsed = parse_chunk_id(chunk_id)

        assert parsed is not None
        assert parsed.resource_id == resource_id
        assert parsed.chunk_index == chunk_index
        assert parsed.chunk_id == chunk_id
