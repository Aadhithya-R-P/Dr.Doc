import pytest
from pydantic import ValidationError

from app.config import BACKEND_DIR, Settings
from app.main import create_app


def test_environment_settings_configure_the_app(monkeypatch):
    monkeypatch.setenv("DRDOC_APP_NAME", "Dr.Doc test")
    monkeypatch.setenv("DRDOC_ENVIRONMENT", "test")
    settings = Settings(_env_file=None)
    app = create_app(settings)

    assert settings.environment == "test"
    assert app.title == "Dr.Doc test"
    assert app.state.settings is settings


def test_invalid_environment_is_rejected(monkeypatch):
    monkeypatch.setenv("DRDOC_ENVIRONMENT", "typo")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_dotenv_path_does_not_depend_on_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert Settings.model_config["env_file"] == BACKEND_DIR / ".env"
    assert (BACKEND_DIR / "pyproject.toml").is_file()
