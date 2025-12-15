# AI Lessons

A knowledge management system for AI agents and humans. Capture lessons learned through debugging and problem-solving, then recall them when facing similar challenges.

## Why?

When you (or an AI agent) spend an hour debugging a problem, you learn something valuable. Without a system to capture it, that knowledge is lost—and you'll re-learn the same lesson next time.

AI Lessons solves this by providing:
- **Semantic search** - Find relevant lessons even when you don't remember exact keywords
- **Hybrid retrieval** - Combines meaning-based and keyword-based search
- **Graph relationships** - Link related lessons to build a knowledge web
- **Multi-agent support** - Works with Claude Code (MCP), custom CLI agents, or direct human use

## Quick Start

```bash
# Install
pip install ai-lessons[all]

# Initialize
ai-lessons admin init

# Add your first lesson
ai-lessons learn add \
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

Commands are organized into three groups:

### `admin` - Database management
```bash
ai-lessons admin init              # Initialize database
ai-lessons admin stats             # Show statistics
ai-lessons admin merge-tags A B    # Merge tag A into B
ai-lessons admin add-source NAME   # Add new source type
```

### `learn` - Create and modify
```bash
ai-lessons learn add --title "..." --content "..." --tags a,b
ai-lessons learn update ID --confidence high
ai-lessons learn delete ID
ai-lessons learn link ID1 ID2 --relation derived_from
ai-lessons learn unlink ID1 ID2
```

### `recall` - Search and view
```bash
ai-lessons recall search "query" --tags api --limit 5
ai-lessons recall show ID
ai-lessons recall related ID --depth 2
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
A lesson has:
- **Title** - Short, searchable description
- **Content** - Detailed explanation
- **Tags** - Categorization (free-form)
- **Contexts** - When this applies / doesn't apply
- **Confidence** - very-low, low, medium, high, very-high
- **Source** - How you know this (tested, documented, inferred, observed, hearsay)

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
Link lessons with relationships:
- `related_to` - General relationship
- `derived_from` - This lesson came from that one
- `contradicts` - These lessons conflict
- `supersedes` - This lesson replaces that one

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

## License

MIT
