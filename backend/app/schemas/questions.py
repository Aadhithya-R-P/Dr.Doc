"""Self-contained question, evidence, structured model output and answer contracts."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=1500)
    document_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=10)

    @field_validator("question")
    @classmethod
    def meaningful_question(cls, value):
        if not value.strip():
            raise ValueError("Question must contain text.")
        return value


class Source(BaseModel):
    source_id: str
    document_id: UUID
    chunk_id: UUID
    filename: str
    page_start: int
    page_end: int
    excerpt: str
    cosine_distance: float


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=1800)
    source_ids: list[str] = Field(min_length=1, max_length=4)


class GeneratedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["answered", "insufficient_evidence"]
    claims: list[Claim] = Field(max_length=6)


class QuestionResponse(BaseModel):
    mode: Literal["rag"] = "rag"
    status: Literal["answered", "no_evidence", "insufficient_evidence"]
    answer: str
    sources: list[Source] = Field(default_factory=list)
