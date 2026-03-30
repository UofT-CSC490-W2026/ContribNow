from typing import Any, Literal
from pydantic import BaseModel, HttpUrl
from app.services.pgvector_interfaces import FloatVector, SearchResult, VectorRecord


class GenerateOnboardingRequest(BaseModel):
    repoUrl: HttpUrl
    userPrompt: str | None = None
    forceRegenerate: bool = False


class GenerateOnboardingResponse(BaseModel):
    success: bool
    document: str
    storageKey: str | None = None
    fromCache: bool
    version: int | None = None


class CreateRdsTableRequest(BaseModel):
    tableName: str


class SaveToRdsRequest(BaseModel):
    tableName: str
    key: str
    value: dict[str, Any]


class SaveToS3Request(BaseModel):
    objectKey: str
    obj: str


class VectorRecordAPI(BaseModel):
    vector: list[float]
    repoSlug: str
    headCommit: str
    filePath: str
    startLine: int
    endLine: int
    dataId: str


class VectorRecordRequest(BaseModel):
    records: list[VectorRecordAPI]


class VectorQueryRequest(BaseModel):
    query_vector: list[float]
    k: int = 5
    repo_slug: str | None = None
    head_commit: str | None = None
    file_path: str | None = None


class SearchResultAPI(BaseModel):
    # Higher score = better match.
    score: float
    repo_slug: str
    head_commit: str
    file_path: str
    start_line: int
    end_line: int
    vector: list[float] | None


class VectorQueryResponse(BaseModel):
    results: list[SearchResultAPI]


class SaveOnboardingDocRequest(BaseModel):
    repo_slug: str
    onboarding_doc: str


class ChatMessage(BaseModel):
    role: Literal["user", "agent"]
    message: str
    created_at: str | None = None