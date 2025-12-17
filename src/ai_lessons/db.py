"""Database operations for ai-lessons."""

from __future__ import annotations

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

    if current_version < 5:
        # v5 adds sections column to resource_chunks and resource_links table
        cursor = conn.execute("PRAGMA table_info(resource_chunks)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        if "sections" not in existing_cols:
            conn.execute("ALTER TABLE resource_chunks ADD COLUMN sections TEXT")

        # Create resource_links table if not exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS resource_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_resource_id TEXT NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
                from_chunk_id TEXT REFERENCES resource_chunks(id) ON DELETE CASCADE,
                to_path TEXT NOT NULL,
                to_fragment TEXT,
                link_text TEXT,
                resolved_resource_id TEXT REFERENCES resources(id) ON DELETE SET NULL,
                resolved_chunk_id TEXT REFERENCES resource_chunks(id) ON DELETE SET NULL
            )
        """)

        # Create indexes
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_resource_links_to_path ON resource_links(to_path)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_resource_links_from_resource ON resource_links(from_resource_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_resource_links_resolved ON resource_links(resolved_resource_id)"
        )

        current_version = 5

    if current_version < 6:
        # v6 adds lesson_links table for lesson-to-resource linking
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lesson_links (
                lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
                resource_id TEXT NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
                relation TEXT NOT NULL DEFAULT 'related_to',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (lesson_id, resource_id)
            )
        """)

        # Create indexes
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lesson_links_lesson ON lesson_links(lesson_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lesson_links_resource ON lesson_links(resource_id)"
        )

        current_version = 6

    if current_version < 7:
        # v7 adds search_feedback table for quality monitoring
        conn.execute("""
            CREATE TABLE IF NOT EXISTS search_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT NOT NULL,
                queries TEXT NOT NULL,
                invocation_count INTEGER NOT NULL,
                suggestion TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_search_feedback_created ON search_feedback(created_at)"
        )

        current_version = 7

    if current_version < 8:
        # v8 adds version column to search_feedback table
        cursor = conn.execute("PRAGMA table_info(search_feedback)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        if "version" not in existing_cols:
            conn.execute("ALTER TABLE search_feedback ADD COLUMN version TEXT")

        current_version = 8

    if current_version < 9:
        # v9: Unify link tables into edges, rename resource_links to resource_anchors

        # 1. Create new edges table structure
        conn.execute("""
            CREATE TABLE IF NOT EXISTS edges_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_id TEXT NOT NULL,
                from_type TEXT NOT NULL CHECK (from_type IN ('lesson', 'resource', 'chunk')),
                to_id TEXT NOT NULL,
                to_type TEXT NOT NULL CHECK (to_type IN ('lesson', 'resource', 'chunk')),
                relation TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(from_id, from_type, to_id, to_type, relation)
            )
        """)

        # 2. Migrate existing edges (lesson→lesson)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='edges'")
        if cursor.fetchone():
            conn.execute("""
                INSERT INTO edges_new (from_id, from_type, to_id, to_type, relation, created_at)
                SELECT from_id, 'lesson', to_id, 'lesson', relation, created_at
                FROM edges
            """)

        # 3. Migrate lesson_links (lesson→resource)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lesson_links'")
        if cursor.fetchone():
            conn.execute("""
                INSERT INTO edges_new (from_id, from_type, to_id, to_type, relation, created_at)
                SELECT lesson_id, 'lesson', resource_id, 'resource', relation, created_at
                FROM lesson_links
            """)
            conn.execute("DROP TABLE lesson_links")

        # 4. Create resource_anchors table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS resource_anchors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                edge_id INTEGER REFERENCES edges_new(id) ON DELETE CASCADE,
                to_path TEXT NOT NULL,
                to_fragment TEXT,
                link_text TEXT
            )
        """)

        # 5. Migrate resource_links to edges + resource_anchors
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='resource_links'")
        if cursor.fetchone():
            # Get all resource_links with resolved targets
            cursor = conn.execute("""
                SELECT id, from_resource_id, from_chunk_id, to_path, to_fragment, link_text,
                       resolved_resource_id, resolved_chunk_id
                FROM resource_links
                WHERE resolved_resource_id IS NOT NULL
            """)

            for row in cursor.fetchall():
                # Determine from_type and from_id
                if row["from_chunk_id"]:
                    from_id = row["from_chunk_id"]
                    from_type = "chunk"
                else:
                    from_id = row["from_resource_id"]
                    from_type = "resource"

                # Determine to_type and to_id
                if row["resolved_chunk_id"]:
                    to_id = row["resolved_chunk_id"]
                    to_type = "chunk"
                else:
                    to_id = row["resolved_resource_id"]
                    to_type = "resource"

                # Insert edge
                conn.execute("""
                    INSERT OR IGNORE INTO edges_new (from_id, from_type, to_id, to_type, relation)
                    VALUES (?, ?, ?, ?, 'references')
                """, (from_id, from_type, to_id, to_type))

                # Get the edge ID
                edge_cursor = conn.execute("""
                    SELECT id FROM edges_new
                    WHERE from_id = ? AND from_type = ? AND to_id = ? AND to_type = ? AND relation = 'references'
                """, (from_id, from_type, to_id, to_type))
                edge_row = edge_cursor.fetchone()

                if edge_row:
                    # Insert anchor metadata
                    conn.execute("""
                        INSERT INTO resource_anchors (edge_id, to_path, to_fragment, link_text)
                        VALUES (?, ?, ?, ?)
                    """, (edge_row["id"], row["to_path"], row["to_fragment"], row["link_text"]))

            conn.execute("DROP TABLE resource_links")

        # 6. Replace old edges table
        conn.execute("DROP TABLE IF EXISTS edges")
        conn.execute("ALTER TABLE edges_new RENAME TO edges")

        # 7. Create indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_id, from_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_id, to_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_resource_anchors_edge ON resource_anchors(edge_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_resource_anchors_path ON resource_anchors(to_path)")

        current_version = 9

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
