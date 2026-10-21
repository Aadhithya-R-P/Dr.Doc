from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import Chunk, Document
from app.schemas.questions import Source


def vector(axis=0):
    result = [0.0] * 768
    result[axis] = 1.0
    return result


def source(source_id="D1"):
    return Source(source_id=source_id, document_id=uuid4(), chunk_id=uuid4(),
        filename="public.pdf", page_start=1, page_end=1,
        excerpt="The Redis cache TTL is 45 seconds.", cosine_distance=0.1)


def factory(connection):
    return lambda: Session(connection, join_transaction_mode="create_savepoint", expire_on_commit=False)


def seed(session_factory, text="The Redis cache TTL is 45 seconds.", axis=0, version="gemini2-retrieval-v1"):
    with session_factory() as session:
        with session.begin():
            doc = Document(filename="public.pdf", content_type="application/pdf", content_hash=uuid4().hex,
                page_count=1, embedding_model="gemini-embedding-2", embedding_dimensions=768,
                embedding_input_version=version, chunking_version="test")
            session.add(doc)
            session.flush()
            chunk = Chunk(document_id=doc.id, chunk_index=0, text=text, page_start=1, page_end=1,
                token_count=max(1, len(text) // 4), embedding=vector(axis))
            session.add(chunk)
            session.flush()
            return doc.id, chunk.id
