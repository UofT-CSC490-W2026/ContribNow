// ─── Legacy — retired in Layer 2 when API client is refactored ───────────────

export interface GenerateOnboardingRequest {
  repoUrl: string;
  accessKey: string;
  userPrompt?: string;
  forceRegenerate?: boolean;
}

export interface GenerateOnboardingResponse {
  success: boolean;
  document: string;
  storageKey: string | null;
  fromCache: boolean;
  version: number | null;
}

// ─── Shared ───────────────────────────────────────────────────────────────────

export interface ApiErrorInfo {
  message: string;
  status?: number;
}

// ─── API contracts ────────────────────────────────────────────────────────────

export type TaskType =
  | "fix_bug"
  | "add_feature"
  | "update_docs"
  | "understand"
  | "other";

export interface AnalyzeRequest {
  repoUrl: string;
  accessKey: string;
  taskType?: TaskType;
  taskDescription?: string;
}

export interface AnalyzeResponse {
  success: boolean;
  runId: string;
  document: string;
  version: number;
}

export interface AskRequest {
  runId: string;
  question: string;
  conversationHistory?: ChatMessage[];
}

export interface AskResponse {
  answer: string;
  citations?: Citation[];
}

// ─── Snapshot data (mirrors DATA_SCHEMA.md — snake_case kept as-is) ──────────

export interface Hotspot {
  path: string;
  touch_count: number;
  last_touched: string | null;
}

export interface RiskLevel {
  path: string;
  risk_level: "high" | "medium" | "low";
  risk_score: number;
  factors: {
    touch_count: number;
    distinct_authors: number;
    co_change_degree: number;
  };
}

export interface CoChangePair {
  file_a: string;
  file_b: string;
  co_change_count: number;
}

export interface Contributor {
  name: string;
  commit_count: number;
}

export interface FileAuthorship {
  path: string;
  total_commits: number;
  distinct_authors: number;
  primary_contributors: Contributor[];
}

export interface Conventions {
  test_framework: { name: string; config_path: string } | null;
  test_dirs: string[];
  linters: Array<{ name: string; config_path: string }>;
  ci_pipelines: Array<{ platform: string; config_path: string }>;
  contribution_docs: string[];
  package_manager: string | null;
}

export interface DependencyGraph {
  imports_map: Record<string, string[]>;
  imported_by: Record<string, string[]>;
}

// ─── UI / derived ─────────────────────────────────────────────────────────────

export interface DocumentSection {
  title: string;
  content: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface Citation {
  filePath: string;
  startLine: number;
  endLine: number;
  snippet: string;
}

export type ViewState = "setup" | "analyzing" | "workbench";
