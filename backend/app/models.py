from typing import Any, Literal
from pydantic import AliasChoices, BaseModel, Field, HttpUrl
from app.services.pgvector_interfaces import FloatVector, SearchResult, VectorRecord


class RepoFileContent(BaseModel):
    path: str
    content: str
    truncated: bool = False


class RepoSnapshot(BaseModel):
    repo_slug: str | None = None
    files: list[str] = Field(default_factory=list)
    selected_file_contents: list[RepoFileContent] = Field(
        default_factory=list,
        validation_alias=AliasChoices("selected_file_contents", "file_contents"),
    )


class OnboardingSnapshot(BaseModel):
    repo_slug: str | None = None
    repo_url: HttpUrl | None = None
    head_commit: str | None = None
    structure_summary: dict[str, Any] = Field(default_factory=dict)
    hotspots: list[dict[str, Any]] = Field(default_factory=list)
    risk_matrix: list[dict[str, Any]] = Field(default_factory=list)
    co_change_pairs: list[dict[str, Any]] = Field(default_factory=list)
    authorship_summary: list[dict[str, Any]] = Field(default_factory=list)
    dependency_graph: dict[str, Any] = Field(default_factory=dict)
    conventions: dict[str, Any] = Field(default_factory=dict)
    transform_metadata: dict[str, Any] = Field(default_factory=dict)
    load_metadata: dict[str, Any] = Field(default_factory=dict)


class GenerateOnboardingRequest(BaseModel):
    repoUrl: HttpUrl
    repoSlug: str
    userPrompt: str | None = None
    forceRegenerate: bool = False
    repoSnapshot: RepoSnapshot | None = None
    onboardingSnapshot: OnboardingSnapshot | None = None


class GenerateOnboardingResponse(BaseModel):
    success: bool
    document: str
    storageKey: str | None = None
    fromCache: bool


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


class SaveChatRequest(BaseModel):
    repo_slug: str
    role: Literal["user", "agent"]
    message: str
    created_at: str | None = None
