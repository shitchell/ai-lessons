# Contributing to AI Lessons

Thank you for your interest in contributing to AI Lessons! This document provides guidelines for contributing to the project.

## Getting Started

### Setting Up Your Development Environment

1. **Clone the repository**
   ```bash
   git clone https://github.com/shitchell/ai-lessons
   cd ai-lessons
   ```

2. **Install in development mode**
   ```bash
   pip install -e ".[dev]"
   ```

   This installs the package in editable mode with development dependencies.

3. **Initialize a test database**
   ```bash
   ai-lessons admin init
   ```

### Project Structure

```
ai-lessons/
├── src/ai_lessons/          # Main package
│   ├── __init__.py          # Public API
│   ├── config.py            # Configuration management
│   ├── db.py                # Database operations
│   ├── schema.py            # Database schema
│   ├── core.py              # Core API (lessons, resources, rules)
│   ├── embeddings.py        # Embedding backends
│   ├── search.py            # Search functionality
│   ├── chunking.py          # Document chunking
│   ├── links.py             # Link extraction and resolution
│   ├── chunk_ids.py         # Chunk ID utilities
│   ├── summaries.py         # LLM-based summarization
│   ├── mcp_server.py        # MCP server for Claude Code
│   └── cli/                 # CLI commands
│       ├── admin.py         # Database management
│       ├── contribute.py    # Add/modify entities
│       ├── recall.py        # Search and view
│       ├── display.py       # Output formatting
│       └── utils.py         # CLI utilities
├── tests/                   # Test suite
├── pyproject.toml           # Package configuration
├── README.md                # User documentation
├── CONTRIBUTING.md          # This file
└── TECHNICAL.md             # Technical documentation
```

## Development Workflow

### Running Tests

```bash
pytest
```

Tests are located in the `tests/` directory and use pytest.

### Code Style

The project follows standard Python conventions:
- Use type hints for function signatures
- Write docstrings for public functions and classes
- Keep functions focused and reasonably sized
- Use descriptive variable names

### Testing Your Changes

1. **Manual testing with CLI**
   ```bash
   # Add a test lesson
   ai-lessons contribute add-lesson \
     --title "Test lesson" \
     --content "Test content" \
     --tags test

   # Search for it
   ai-lessons recall search "test"
   ```

2. **Test with MCP server**
   If you're making changes to the MCP server, test it with Claude Code:
   ```bash
   ai-lessons-mcp
   ```

3. **Run automated tests**
   ```bash
   pytest tests/
   ```

## Types of Contributions

### Bug Fixes

1. Search the issue tracker to see if the bug has been reported
2. If not, create a new issue describing the bug
3. Fork the repository and create a branch for your fix
4. Write a test that reproduces the bug
5. Fix the bug and ensure the test passes
6. Submit a pull request

### New Features

1. Open an issue to discuss the feature before implementing
2. Once approved, fork the repository and create a feature branch
3. Implement the feature with tests
4. Update documentation as needed
5. Submit a pull request

### Documentation Improvements

Documentation improvements are always welcome! This includes:
- Fixing typos or unclear wording
- Adding examples
- Improving API documentation
- Writing tutorials or guides

### Adding Embedding Backends

To add a new embedding backend:

1. Create a new class in `embeddings.py` that implements `EmbeddingBackend`:
   ```python
   class YourBackend(EmbeddingBackend):
       def embed(self, text: str) -> list[float]:
           # Your implementation
           pass

       def embed_batch(self, texts: list[str]) -> list[list[float]]:
           # Your implementation
           pass

       @property
       def dimensions(self) -> int:
           # Return embedding dimensions
           pass
   ```

2. Update `get_embedder()` to support your backend
3. Add configuration options to `config.py`
4. Add optional dependencies to `pyproject.toml`
5. Update documentation

### Adding Chunking Strategies

To add a new chunking strategy:

1. Add your strategy to `chunking.py`:
   ```python
   def chunk_by_your_strategy(content: str, config: ChunkingConfig) -> list[Chunk]:
       # Your implementation
       pass
   ```

2. Update `chunk_document()` to dispatch to your strategy
3. Update `detect_strategy()` if it should be auto-detected
4. Add tests
5. Update documentation

## Database Schema Changes

When making schema changes:

1. **Increment `SCHEMA_VERSION`** in `schema.py`
2. **Add migration logic** in `_run_migrations()` in `db.py`:
   ```python
   if current_version < N:
       # Your migration logic
       # Use IF NOT EXISTS for idempotency
       conn.execute("ALTER TABLE ...")
       current_version = N
   ```
3. **Test migrations** with existing databases
4. **Document breaking changes** in the commit message

### Schema Migration Guidelines

- Migrations should be idempotent (safe to run multiple times)
- Use `IF NOT EXISTS` and `IF NOT FOUND` checks
- Test with databases at various schema versions
- Consider backwards compatibility when possible
- Document any breaking changes clearly

## Pull Request Process

1. **Fork the repository** and create a branch from `main`
2. **Make your changes** with clear, descriptive commits
3. **Update tests** - ensure all tests pass
4. **Update documentation** - README, docstrings, etc.
5. **Submit a pull request** with a clear description of the changes

### Pull Request Guidelines

- Keep PRs focused on a single feature or fix
- Write clear commit messages
- Update relevant documentation
- Add tests for new functionality
- Ensure all tests pass
- Respond to review feedback promptly

## Commit Messages

Write clear, descriptive commit messages:

```
Short summary (50 chars or less)

More detailed explanation if needed. Wrap at 72 characters.
Explain what changed and why, not how (the code shows how).

- Bullet points are okay
- Use present tense ("Add feature" not "Added feature")
- Reference issues: "Fixes #123"
```

## Code Review

All submissions require review. We use GitHub pull requests for this purpose. Reviewers will look for:

- Code quality and style
- Test coverage
- Documentation completeness
- Backwards compatibility
- Performance implications

## Release Process

Releases are managed by maintainers:

1. Version number is updated in `pyproject.toml`
2. CHANGELOG is updated
3. Git tag is created
4. Package is published to PyPI

## Getting Help

- Open an issue for bugs or feature requests
- Ask questions in discussions
- Check existing documentation and issues first

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Code of Conduct

Be respectful and constructive in all interactions. We aim to foster an inclusive and welcoming community.
