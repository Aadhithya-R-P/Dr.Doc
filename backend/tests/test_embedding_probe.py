from types import SimpleNamespace
from unittest.mock import MagicMock

from google.genai import errors
from pydantic import SecretStr
import pytest

from app.config import Settings
from scripts import check_embedding as probe


def fake_client(monkeypatch):
    factory = MagicMock()
    client = factory.return_value.__enter__.return_value
    monkeypatch.setattr(probe.genai, "Client", factory)
    return factory, client


def test_missing_key_does_not_call_provider(monkeypatch):
    factory, _ = fake_client(monkeypatch)
    settings = Settings(_env_file=None, gemini_api_key=None)
    assert probe.check_embedding(settings) == 1
    factory.assert_not_called()


@pytest.mark.parametrize("dimensions,expected", [(768, 0), (758, 1)])
def test_dimension_validation_and_bounded_request(monkeypatch, dimensions, expected):
    factory, client = fake_client(monkeypatch)
    client.models.embed_content.return_value = SimpleNamespace(
        embeddings=[SimpleNamespace(values=[1.0] + [0.0] * (dimensions - 1))]
    )
    settings = Settings(_env_file=None, gemini_api_key=SecretStr("test-placeholder"))
    assert probe.check_embedding(settings) == expected
    client.models.embed_content.assert_called_once()
    options = factory.call_args.kwargs["http_options"]
    assert options.retry_options.attempts == 1
    assert options.timeout == 15000
    config = client.models.embed_content.call_args.kwargs["config"]
    assert config.output_dimensionality == 768


def test_quota_error_is_clear_and_does_not_expose_provider_body(monkeypatch, capsys):
    _, client = fake_client(monkeypatch)
    client.models.embed_content.side_effect = errors.ClientError(
        429, {"error": {"message": "sensitive-provider-detail", "status": "RESOURCE_EXHAUSTED"}}
    )
    settings = Settings(_env_file=None, gemini_api_key=SecretStr("test-placeholder"))
    assert probe.check_embedding(settings) == 1
    output = capsys.readouterr().out
    assert "quota" in output
    assert "sensitive-provider-detail" not in output
    assert "test-placeholder" not in output
    client.models.embed_content.assert_called_once()
