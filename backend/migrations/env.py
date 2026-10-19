"""Run migrations with the same private settings as the application."""

from alembic import context
from app.config import Settings
from app.database import create_database_engine
from app.models import Base

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    # SQL rendering needs a dialect, never real credentials or a live database.
    context.configure(
        dialect_name="postgresql", target_metadata=target_metadata,
        literal_binds=True, compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = context.config.attributes.get("connection")
    if engine is not None:
        # Integration tests supply a connection in an isolated test schema.
        context.configure(connection=engine, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_database_engine(Settings())
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection, target_metadata=target_metadata, compare_type=True
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
