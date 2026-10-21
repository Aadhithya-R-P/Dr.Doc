"""Diagnose one synthetic answer request without exposing the API key."""

from google import genai
from google.genai import errors, types

from app.config import Settings
from app.schemas.questions import GeneratedAnswer
from app.services.answers import ANSWER_MODEL


def main():
    settings = Settings()
    if settings.gemini_api_key is None:
        print("Missing private API key.")
        return 1
    key = settings.gemini_api_key.get_secret_value()
    try:
        with genai.Client(api_key=key, vertexai=False, http_options=types.HttpOptions(
            timeout=45000, retry_options=types.HttpRetryOptions(attempts=1)
        )) as client:
            result = client.models.generate_content(
                model=ANSWER_MODEL,
                contents='Evidence D1: Redis TTL is 45 seconds. Return one cited claim giving the TTL.',
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=GeneratedAnswer.model_json_schema(),
                    max_output_tokens=1800, temperature=0,
                ),
            )
            print("Generation request succeeded; response present:", bool(result.text))
        return 0
    except errors.APIError as exc:
        # This diagnostic uses synthetic text only; strip the key from provider diagnostics.
        print("Provider HTTP status:", exc.code)
        print("Reason:", str(exc.message).replace(key, "[REDACTED]")[:1000])
        return 1
    except Exception:
        print("Network or SDK failure; raw exception suppressed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
