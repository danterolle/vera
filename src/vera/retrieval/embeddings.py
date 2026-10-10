import math
import re
from hashlib import sha256
from typing import Protocol

from vera.config import Settings
from vera.errors import ConfigurationError

TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]*", re.IGNORECASE)


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedder:
    name = "hash"

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in TOKEN_PATTERN.findall(text.lower()):
            digest = sha256(token.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


class SentenceTransformerEmbedder:
    name = "sentence-transformers"

    def __init__(self, model_name: str) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ConfigurationError(
                "Install the 'embeddings' extra to use sentence-transformers"
            ) from exc
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [vector.tolist() for vector in vectors]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def build_embedder(settings: Settings) -> Embedder:
    if settings.embedding_backend == "sentence-transformers":
        return SentenceTransformerEmbedder(settings.embedding_model)
    return HashEmbedder()
