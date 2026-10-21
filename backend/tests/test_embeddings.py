from types import SimpleNamespace
from unittest.mock import MagicMock

from google.genai import errors
from pydantic import SecretStr
import pytest

from app.config import Settings
from app.services import embeddings
from app.services.embeddings import EmbeddingUnavailable, GeminiEmbedder, validate_vector


def vector():
    return [1.0] + [0.0] * 767


def setup_client(monkeypatch):
    factory = MagicMock()
    client = factory.return_value.__enter__.return_value
    client.models.embed_content.return_value = SimpleNamespace(
        embeddings=[SimpleNamespace(values=vector())]
    )
    monkeypatch.setattr(embeddings.genai, "Client", factory)
    provider = GeminiEmbedder(Settings(_env_file=None, gemini_api_key=SecretStr("test-only")))
    return factory, client, provider


def test_one_call_per_chunk_and_document_prefix(monkeypatch):
    factory, client, provider = setup_client(monkeypatch)
    result = provider.embed_documents(["First passage", "Second passage"])
    assert len(result) == 2
    calls = client.models.embed_content.call_args_list
    assert len(calls) == 2
    assert calls[0].kwargs["contents"] == "title: none | text: First passage"
    assert calls[1].kwargs["contents"] == "title: none | text: Second passage"
    assert calls[0].kwargs["config"].output_dimensionality == 768
    assert calls[0].kwargs["config"].task_type is None
    assert factory.call_args.kwargs["http_options"].retry_options.attempts == 1
    assert calls[0].kwargs["config"].http_options.timeout <= 15000


def test_quota_failure_stops_after_failed_chunk(monkeypatch):
    _, client, provider = setup_client(monkeypatch)
    client.models.embed_content.side_effect = errors.ClientError(
        429, {"error": {"message": "provider-private", "status": "RESOURCE_EXHAUSTED"}}
    )
    with pytest.raises(EmbeddingUnavailable) as caught:
        provider.embed_documents(["first", "second"])
    assert caught.value.code == "embedding_quota_exhausted"
    assert "provider-private" not in str(caught.value)
    client.models.embed_content.assert_called_once()


def test_timeout_failure_is_safe(monkeypatch):
    _, client, provider = setup_client(monkeypatch)
    client.models.embed_content.side_effect = TimeoutError("private-network-detail")
    with pytest.raises(EmbeddingUnavailable) as caught:
        provider.embed_documents(["text"])
    assert "private-network-detail" not in str(caught.value)


def test_budget_exhaustion_stops_further_calls(monkeypatch):
    _, client, provider = setup_client(monkeypatch)
    monkeypatch.setattr(embeddings.time, "monotonic", MagicMock(side_effect=[0, 0, 61]))
    with pytest.raises(EmbeddingUnavailable, match="time budget"):
        provider.embed_documents(["first", "second"])
    client.models.embed_content.assert_called_once()


@pytest.mark.parametrize("bad", [[], [1.0], [0.0] * 768,
    [float("nan")] * 768, [float("inf")] * 768, [1e100] * 768, [1e-100] * 768, None])
def test_malformed_vectors_rejected(bad):
    with pytest.raises(EmbeddingUnavailable) as caught:
        validate_vector(bad)
    assert caught.value.code == "invalid_embedding"


def test_aggregated_or_missing_embeddings_rejected(monkeypatch):
    _, client, provider = setup_client(monkeypatch)
    client.models.embed_content.return_value = SimpleNamespace(embeddings=[])
    with pytest.raises(EmbeddingUnavailable):
        provider.embed_documents(["text"])


def test_chunk_cap_checked_before_client_is_created(monkeypatch):
    factory, _, provider = setup_client(monkeypatch)
    with pytest.raises(EmbeddingUnavailable):
        provider.embed_documents(["text"] * 13)
    factory.assert_not_called()
