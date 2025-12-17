# Contributing Resources to ai-lessons

This guide covers how to prepare and add documentation resources to ai-lessons for optimal chunking and retrieval.

## Overview

ai-lessons uses semantic search to find relevant knowledge. The quality of search results depends heavily on how documents are structured before import. Well-structured docs:

- **Chunk cleanly** at logical boundaries
- **Embed meaningfully** with clear topic signals
- **Retrieve accurately** when queries match section titles/content

## The Theory: Why Structure Matters

### How Chunking Works

Large documents are split into smaller "chunks" for embedding. Each chunk becomes a searchable unit. The chunking strategy determines where splits happen:

| Strategy | How It Works | Best For |
|----------|--------------|----------|
| **Header-based** | Split on markdown headers (`##`, `###`) | Structured docs (recommended) |
| **Delimiter-based** | Split on patterns (`---`, blank lines) | Semi-structured docs |
| **Fixed-size** | Split every N tokens with overlap | Unstructured text (fallback) |

**Key insight**: Header-based chunking on well-structured markdown is "often the single biggest and easiest improvement" for RAG systems ([source](https://unstructured.io/blog/chunking-for-rag-best-practices)).

### Optimal Chunk Characteristics

Good chunks are:

1. **Self-contained** - Understandable without reading other chunks
2. **Focused** - One topic/task per chunk
3. **Titled well** - Header describes the content (aids retrieval)
4. **Right-sized** - 250-800 tokens (~1-3KB) is the sweet spot

### The Diátaxis Framework

Technical documentation generally falls into four types, each with different optimal structures:

| Type | Purpose | User's Question | Structure |
|------|---------|-----------------|-----------|
| **Tutorial** | Learning | "Can you teach me...?" | Step-by-step journey |
| **How-to** | Task completion | "How do I...?" | Problem → Solution steps |
| **Reference** | Information lookup | "What is/are...?" | Structured, complete |
| **Explanation** | Understanding | "Why does...?" | Conceptual, discursive |

See [diataxis.fr](https://diataxis.fr/) for the full framework.

## Document Templates

We provide templates optimized for ai-lessons chunking:

| Template | Use For | Example |
|----------|---------|---------|
| [api-reference.md](examples/api-reference.md) | API endpoints, functions, methods | Jira API docs |
| [how-to.md](examples/how-to.md) | Task-oriented guides | "How to duplicate a workflow" |
| [troubleshooting.md](examples/troubleshooting.md) | Error resolution guides | "Error X: how to fix" |
| [conceptual.md](examples/conceptual.md) | Explanatory content | "How workflows work" |

### Key Principles Across All Templates

1. **`##` headers = chunk boundaries** - Each `##` section should be self-contained
2. **Task-oriented titles** - "Creating a workflow" > "Workflows"
3. **Lead with context** - Start sections with "When to use" or "Use this when"
4. **Examples inline** - Keep code examples with their explanations
5. **~300-800 tokens per section** - Split if longer, merge if shorter

## Adding Resources

### Quick Start

```bash
# Add a markdown document (auto-chunks based on structure)
ai-lessons contribute add-resource \
  --type doc \
  --path /path/to/document.md \
  --title "Document Title" \
  --version v3 \
  --tags topic,subtopic

# Add a script (no chunking, kept as reference)
ai-lessons contribute add-resource \
  --type script \
  --path /path/to/script.sh \
  --title "Script Description" \
  --tags topic,subtopic
```

Documents are automatically chunked for better search retrieval. Each chunk is embedded separately, allowing searches to find specific sections within large documents.

### Converting Other Formats

ai-lessons accepts markdown and plain text. For other formats:

**PDF to Markdown:**
```bash
# Using pandoc (good for most PDFs)
pandoc document.pdf -o document.md

# Using marker (ML-based, best quality for complex layouts)
marker document.pdf --output document.md
```

**After conversion**, review the output and:
1. Add `##` headers at logical section boundaries
2. Remove conversion artifacts (page numbers, headers/footers)
3. Ensure code blocks are properly fenced

### Chunking Configuration

Use `--preview` to see how a document will be chunked before adding:

```bash
# Preview chunking (dry run, doesn't store anything)
ai-lessons contribute add-resource \
  --type doc \
  --path /path/to/document.md \
  --title "Document Title" \
  --preview
```

The preview shows each chunk with its breadcrumb, token count, and any warnings about oversized or undersized chunks.

#### Chunking Options

| Option | Default | Description |
|--------|---------|-------------|
| `--chunk-strategy` | `auto` | Strategy: `auto`, `headers`, `delimiter`, `fixed`, `none` |
| `--chunk-min-size` | `100` | Minimum chunk size in tokens |
| `--chunk-max-size` | `800` | Maximum chunk size in tokens |
| `--chunk-header-levels` | `2,3` | Header levels to split on (comma-separated) |
| `--chunk-delimiter` | — | Custom delimiter pattern (regex) |

#### Chunking Strategies

**`auto` (default)**: Automatically detects the best strategy:
- Uses `headers` if document has 3+ markdown headers
- Uses `delimiter` if document has 3+ horizontal rules (`---`)
- Falls back to `fixed` for unstructured text
- Uses `none` for very small documents

**`headers`**: Splits on markdown headers (`##`, `###`, etc.)
```bash
ai-lessons contribute add-resource \
  --type doc \
  --path api-docs.md \
  --title "API Documentation" \
  --chunk-strategy headers \
  --chunk-header-levels 2,3  # Split on h2 and h3
```

**`delimiter`**: Splits on a regex pattern
```bash
ai-lessons contribute add-resource \
  --type doc \
  --path document.md \
  --title "Document" \
  --chunk-strategy delimiter \
  --chunk-delimiter "^---+$"  # Split on horizontal rules
```

**`fixed`**: Splits every N tokens with overlap (useful for unstructured text)
```bash
ai-lessons contribute add-resource \
  --type doc \
  --path raw-text.txt \
  --title "Raw Text" \
  --chunk-strategy fixed \
  --chunk-max-size 500
```

**`none`**: No chunking (stores document as single unit)
```bash
ai-lessons contribute add-resource \
  --type doc \
  --path small-doc.md \
  --title "Small Document" \
  --chunk-strategy none
```

#### Example: Previewing and Tuning Chunks

```bash
# 1. Preview with default settings
ai-lessons contribute add-resource \
  --type doc --path guide.md --title "Guide" --preview

# Output shows:
# Document: guide.md
# Strategy: headers (auto-detected)
# Chunks: 5
#   0   150  Introduction
#   1   890  Getting Started > Installation   <- oversized!
#   2   320  Getting Started > Configuration
#   ...

# 2. Adjust max size and re-preview
ai-lessons contribute add-resource \
  --type doc --path guide.md --title "Guide" \
  --chunk-max-size 500 --preview

# 3. When satisfied, add without --preview
ai-lessons contribute add-resource \
  --type doc --path guide.md --title "Guide" \
  --chunk-max-size 500 --version v3 --tags guide,setup
```

## Best Practices

### Do

- Use descriptive `##` headers that could match search queries
- Include "when to use" context at the start of sections
- Keep examples adjacent to the concepts they illustrate
- Use consistent terminology throughout

### Don't

- Create sections shorter than ~100 tokens (merge them)
- Create sections longer than ~1000 tokens (split them)
- Put all examples in a separate "Examples" section
- Use vague headers like "Overview" or "More Information"

## Further Reading

- [Diátaxis Framework](https://diataxis.fr/) - Documentation type theory
- [Chunking for RAG Best Practices](https://unstructured.io/blog/chunking-for-rag-best-practices) - Unstructured.io
- [Best Chunking Strategies 2025](https://www.firecrawl.dev/blog/best-chunking-strategies-rag-2025) - Firecrawl
