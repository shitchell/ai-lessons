"""Embedding backends for ai-lessons."""

from __future__ import annotations

import os
import threading
from abc import ABC, abstractmethod
from typing import Optional

from .config import Config, EmbeddingConfig, get_config


class EmbeddingBackend(ABC):
    """Abstract base class for embedding backends."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Generate an embedding for the given text."""
        pass

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        pass

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Return the embedding dimensions."""
        pass


class SentenceTransformersBackend(EmbeddingBackend):
    """Embedding backend using sentence-transformers."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", device: str = None):
        self.model_name = model_name
        self.device = device
        self._model = None

    @property
    def model(self):
        """Lazy load the model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            # Use CPU by default to avoid CUDA compatibility issues
            device = self.device or "cpu"
            self._model = SentenceTransformer(self.model_name, device=device)
        return self._model

    def embed(self, text: str) -> list[float]:
        """Generate an embedding for the given text."""
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return [e.tolist() for e in embeddings]

    @property
    def dimensions(self) -> int:
        """Return the embedding dimensions."""
        return self.model.get_sentence_embedding_dimension()


class OpenAIBackend(EmbeddingBackend):
    """Embedding backend using OpenAI API."""

    def __init__(
        self,
        model_name: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
    ):
        self.model_name = model_name
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._client = None
        self._dimensions = self._get_model_dimensions()

    def _get_model_dimensions(self) -> int:
        """Return dimensions for known OpenAI models."""
        known_dimensions = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        return known_dimensions.get(self.model_name, 1536)

    def _validate_api_key(self, client) -> None:
        """Validate API key by calling a free endpoint.

        Raises:
            ValueError: If API key is invalid or missing.
        """
        if not self.api_key:
            raise ValueError(
                "OpenAI API key not provided. Set via config or OPENAI_API_KEY environment variable."
            )
        try:
            # List models is a free endpoint (no tokens consumed)
            client.models.list()
        except Exception as e:
            error_msg = str(e).lower()
            if "invalid" in error_msg or "api key" in error_msg or "unauthorized" in error_msg:
                raise ValueError(
                    f"Invalid OpenAI API key: {e}"
                ) from e
            # Other errors (network, etc.) - re-raise as-is
            raise

    @property
    def client(self):
        """Lazy load the OpenAI client and validate API key on first use."""
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError(
                    "OpenAI backend requires the 'openai' package. "
                    "Install with: pip install ai-lessons[openai]"
                )
            self._client = OpenAI(api_key=self.api_key)
            self._validate_api_key(self._client)
        return self._client

    def embed(self, text: str) -> list[float]:
        """Generate an embedding for the given text."""
        response = self.client.embeddings.create(
            model=self.model_name,
            input=text,
        )
        return response.data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        response = self.client.embeddings.create(
            model=self.model_name,
            input=texts,
        )
        # Sort by index to ensure order matches input
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [d.embedding for d in sorted_data]

    @property
    def dimensions(self) -> int:
        """Return the embedding dimensions."""
        return self._dimensions


def get_embedder(config: Optional[Config] = None) -> EmbeddingBackend:
    """Get the appropriate embedding backend based on configuration."""
    if config is None:
        config = get_config()

    embedding_config = config.embedding

    if embedding_config.backend == "sentence-transformers":
        return SentenceTransformersBackend(model_name=embedding_config.model)
    elif embedding_config.backend == "openai":
        return OpenAIBackend(
            model_name=embedding_config.model,
            api_key=embedding_config.api_key,
        )
    else:
        raise ValueError(f"Unknown embedding backend: {embedding_config.backend}")


# Global embedder instance (lazy loaded) with thread safety
_embedder: Optional[EmbeddingBackend] = None
_embedder_lock = threading.Lock()


def embed_text(text: str, config: Optional[Config] = None) -> list[float]:
    """Generate an embedding for the given text using the configured backend."""
    global _embedder
    with _embedder_lock:
        if _embedder is None or config is not None:
            # Reinitialize if config is explicitly provided
            _embedder = get_embedder(config)
        embedder = _embedder
    return embedder.embed(text)


def embed_batch(texts: list[str], config: Optional[Config] = None) -> list[list[float]]:
    """Generate embeddings for multiple texts using the configured backend."""
    global _embedder
    with _embedder_lock:
        if _embedder is None:
            _embedder = get_embedder(config)
        embedder = _embedder
    return embedder.embed_batch(texts)


def reload_embedder(config: Optional[Config] = None) -> None:
    """Reload the embedder with new configuration."""
    global _embedder
    _embedder = get_embedder(config)
