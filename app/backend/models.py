from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    repoUrl: str
    accessKey: str
    taskType: Optional[
        Literal["fix_bug", "add_feature", "update_docs", "understand", "other"]
    ] = None
    taskDescription: Optional[str] = None


class AnalyzeResponse(BaseModel):
    success: bool
    runId: str
    document: str
    storageKey: Optional[str] = None
    fromCache: bool = False
    version: Optional[int] = None


class AskRequest(BaseModel):
    runId: str
    repoSlug: str
    accessKey: str
    question: str
    conversationHistory: Optional[List[dict]] = None


class Citation(BaseModel):
    filePath: str
    startLine: int
    endLine: int
    snippet: str


class AskResponse(BaseModel):
    answer: str
    citations: Optional[List[Citation]] = None
