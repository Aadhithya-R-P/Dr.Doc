from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.config import Settings
from app.database import create_database_engine


def pytest_addoption(parser):
    parser.addoption("--run-db", action="store_true", help="Run real PostgreSQL integration tests.")
    parser.addoption("--run-live-embedding", action="store_true", help="Opt into one real synthetic-text Gemini request.")


@pytest.fixture
def db_connection(request):
    if not request.config.getoption("--run-db"):
        pytest.skip("Real PostgreSQL tests require --run-db and DRDOC_DATABASE_URL.")
    settings = Settings()
    try:
        engine = create_database_engine(settings)
        connection = engine.connect()
    except Exception:
        pytest.fail("Could not connect to PostgreSQL. Check backend/.env and network access.", pytrace=False)

    transaction = connection.begin()
    try:
        # Unique, generated identifier; no existing application tables are touched.
        schema = "drdoc_test_" + uuid4().hex
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        yield connection
    finally:
        # Rollback removes test tables, schema and rows, including committed savepoints.
        transaction.rollback()
        connection.close()
        engine.dispose()
