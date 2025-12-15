"""Database schema definitions for ai-lessons."""

SCHEMA_VERSION = 1

# Schema creation SQL
SCHEMA_SQL = """
-- Metadata table
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Reference tables for enum-like fields
CREATE TABLE IF NOT EXISTS confidence_levels (
    name TEXT PRIMARY KEY,
    ordinal INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS source_types (
    name TEXT PRIMARY KEY,
    description TEXT,
    typical_confidence TEXT
);

-- Core lessons table
CREATE TABLE IF NOT EXISTS lessons (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    confidence TEXT REFERENCES confidence_levels(name),
    source TEXT REFERENCES source_types(name),
    source_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tags (many-to-many, no constraints on values)
CREATE TABLE IF NOT EXISTS lesson_tags (
    lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (lesson_id, tag)
);

-- Contexts (when does this lesson apply/not apply?)
CREATE TABLE IF NOT EXISTS lesson_contexts (
    lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    context TEXT NOT NULL,
    applies BOOLEAN DEFAULT TRUE,
    PRIMARY KEY (lesson_id, context, applies)
);

-- Graph edges between lessons
CREATE TABLE IF NOT EXISTS edges (
    from_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    to_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    relation TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (from_id, to_id, relation)
);

-- Tag relationships (aliases, hierarchy)
CREATE TABLE IF NOT EXISTS tag_relations (
    from_tag TEXT NOT NULL,
    to_tag TEXT NOT NULL,
    relation TEXT NOT NULL,
    PRIMARY KEY (from_tag, to_tag, relation)
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_lesson_tags_tag ON lesson_tags(tag);
CREATE INDEX IF NOT EXISTS idx_lesson_tags_lesson ON lesson_tags(lesson_id);
CREATE INDEX IF NOT EXISTS idx_lesson_contexts_context ON lesson_contexts(context);
CREATE INDEX IF NOT EXISTS idx_lesson_contexts_lesson ON lesson_contexts(lesson_id);
CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_id);
CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_id);
CREATE INDEX IF NOT EXISTS idx_lessons_created ON lessons(created_at);
CREATE INDEX IF NOT EXISTS idx_lessons_updated ON lessons(updated_at);
CREATE INDEX IF NOT EXISTS idx_lessons_confidence ON lessons(confidence);
CREATE INDEX IF NOT EXISTS idx_lessons_source ON lessons(source);
"""

# Seed data for reference tables
SEED_CONFIDENCE_LEVELS = [
    ("very-low", 1),
    ("low", 2),
    ("medium", 3),
    ("high", 4),
    ("very-high", 5),
]

SEED_SOURCE_TYPES = [
    ("inferred", "Reasoned from evidence", "low-medium"),
    ("tested", "Ran code, verified behavior", "high"),
    ("documented", "Official docs/specs", "medium-high"),
    ("observed", "Saw in logs/output", "medium"),
    ("hearsay", "Someone said so", "low"),
]

# Vector table creation (separate because it uses sqlite-vec extension)
# The dimension is configurable based on embedding model
VECTOR_TABLE_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS lesson_embeddings USING vec0(
    lesson_id TEXT PRIMARY KEY,
    embedding FLOAT[{dimensions}]
);
"""
