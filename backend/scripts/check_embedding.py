"""One synthetic-text API request; no PDF upload or database write."""

import argparse
import math

from google import genai
from google.genai import errors, types

from app.config import Settings

MODEL = "gemini-embedding-2"
DIMENSIONS = 768


def check_embedding(settings: Settings) -> int:
    key = settings.gemini_api_key
    if key is None or not key.get_secret_value().strip():
        print("Not run: set DRDOC_GEMINI_API_KEY in backend/.env. Do not share it in chat.")
        return 1
    try:
        with genai.Client(
            api_key=key.get_secret_value(),
            vertexai=False,
            http_options=types.HttpOptions(
                timeout=15000, retry_options=types.HttpRetryOptions(attempts=1)
            ),
        ) as client:
            result = client.models.embed_content(
                model=MODEL,
                contents="title: Dr.Doc sample | text: Redis caches frequently requested data.",
                config=types.EmbedContentConfig(output_dimensionality=DIMENSIONS),
            )
        embeddings = result.embeddings or []
        if len(embeddings) != 1:
            print("Failed: expected exactly one embedding.")
            return 1
        values = embeddings[0].values or []
        if len(values) != DIMENSIONS or not all(math.isfinite(value) for value in values):
            print("Failed: response does not contain 768 finite numeric values.")
            return 1
        norm = math.sqrt(sum(value * value for value in values))
        if norm <= 0:
            print("Failed: zero vector cannot support cosine search.")
            return 1
        print(f"PASS: model={MODEL}, dimensions={len(values)}, finite=True, norm={norm:.6f}")
        print("One synthetic-text request succeeded. Future quota and retrieval quality are not guaranteed.")
        return 0
    except errors.APIError as exc:
        if exc.code == 429:
            print("Temporarily unavailable: quota exhausted or rate limited. No retry or paid fallback.")
        elif exc.code in {401, 403}:
            print("Unavailable: API key or project access was rejected. Check AI Studio permissions.")
        elif exc.code == 404:
            print("Unavailable: the configured model was not found or is unavailable to this project.")
        else:
            print(f"Provider request failed (HTTP {exc.code}). No retry or paid fallback.")
        return 1
    except Exception:
        # Never print raw exceptions, request headers, credentials or provider bodies.
        print("Check failed: network, SDK or response error. No retry; no credentials logged.")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--free-tier-confirmed", action="store_true",
        help="Confirm in AI Studio that this key's project is Free with billing disabled.",
    )
    args = parser.parse_args()
    if not args.free_tier_confirmed:
        print("Not run: confirm the project is Free with billing disabled, then use --free-tier-confirmed.")
        return 1
    return check_embedding(Settings())


if __name__ == "__main__":
    raise SystemExit(main())
