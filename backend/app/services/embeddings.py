"""Embedding service.

Anthropic (our primary LLM provider) has no embeddings API, so rather than
require a separate paid embeddings key we embed locally with a small, free,
CPU-friendly sentence-transformers model: ``all-MiniLM-L6-v2`` (384 dims). The
``Clause`` and ``RegulatoryUpdate`` vector columns are sized to match.

The model is loaded **once**, lazily, on first use and cached on the singleton
``embedding_service`` — never per request. Importing this module is cheap (the
heavy ``sentence_transformers`` import happens inside the loader) so unit tests
that mock the service never pay the model-load cost.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

# Force CPU-only execution. torch reads these at import time, so set them here —
# before the (lazy) ``sentence_transformers`` import pulls torch in. This avoids
# macOS fork+Metal (MPS) crashes (SIGABRT / MPSGraphObject) in Celery's prefork
# workers, where a forked child must never touch the GPU context.
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "0"
os.environ["CUDA_VISIBLE_DEVICES"] = ""

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger("counseliq.embeddings")


class EmbeddingService:
    """Generates dense embeddings for similarity search via a local model."""

    MODEL_NAME = "all-MiniLM-L6-v2"
    DIMENSIONS = 384

    def __init__(self) -> None:
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        """Return the cached model, loading it on first access."""
        if self._model is None:
            # Imported lazily so this module (and the whole app) imports without
            # the heavy torch/sentence-transformers stack present or loaded.
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model '%s' (one-time)", self.MODEL_NAME)
            # Pin to CPU explicitly (belt-and-braces with the env vars above) so
            # the model never initialises on MPS/CUDA in a forked worker.
            self._model = SentenceTransformer(self.MODEL_NAME, device="cpu")
        return self._model

    # --- Synchronous core (CPU-bound) --------------------------------------
    def embed_sync(self, text: str) -> list[float]:
        """Embed a single string. Normalised so cosine distance is meaningful."""
        vector = self.model.encode(text, normalize_embeddings=True)
        return [float(x) for x in vector]

    def embed_batch_sync(self, texts: list[str]) -> list[list[float]]:
        """Embed many strings in one batched forward pass."""
        if not texts:
            return []
        vectors = self.model.encode(texts, normalize_embeddings=True)
        return [[float(x) for x in vector] for vector in vectors]

    # --- Async wrappers (offload CPU work from the event loop) --------------
    async def generate_embedding(self, text: str) -> list[float]:
        """Async embedding for a single string (runs in a thread pool)."""
        return await asyncio.to_thread(self.embed_sync, text)

    async def generate_embeddings_batch(
        self, texts: list[str]
    ) -> list[list[float]]:
        """Async batched embedding (runs in a thread pool)."""
        return await asyncio.to_thread(self.embed_batch_sync, texts)


# Process-wide singleton. The model is loaded on first embed call, not here.
embedding_service = EmbeddingService()
