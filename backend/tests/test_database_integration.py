from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.models import Chunk, Document

pytestmark = pytest.mark.integration


def document(**overrides):
    values = dict(
        filename="sample.pdf", content_type="application/pdf",
        content_hash=sha256(uuid4().bytes).hexdigest(), page_count=2,
        embedding_model="gemini-embedding-2", embedding_dimensions=768,
        chunking_version="test-only",
    )
    values.update(overrides)
    return Document(**values)


def vector(axis):
    values = [0.0] * 768
    values[axis] = 1.0
    return values


def chunk(doc, index=0, axis=0, **overrides):
    values = dict(
        document=doc, chunk_index=index, text="Public synthetic test passage.",
        page_start=1, page_end=2, token_count=6, embedding=vector(axis),
    )
    values.update(overrides)
    return Chunk(**values)


def session_for(connection):
    return Session(connection, join_transaction_mode="create_savepoint", expire_on_commit=False)


def test_migration_vector_roundtrip_cosine_search_and_document_filter(db_connection):
    with session_for(db_connection) as session:
        first, second = document(), document()
        a, b = chunk(first, axis=0), chunk(second, axis=1)
        session.add_all([a, b])
        session.commit()
        session.expire_all()

        distance = Chunk.embedding.cosine_distance(vector(0))
        nearest = session.scalars(select(Chunk).order_by(distance).limit(1)).one()
        assert nearest.id == a.id
        assert len(nearest.embedding) == 768
        filtered = session.scalars(
            select(Chunk).where(Chunk.document_id == second.id).order_by(distance)
        ).one()
        assert filtered.id == b.id
        assert session.scalar(select(distance).where(Chunk.id == a.id)) == pytest.approx(0)
        assert first.created_at.tzinfo is not None
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "0001"


def test_database_cascade_removes_chunks_from_search(db_connection):
    with session_for(db_connection) as session:
        doc = document()
        session.add(chunk(doc))
        session.commit()
        # Bulk SQL delete exercises the database FK, rather than ORM child deletion.
        session.execute(delete(Document).where(Document.id == doc.id))
        session.commit()
        assert session.scalar(select(func.count()).select_from(Chunk)) == 0


def test_duplicate_hash_is_rejected(db_connection):
    with session_for(db_connection) as session:
        doc = document()
        session.add(doc)
        session.commit()
        session.add(document(content_hash=doc.content_hash))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_duplicate_chunk_rolls_back_whole_document(db_connection):
    with session_for(db_connection) as session:
        doc = document()
        session.add_all([chunk(doc), chunk(doc)])
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert session.scalar(select(func.count()).select_from(Document)) == 0
        assert session.scalar(select(func.count()).select_from(Chunk)) == 0


@pytest.mark.parametrize("overrides", [
    {"page_start": 0}, {"page_start": 2, "page_end": 1}, {"token_count": 0},
    {"text": "   "}, {"chunk_index": -1}, {"embedding": [1.0, 0.0]},
])
def test_invalid_chunk_is_rejected(db_connection, overrides):
    with session_for(db_connection) as session:
        session.add(chunk(document(), **overrides))
        with pytest.raises((IntegrityError, StatementError)):
            session.flush()
        session.rollback()


@pytest.mark.parametrize("overrides", [
    {"embedding_model": "another-model"}, {"embedding_dimensions": 1536}, {"page_count": 0},
])
def test_incompatible_model_dimensions_and_invalid_pages_are_rejected(db_connection, overrides):
    with session_for(db_connection) as session:
        session.add(document(**overrides))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
