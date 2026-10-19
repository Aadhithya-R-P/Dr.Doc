import pytest
from pydantic import SecretStr

from app.config import Settings
from app.database import create_database_engine, database_url


def settings_with_url(value):
    return Settings(_env_file=None, database_url=SecretStr(value))


def test_neon_url_selects_psycopg_and_preserves_ssl():
    settings = settings_with_url(
        "postgresql://sample:fake-password@example.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )
    url = database_url(settings)
    assert url.drivername == "postgresql+psycopg"
    assert url.query["sslmode"] == "require"
    assert url.query["channel_binding"] == "require"
    assert "fake-password" not in repr(settings)
    engine = create_database_engine(settings)
    try:
        assert engine.hide_parameters is True
        assert engine.echo is False
    finally:
        engine.dispose()


@pytest.mark.parametrize("value", ["", "not-a-url", "sqlite:///db", "postgresql://u:p@remote/db"])
def test_missing_invalid_or_insecure_database_url_is_rejected(value):
    with pytest.raises(ValueError):
        database_url(settings_with_url(value))


def test_database_is_optional_for_liveness(monkeypatch):
    monkeypatch.delenv("DRDOC_DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.database_url is None
    with pytest.raises(ValueError, match="Set DRDOC_DATABASE_URL"):
        database_url(settings)
