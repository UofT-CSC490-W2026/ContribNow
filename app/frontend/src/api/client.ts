import type {
  AnalyzeRequest,
  AnalyzeResponse,
  AskRequest,
  AskResponse,
  ChatHistoryResponse,
  CoChangePair,
  Conventions,
  DependencyGraph,
  FileAuthorship,
  GenerateOnboardingRequest,
  GenerateOnboardingResponse,
  Hotspot,
  OnboardingDocResponse,
  RiskLevel,
} from "../types";
import {
  MOCK_DOCUMENT,
  MOCK_AUTHORSHIP,
  MOCK_CO_CHANGES,
  MOCK_CONVENTIONS,
  MOCK_DEPENDENCIES,
  MOCK_HOTSPOTS,
  MOCK_RISK_LEVELS,
  mockAnalyze,
  mockAsk,
} from "./mock-data";

/* v8 ignore next */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function isMockMode() {
  return import.meta.env.VITE_USE_MOCK === "true";
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function parseErrorResponse(response: Response): Promise<ApiError> {
  const errorBody = await response.json().catch(() => ({}));
  return new ApiError(
    response.status,
    (errorBody as { detail?: string }).detail || "Request failed"
  );
}

// ── Legacy — removed in Layer 3 ─────────────────────────────────────────────

async function mockGenerateOnboarding(
  params: GenerateOnboardingRequest
): Promise<GenerateOnboardingResponse> {
  await new Promise((resolve) => setTimeout(resolve, 3000));

  if (params.accessKey !== "test") {
    throw new ApiError(401, "Invalid access key");
  }

  return {
    success: true,
    document: MOCK_DOCUMENT.replace(
      "pallets/markupsafe",
      new URL(params.repoUrl).pathname.slice(1)
    ),
    storageKey: "outputs/mock-repo-id/v1.md",
    fromCache: params.forceRegenerate ? false : Math.random() > 0.5,
    version: 1,
  };
}

export async function generateOnboarding(
  params: GenerateOnboardingRequest,
  signal?: AbortSignal
): Promise<GenerateOnboardingResponse> {
  if (isMockMode()) {
    return mockGenerateOnboarding(params);
  }

  const response = await fetch(`${API_BASE_URL}/generate-onboarding`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
    signal,
  });

  if (!response.ok) {
    throw await parseErrorResponse(response);
  }

  return response.json();
}

// ── New API functions ─────────────────────────────────────────────────────────

export async function analyze(
  params: AnalyzeRequest,
  signal?: AbortSignal
): Promise<AnalyzeResponse> {
  if (isMockMode()) {
    if (params.accessKey !== "test") throw new ApiError(401, "Invalid access key");
    return mockAnalyze(params);
  }

  const response = await fetch(`${API_BASE_URL}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
    signal,
  });

  if (!response.ok) throw await parseErrorResponse(response);
  return response.json();
}

export async function getHotspots(runId: string): Promise<Hotspot[]> {
  if (isMockMode()) return MOCK_HOTSPOTS;
  const response = await fetch(`${API_BASE_URL}/snapshot/${runId}/hotspots`);
  if (!response.ok) throw await parseErrorResponse(response);
  return response.json();
}

export async function getRiskLevels(runId: string): Promise<RiskLevel[]> {
  if (isMockMode()) return MOCK_RISK_LEVELS;
  const response = await fetch(`${API_BASE_URL}/snapshot/${runId}/risk-levels`);
  if (!response.ok) throw await parseErrorResponse(response);
  return response.json();
}

export async function getConventions(runId: string): Promise<Conventions> {
  if (isMockMode()) return MOCK_CONVENTIONS;
  const response = await fetch(`${API_BASE_URL}/snapshot/${runId}/conventions`);
  if (!response.ok) throw await parseErrorResponse(response);
  return response.json();
}

export async function getAuthorship(runId: string): Promise<FileAuthorship[]> {
  if (isMockMode()) return MOCK_AUTHORSHIP;
  const response = await fetch(`${API_BASE_URL}/snapshot/${runId}/authorship`);
  if (!response.ok) throw await parseErrorResponse(response);
  return response.json();
}

export async function getCoChanges(runId: string): Promise<CoChangePair[]> {
  if (isMockMode()) return MOCK_CO_CHANGES;
  const response = await fetch(`${API_BASE_URL}/snapshot/${runId}/co-changes`);
  if (!response.ok) throw await parseErrorResponse(response);
  return response.json();
}

export async function getDependencies(runId: string): Promise<DependencyGraph> {
  if (isMockMode()) return MOCK_DEPENDENCIES;
  const response = await fetch(`${API_BASE_URL}/snapshot/${runId}/dependencies`);
  if (!response.ok) throw await parseErrorResponse(response);
  return response.json();
}

export async function ask(params: AskRequest): Promise<AskResponse> {
  if (isMockMode()) return mockAsk(params);

  const response = await fetch(`${API_BASE_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });

  if (!response.ok) throw await parseErrorResponse(response);
  return response.json();
}

export async function loadOnboardingDoc(
  repoSlug: string,
  accessKey: string,
  storageKey?: string | null
): Promise<OnboardingDocResponse> {
  const url = new URL(`${API_BASE_URL}/onboarding-doc/load`);
  url.searchParams.set("repo_slug", repoSlug);
  if (storageKey) {
    url.searchParams.set("storageKey", storageKey);
    url.searchParams.set("storage_key", storageKey);
  }

  const response = await fetch(url.toString(), {
    headers: { "X-Access-Key": accessKey },
  });
  if (!response.ok) throw await parseErrorResponse(response);
  return response.json();
}

export async function saveChatMessage(
  repoSlug: string,
  role: "user" | "assistant",
  message: string,
  accessKey: string,
  createdAt?: string
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/chat-history/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Access-Key": accessKey },
    body: JSON.stringify({
      repo_slug: repoSlug,
      role,
      message,
      created_at: createdAt ?? new Date().toISOString(),
    }),
  });
  if (!response.ok) throw await parseErrorResponse(response);
}

export async function loadChatHistory(
  repoSlug: string,
  accessKey: string
): Promise<ChatHistoryResponse> {
  const response = await fetch(
    `${API_BASE_URL}/chat-history/load?repo_slug=${encodeURIComponent(repoSlug)}`,
    { headers: { "X-Access-Key": accessKey } }
  );
  if (!response.ok) throw await parseErrorResponse(response);
  return response.json();
}

export async function healthCheck(): Promise<boolean> {
  if (isMockMode()) return true;

  try {
    const response = await fetch(`${API_BASE_URL}/health`);
    return response.ok;
  } catch {
    return false;
  }
}
