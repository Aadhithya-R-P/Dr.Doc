"""One Gemini Embedding 2 vector per passage, with bounded calls and safe failures."""

import math
import struct
import time

from google import genai
from google.genai import errors, types

from app.config import Settings

MODEL = "gemini-embedding-2"
DIMENSIONS = 768
INPUT_VERSION = "gemini2-retrieval-v1"
MAX_CHUNKS = 12
BUDGET_SECONDS = 60


class EmbeddingUnavailable(Exception):
    def __init__(self, code: str, message: str, status_code: int = 503):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def validate_vector(values) -> list[float]:
    try:
        if len(values) != DIMENSIONS:
            raise ValueError
        vector = [float(value) for value in values]
        if not all(math.isfinite(value) and abs(value) <= 3.4e38 for value in vector):
            raise ValueError
        # Validate the float32 representation pgvector actually stores, including underflow.
        vector = list(struct.unpack("<768f", struct.pack("<768f", *vector)))
        if sum(value * value for value in vector) <= 0:
            raise ValueError
        return vector
    except (ValueError, TypeError, OverflowError):
        raise EmbeddingUnavailable(
            "invalid_embedding", "The provider returned an invalid embedding. Nothing was indexed.", 502
        ) from None


class GeminiEmbedder:
    def __init__(self, settings: Settings):
        self.settings = settings

    def embed_documents(self, passages: list[str]) -> list[list[float]]:
        key = self.settings.gemini_api_key
        if key is None or not key.get_secret_value().strip():
            raise EmbeddingUnavailable("embedding_not_configured", "Embedding service is not configured.")
        if not 1 <= len(passages) <= MAX_CHUNKS:
            raise EmbeddingUnavailable("embedding_limit", "Upload must contain 1 to 12 chunks.", 422)
        deadline = time.monotonic() + BUDGET_SECONDS
        vectors = []
        try:
            with genai.Client(
                api_key=key.get_secret_value(), vertexai=False,
                http_options=types.HttpOptions(
                    timeout=15000, retry_options=types.HttpRetryOptions(attempts=1)
                ),
            ) as client:
                for passage in passages:
                    remaining_ms = int((deadline - time.monotonic()) * 1000)
                    if remaining_ms <= 0:
                        raise EmbeddingUnavailable("embedding_timeout", "Embedding time budget exhausted. Nothing was indexed.")
                    result = client.models.embed_content(
                        model=MODEL,
                        contents=f"title: none | text: {passage}",
                        config=types.EmbedContentConfig(
                            output_dimensionality=DIMENSIONS,
                            http_options=types.HttpOptions(
                                timeout=min(15000, remaining_ms),
                                retry_options=types.HttpRetryOptions(attempts=1),
                            ),
                        ),
                    )
                    if time.monotonic() > deadline:
                        raise EmbeddingUnavailable("embedding_timeout", "Embedding time budget exhausted. Nothing was indexed.")
                    if not result.embeddings or len(result.embeddings) != 1:
                        raise EmbeddingUnavailable("invalid_embedding", "Provider returned an unexpected embedding count.", 502)
                    vectors.append(validate_vector(result.embeddings[0].values))
            return vectors
        except EmbeddingUnavailable:
            raise
        except errors.APIError as exc:
            if exc.code == 429:
                raise EmbeddingUnavailable(
                    "embedding_quota_exhausted",
                    "Embedding quota exhausted or rate limited. Try later; nothing was indexed.",
                ) from None
            raise EmbeddingUnavailable("embedding_provider_failure", "Embedding provider is unavailable. Nothing was indexed.") from None
        except Exception:
            raise EmbeddingUnavailable("embedding_provider_failure", "Embedding request failed or timed out. Nothing was indexed.") from None
