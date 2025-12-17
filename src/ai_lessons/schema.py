"""Database schema definitions for ai-lessons."""

SCHEMA_VERSION = 4

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

-- v2: Resources table (docs and scripts)
CREATE TABLE IF NOT EXISTS resources (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('doc', 'script')),
    title TEXT NOT NULL,
    path TEXT,                              -- Filesystem path (required for scripts, optional for docs)
    content BLOB,                           -- Stored for docs, cached for scripts
    content_hash TEXT,                      -- For change detection
    source_ref TEXT,                        -- Git commit ref (auto-captured)
    indexed_at TIMESTAMP,                   -- When content was last indexed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- v2: Resource versions (many-to-many)
CREATE TABLE IF NOT EXISTS resource_versions (
    resource_id TEXT NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    version TEXT NOT NULL,                  -- 'v2', 'v3', 'unversioned'
    PRIMARY KEY (resource_id, version)
);

-- v2: Resource tags
CREATE TABLE IF NOT EXISTS resource_tags (
    resource_id TEXT NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (resource_id, tag)
);

-- v2: Resource chunks (for large documents)
-- v3: Added breadcrumb, start_line, end_line, token_count
-- v4: Added summary, summary_generated_at for LLM-generated summaries
CREATE TABLE IF NOT EXISTS resource_chunks (
    id TEXT PRIMARY KEY,
    resource_id TEXT NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,           -- Order within document
    title TEXT,                             -- Section title if applicable
    content TEXT NOT NULL,
    breadcrumb TEXT,                        -- Hierarchy path (e.g., "Parent > Child")
    start_line INTEGER,                     -- Starting line in source document
    end_line INTEGER,                       -- Ending line in source document
    token_count INTEGER,                    -- Estimated token count
    summary TEXT,                           -- LLM-generated summary
    summary_generated_at TIMESTAMP          -- When summary was generated (for cache invalidation)
);

-- v2: Rules table (prescriptive guidance)
CREATE TABLE IF NOT EXISTS rules (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    rationale TEXT NOT NULL,                -- Why we want this outcome (required)
    approved INTEGER DEFAULT 0,             -- Must be approved to surface
    approved_at TIMESTAMP,
    approved_by TEXT,
    suggested_by TEXT,                      -- Agent/session that suggested
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- v2: Rule tags
CREATE TABLE IF NOT EXISTS rule_tags (
    rule_id TEXT NOT NULL REFERENCES rules(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (rule_id, tag)
);

-- v2: Rule links (to lessons and resources)
CREATE TABLE IF NOT EXISTS rule_links (
    rule_id TEXT NOT NULL REFERENCES rules(id) ON DELETE CASCADE,
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('lesson', 'resource')),
    PRIMARY KEY (rule_id, target_id)
);

-- v2: Indexes for resources
CREATE INDEX IF NOT EXISTS idx_resources_type ON resources(type);
CREATE INDEX IF NOT EXISTS idx_resources_indexed ON resources(indexed_at);
CREATE INDEX IF NOT EXISTS idx_resource_versions_version ON resource_versions(version);
CREATE INDEX IF NOT EXISTS idx_resource_tags_tag ON resource_tags(tag);
CREATE INDEX IF NOT EXISTS idx_resource_chunks_resource ON resource_chunks(resource_id);

-- v2: Indexes for rules
CREATE INDEX IF NOT EXISTS idx_rules_approved ON rules(approved);
CREATE INDEX IF NOT EXISTS idx_rule_tags_tag ON rule_tags(tag);
CREATE INDEX IF NOT EXISTS idx_rule_links_target ON rule_links(target_id, target_type);
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

# v2: Vector tables for resources and chunks
RESOURCE_VECTOR_TABLE_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS resource_embeddings USING vec0(
    resource_id TEXT PRIMARY KEY,
    embedding FLOAT[{dimensions}]
);
"""

CHUNK_VECTOR_TABLE_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_embeddings USING vec0(
    chunk_id TEXT PRIMARY KEY,
    embedding FLOAT[{dimensions}]
);
"""

