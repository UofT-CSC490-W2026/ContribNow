from pydantic import BaseModel, HttpUrl


class GenerateOnboardingRequest(BaseModel):
    repoUrl: HttpUrl
    userPrompt: str | None = None
    accessKey: str
    forceRegenerate: bool = False


class GenerateOnboardingResponse(BaseModel):
    success: bool
    document: str
    storageKey: str | None = None
    fromCache: bool
    version: int | None = None