"""SQLAlchemy connection and session setup. Importing this module opens no connection."""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.config import Settings


def database_url(settings: Settings) -> URL:
    secret = settings.database_url
    if secret is None or not secret.get_secret_value().strip():
        raise ValueError("Set DRDOC_DATABASE_URL in backend/.env before using the database.")
    try:
        url = make_url(secret.get_secret_value())
    except ArgumentError:
        raise ValueError("DRDOC_DATABASE_URL must be a PostgreSQL connection URL.") from None
    if url.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
        raise ValueError("Only PostgreSQL with the psycopg driver is supported.")
    if not url.host or not url.database:
        raise ValueError("The database URL must include a host and database name.")
    if url.host not in {"localhost", "127.0.0.1", "::1"}:
        if url.query.get("sslmode") not in {"require", "verify-ca", "verify-full"}:
            raise ValueError("Remote PostgreSQL connections require sslmode=require or stronger.")
    return url.set(drivername="postgresql+psycopg")


def create_database_engine(settings: Settings) -> Engine:
    # NullPool closes connections after use, allowing Neon to become idle.
    # No SQL or bound parameter logging; bound values may contain document text.
    return create_engine(
        database_url(settings),
        poolclass=NullPool,
        echo=False,
        hide_parameters=True,
        connect_args={"connect_timeout": 10, "options": "-c statement_timeout=15000"},
    )


def create_session(engine: Engine) -> Session:
    """Caller owns the session context and explicit transaction/commit boundary."""
    return Session(engine, expire_on_commit=False)
