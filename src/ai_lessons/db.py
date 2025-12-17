"""Database operations for ai-lessons."""

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional

# Try to use pysqlite3 which has extension loading enabled,
# fall back to standard sqlite3
try:
    import pysqlite3 as sqlite3
except ImportError:
    import sqlite3

import sqlite_vec

from .config import Config, get_config
from .schema import (
    CHUNK_VECTOR_TABLE_SQL,
    RESOURCE_VECTOR_TABLE_SQL,
    SCHEMA_SQL,
    SCHEMA_VERSION,
    SEED_CONFIDENCE_LEVELS,
    SEED_SOURCE_TYPES,
    VECTOR_TABLE_SQL,
)


def _get_connection(db_path: Path) -> sqlite3.Connection:
    """Create a database connection with sqlite-vec loaded."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    # Enable WAL mode for better concurrency
    conn.execute("PRAGMA journal_mode=WAL")
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db(config: Optional[Config] = None) -> Generator[sqlite3.Connection, None, None]:
    """Get a database connection as a context manager."""
    if config is None:
        config = get_config()

    conn = _get_connection(config.db_path)
    try:
        yield conn
    finally:
        conn.close()


def init_db(config: Optional[Config] = None, force: bool = False) -> None:
    """Initialize the database with schema and seed data.

    Args:
        config: Configuration to use. Defaults to global config.
        force: If True, recreate the vector table even if dimensions differ.
    """
    if config is None:
        config = get_config()

    # Ensure directory exists
    config.db_path.parent.mkdir(parents=True, exist_ok=True)

    with get_db(config) as conn:
        # Check if already initialized
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='meta'"
        )
        is_new = cursor.fetchone() is None

        # Create schema
        conn.executescript(SCHEMA_SQL)

        if is_new:
            # Set schema version
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

            # Seed confidence levels
            conn.executemany(
                "INSERT OR IGNORE INTO confidence_levels (name, ordinal) VALUES (?, ?)",
                SEED_CONFIDENCE_LEVELS,
            )

            # Seed source types
            conn.executemany(
                "INSERT OR IGNORE INTO source_types (name, description, typical_confidence) VALUES (?, ?, ?)",
                SEED_SOURCE_TYPES,
            )
        else:
            # Run migrations for existing databases
            _run_migrations(conn, config)

        # Create or verify vector tables
        _ensure_vector_table(conn, config, force)
        _ensure_resource_vector_tables(conn, config, force)

        conn.commit()


def _ensure_vector_table(
    conn: sqlite3.Connection, config: Config, force: bool = False
) -> None:
    """Ensure the vector table exists with correct dimensions."""
    dimensions = config.embedding.dimensions

    # Check if vector table exists
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='lesson_embeddings'"
    )
    exists = cursor.fetchone() is not None

    if exists and not force:
        # Verify dimensions match (stored in meta)
        cursor = conn.execute(
            "SELECT value FROM meta WHERE key = 'embedding_dimensions'"
        )
        row = cursor.fetchone()
        if row:
            stored_dims = int(row[0])
            if stored_dims != dimensions:
                raise ValueError(
                    f"Embedding dimensions mismatch: config has {dimensions}, "
                    f"database has {stored_dims}. Use force=True to recreate "
                    "the vector table (will require re-embedding all lessons)."
                )
        return

    if exists and force:
        # Drop and recreate
        conn.execute("DROP TABLE IF EXISTS lesson_embeddings")

    # Create vector table
    conn.execute(VECTOR_TABLE_SQL.format(dimensions=dimensions))

    # Store dimensions in meta
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('embedding_dimensions', ?)",
        (str(dimensions),),
    )


def _ensure_resource_vector_tables(
    conn: sqlite3.Connection, config: Config, force: bool = False
) -> None:
    """Ensure the resource and chunk vector tables exist."""
    dimensions = config.embedding.dimensions

    # Check if resource vector table exists
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='resource_embeddings'"
    )
    resource_exists = cursor.fetchone() is not None

    # Check if chunk vector table exists
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='chunk_embeddings'"
    )
    chunk_exists = cursor.fetchone() is not None

    if force:
        conn.execute("DROP TABLE IF EXISTS resource_embeddings")
        conn.execute("DROP TABLE IF EXISTS chunk_embeddings")
        resource_exists = False
        chunk_exists = False

    if not resource_exists:
        conn.execute(RESOURCE_VECTOR_TABLE_SQL.format(dimensions=dimensions))

    if not chunk_exists:
        conn.execute(CHUNK_VECTOR_TABLE_SQL.format(dimensions=dimensions))


def _run_migrations(conn: sqlite3.Connection, config: Config) -> None:
    """Run database migrations for existing databases."""
    # Get current schema version
    cursor = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'")
    row = cursor.fetchone()
    current_version = int(row[0]) if row else 1

    if current_version < 2:
        # v2 adds resources and rules tables (handled by SCHEMA_SQL with IF NOT EXISTS)
        current_version = 2

    if current_version < 3:
        # v3 adds new columns to resource_chunks for chunking metadata
        # Check if columns already exist (idempotent migration)
        cursor = conn.execute("PRAGMA table_info(resource_chunks)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        if "breadcrumb" not in existing_cols:
            conn.execute("ALTER TABLE resource_chunks ADD COLUMN breadcrumb TEXT")
        if "start_line" not in existing_cols:
            conn.execute("ALTER TABLE resource_chunks ADD COLUMN start_line INTEGER")
        if "end_line" not in existing_cols:
            conn.execute("ALTER TABLE resource_chunks ADD COLUMN end_line INTEGER")
        if "token_count" not in existing_cols:
            conn.execute("ALTER TABLE resource_chunks ADD COLUMN token_count INTEGER")

        current_version = 3

    if current_version < 4:
        # v4 adds summary columns to resource_chunks for LLM-generated summaries
        cursor = conn.execute("PRAGMA table_info(resource_chunks)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        if "summary" not in existing_cols:
            conn.execute("ALTER TABLE resource_chunks ADD COLUMN summary TEXT")
        if "summary_generated_at" not in existing_cols:
            conn.execute(
                "ALTER TABLE resource_chunks ADD COLUMN summary_generated_at TIMESTAMP"
            )

        current_version = 4

    # Update schema version
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )


def get_schema_version(config: Optional[Config] = None) -> Optional[int]:
    """Get the current schema version from the database."""
    if config is None:
        config = get_config()

    if not config.db_path.exists():
        return None

    with get_db(config) as conn:
        cursor = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        )
        row = cursor.fetchone()
        return int(row[0]) if row else None


def execute_query(
    query: str,
    params: tuple = (),
    config: Optional[Config] = None,
) -> list[sqlite3.Row]:
    """Execute a query and return all results."""
    if config is None:
        config = get_config()

    with get_db(config) as conn:
        cursor = conn.execute(query, params)
        return cursor.fetchall()


def execute_write(
    query: str,
    params: tuple = (),
    config: Optional[Config] = None,
) -> int:
    """Execute a write query and return rows affected."""
    if config is None:
        config = get_config()

    with get_db(config) as conn:
        cursor = conn.execute(query, params)
        conn.commit()
        return cursor.rowcount


def execute_many(
    query: str,
    params_list: list[tuple],
    config: Optional[Config] = None,
) -> None:
    """Execute a query multiple times with different parameters."""
    if config is None:
        config = get_config()

    with get_db(config) as conn:
        conn.executemany(query, params_list)
        conn.commit()
