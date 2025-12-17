"""Configuration management for ai-lessons."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


# Default paths
DEFAULT_AI_DIR = Path.home() / ".ai"
DEFAULT_LESSONS_DIR = DEFAULT_AI_DIR / "lessons"
DEFAULT_DB_PATH = DEFAULT_LESSONS_DIR / "knowledge.db"
DEFAULT_CONFIG_PATH = DEFAULT_LESSONS_DIR / "config.yaml"


@dataclass
class EmbeddingConfig:
    """Embedding model configuration."""
    backend: str = "sentence-transformers"
    model: str = "all-MiniLM-L6-v2"
    api_key: Optional[str] = None
    dimensions: Optional[int] = None  # Auto-detected if not specified

    def __post_init__(self):
        # Resolve environment variables in api_key
        if self.api_key and self.api_key.startswith("${") and self.api_key.endswith("}"):
            env_var = self.api_key[2:-1]
            self.api_key = os.environ.get(env_var)

        # Default dimensions based on model
        if self.dimensions is None:
            self.dimensions = self._default_dimensions()

    def _default_dimensions(self) -> int:
        """Return default dimensions for known models."""
        known_dimensions = {
            # sentence-transformers
            "all-MiniLM-L6-v2": 384,
            "all-mpnet-base-v2": 768,
            "paraphrase-MiniLM-L6-v2": 384,
            # OpenAI
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        return known_dimensions.get(self.model, 384)


@dataclass
class SearchConfig:
    """Search configuration."""
    default_limit: int = 10
    hybrid_weight_semantic: float = 0.7
    hybrid_weight_keyword: float = 0.3


@dataclass
class SummaryConfig:
    """LLM summary generation configuration."""
    backend: Optional[str] = None  # "anthropic", "openai", or None (disabled)
    model: Optional[str] = None  # e.g., "claude-3-haiku-20240307", "gpt-4o-mini"
    api_key: Optional[str] = None

    def __post_init__(self):
        # Resolve environment variables in api_key
        if self.api_key and self.api_key.startswith("${") and self.api_key.endswith("}"):
            env_var = self.api_key[2:-1]
            self.api_key = os.environ.get(env_var)

    @property
    def enabled(self) -> bool:
        """Check if summary generation is configured."""
        return bool(self.backend and self.model)


@dataclass
class Config:
    """Main configuration."""
    db_path: Path = DEFAULT_DB_PATH
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    summaries: SummaryConfig = field(default_factory=SummaryConfig)
    tag_aliases: dict[str, str] = field(default_factory=dict)
    known_tags: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "Config":
        """Load configuration from YAML file."""
        if config_path is None:
            config_path = DEFAULT_CONFIG_PATH

        if not config_path.exists():
            return cls()

        with open(config_path) as f:
            data = yaml.safe_load(f) or {}

        # Parse embedding config
        embedding_data = data.get("embedding", {})
        embedding = EmbeddingConfig(
            backend=embedding_data.get("backend", "sentence-transformers"),
            model=embedding_data.get("model", "all-MiniLM-L6-v2"),
            api_key=embedding_data.get("api_key"),
            dimensions=embedding_data.get("dimensions"),
        )

        # Parse search config
        search_data = data.get("search", {})
        search = SearchConfig(
            default_limit=search_data.get("default_limit", 10),
            hybrid_weight_semantic=search_data.get("hybrid_weight_semantic", 0.7),
            hybrid_weight_keyword=search_data.get("hybrid_weight_keyword", 0.3),
        )

        # Parse summaries config
        summaries_data = data.get("summaries", {})
        summaries = SummaryConfig(
            backend=summaries_data.get("backend"),
            model=summaries_data.get("model"),
            api_key=summaries_data.get("api_key"),
        )

        # Parse db_path if specified
        db_path = DEFAULT_DB_PATH
        if "db_path" in data:
            db_path = Path(data["db_path"]).expanduser()

        return cls(
            db_path=db_path,
            embedding=embedding,
            search=search,
            summaries=summaries,
            tag_aliases=data.get("tag_aliases", {}),
            known_tags=data.get("known_tags", []),
        )

    def save(self, config_path: Optional[Path] = None) -> None:
        """Save configuration to YAML file."""
        if config_path is None:
            config_path = DEFAULT_CONFIG_PATH

        config_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "embedding": {
                "backend": self.embedding.backend,
                "model": self.embedding.model,
            },
            "search": {
                "default_limit": self.search.default_limit,
                "hybrid_weight_semantic": self.search.hybrid_weight_semantic,
                "hybrid_weight_keyword": self.search.hybrid_weight_keyword,
            },
        }

        if self.embedding.api_key:
            data["embedding"]["api_key"] = self.embedding.api_key
        if self.embedding.dimensions:
            data["embedding"]["dimensions"] = self.embedding.dimensions

        # Add summaries config if configured
        if self.summaries.enabled:
            data["summaries"] = {
                "backend": self.summaries.backend,
                "model": self.summaries.model,
            }
            if self.summaries.api_key:
                data["summaries"]["api_key"] = self.summaries.api_key

        if self.tag_aliases:
            data["tag_aliases"] = self.tag_aliases
        if self.known_tags:
            data["known_tags"] = self.known_tags

        with open(config_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)


# Global config instance (lazy loaded)
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config.load()
    return _config


def reload_config() -> Config:
    """Reload configuration from disk."""
    global _config
    _config = Config.load()
    return _config
