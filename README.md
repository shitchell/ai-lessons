# AI Lessons

A knowledge management system for AI agents and humans. Capture lessons learned through debugging and problem-solving, then recall them when facing similar challenges.

## Why?

When you (or an AI agent) spend an hour debugging a problem, you learn something valuable. Without a system to capture it, that knowledge is lost—and you'll re-learn the same lesson next time.

AI Lessons solves this by providing:
- **Semantic search** - Find relevant lessons even when you don't remember exact keywords
- **Hybrid retrieval** - Combines meaning-based and keyword-based search
- **Document chunking** - Intelligently splits large documents for better search results
- **Graph relationships** - Link related lessons, resources, and rules to build a knowledge web
- **Multi-agent support** - Works with Claude Code (MCP), custom CLI agents, or direct human use
- **Type-prefixed IDs** - Instantly recognize entity types (LSN for lessons, RES for resources, etc.)

## Quick Start

```bash
# Install
pip install ai-lessons[all]

# Initialize
ai-lessons admin init

# Add your first lesson
ai-lessons contribute add-lesson \
  --title "Always GET before PUT on Jira workflows" \
  --content "PUT /workflows deletes any statuses not included in the payload" \
  --tags jira,api,gotcha \
  --confidence high \
  --source tested

# Search later
ai-lessons recall search "jira workflow update"
```

## Installation

### Basic (sentence-transformers embeddings, free)
```bash
pip install ai-lessons
```

### With OpenAI embeddings (higher quality)
```bash
pip install ai-lessons[openai]
export OPENAI_API_KEY="your-api-key"
```

### With MCP server (for Claude Code)
```bash
pip install ai-lessons[mcp]
```

### Everything
```bash
pip install ai-lessons[all]
```

## Configuration

Configuration lives at `~/.ai/lessons/config.yaml`:

```yaml
# Embedding backend (sentence-transformers is free, openai is higher quality)
embedding:
  backend: sentence-transformers  # or: openai
  model: all-MiniLM-L6-v2         # or: text-embedding-3-small

# Search tuning
search:
  default_limit: 10
  hybrid_weight_semantic: 0.7
  hybrid_weight_keyword: 0.3

# Tag normalization
tag_aliases:
  js: javascript
  proj: project
```

For OpenAI embeddings, set `OPENAI_API_KEY` in your environment.

## CLI Usage

Commands are organized into three groups. Entity IDs use type prefixes for instant recognition:
- `LSN...` - Lessons
- `RES...` - Resources
- `RUL...` - Rules
- `RES....N` - Chunks (resource ID + `.N` suffix)

### `admin` - Database management
```bash
ai-lessons admin init              # Initialize database
ai-lessons admin stats             # Show statistics
ai-lessons admin merge-tags A B    # Merge tag A into B
ai-lessons admin add-source NAME   # Add new source type
ai-lessons admin pending-rules     # Review pending rules
ai-lessons admin approve-rule ID   # Approve a rule
```

### `contribute` - Add and modify
```bash
# Add lessons
ai-lessons contribute add-lesson --title "..." --content "..." --tags a,b

# Add resources (docs and scripts)
ai-lessons contribute add-resource -t doc docs/api.md --version v3
ai-lessons contribute add-resource -t script scripts/deploy.sh

# Suggest rules (require approval)
ai-lessons contribute suggest-rule --title "..." --content "..." --rationale "..."

# Unified update (works with any entity type - detected from ID prefix)
ai-lessons contribute update LSN01... --title "New title"
ai-lessons contribute update RES01... --tags new,tags --resource-version v4
ai-lessons contribute update RUL01... --rule-rationale "Better reasoning"

# Unified delete (works with any entity type)
ai-lessons contribute delete LSN01...
ai-lessons contribute delete RES01... --yes

# Unified link/unlink (any entity to any entity)
ai-lessons contribute link LSN01... LSN02... --relation derived_from
ai-lessons contribute link LSN01... RES01... --relation documents
ai-lessons contribute unlink LSN01... RES01...

# Refresh resource content from filesystem
ai-lessons contribute refresh RES01...

# Preview how a document will be chunked
ai-lessons contribute add-resource -t doc docs/guide.md --preview
```

### `recall` - Search and view
```bash
# Unified search (all types or filtered)
ai-lessons recall search "query"                           # Search all
ai-lessons recall search "query" --type lesson             # Lessons only
ai-lessons recall search "query" --type resource -g        # Resources, grouped
ai-lessons recall search "query" --lesson-confidence-min high  # Filter lessons

# Unified show (type detected from ID prefix)
ai-lessons recall show LSN01...     # Show lesson
ai-lessons recall show RES01...     # Show resource
ai-lessons recall show RES01....0   # Show chunk
ai-lessons recall show RUL01...     # Show rule

# Unified list (by type)
ai-lessons recall list --type lesson
ai-lessons recall list --type resource --resource-type script
ai-lessons recall list --type rule --rule-pending
ai-lessons recall list --type chunk --chunk-parent RES01...

# Unified related (type detected from ID prefix)
ai-lessons recall related LSN01... --depth 2
ai-lessons recall related RES01...

# Metadata commands
ai-lessons recall tags --counts
ai-lessons recall sources
ai-lessons recall confidence
```

## MCP Server (Claude Code)

Register the MCP server in your Claude Code settings:

```json
{
  "mcpServers": {
    "ai-lessons": {
      "command": "ai-lessons-mcp"
    }
  }
}
```

Then Claude can use tools like `learn`, `recall`, `get_lesson`, `link`, etc.

## Concepts

### Lessons
A lesson captures objective knowledge about causality: "If X, then Y happens."

A lesson has:
- **Title** - Short, searchable description
- **Content** - Detailed explanation
- **Tags** - Categorization (free-form)
- **Contexts** - When this applies / doesn't apply
- **Confidence** - very-low, low, medium, high, very-high
- **Source** - How you know this (tested, documented, inferred, observed, hearsay)

### Resources
Resources are documents and scripts that complement lessons:

- **Docs** - Markdown/text documents, automatically chunked for better search
- **Scripts** - Executable files that can be run via the MCP server

Documents are split into chunks at logical boundaries (headers, delimiters) so searches can find specific sections within large documents. Use `--preview` to see how a document will be chunked before adding.

### Rules
Rules are prescriptive guidance that require approval:
- **Title** - What should be done
- **Content** - How to do it
- **Rationale** - Why this outcome is desirable (required)
- **Approved** - Must be approved to surface in searches

Rules only surface when they have tag overlap with the search context, preventing false positives.

### Confidence Levels
| Level | Meaning |
|-------|---------|
| very-low | Wild guess, untested assumption |
| low | Some evidence but shaky |
| medium | Reasonable confidence, worked once |
| high | Well-tested, multiple confirmations |
| very-high | Battle-tested, extremely confident |

### Source Types
| Source | Meaning |
|--------|---------|
| tested | Ran code, verified behavior |
| documented | Official docs/specs |
| observed | Saw in logs/output |
| inferred | Reasoned from evidence |
| hearsay | Someone said so |

### Graph Edges
Link lessons, resources, and rules with relationships:
- `related_to` - General relationship
- `derived_from` - This lesson came from that one
- `contradicts` - These lessons conflict
- `supersedes` - This lesson replaces that one
- `documents` - A resource documents a lesson
- `references` - Cross-references between resources

## Architecture

### Database
- SQLite with sqlite-vec extension for vector similarity search
- Hybrid search combining semantic (vector) and keyword (FTS-like) matching
- Graph edges support any-to-any relationships between entities
- Type-prefixed IDs (LSN, RES, RUL) for instant type recognition

### Embeddings
- Pluggable backend: sentence-transformers (free) or OpenAI (higher quality)
- Resource-level and chunk-level embeddings for granular retrieval
- Automatic embedding generation on add/update

### Chunking
- Intelligent document splitting strategies:
  - **headers**: Split on markdown headers (h2, h3, etc.)
  - **delimiter**: Split on custom regex patterns
  - **fixed**: Fixed-size chunks with overlap
  - **auto**: Auto-detect best strategy
  - **single**: Keep small documents as one chunk
- Preserves document structure with breadcrumbs
- Handles oversized chunks gracefully

## Data Location

```
~/.ai/lessons/
├── knowledge.db    # SQLite database with embeddings
└── config.yaml     # Configuration
```

## Development

```bash
git clone https://github.com/shitchell/ai-lessons
cd ai-lessons
pip install -e ".[dev]"
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines and [TECHNICAL.md](TECHNICAL.md) for technical details.

## License

MIT
