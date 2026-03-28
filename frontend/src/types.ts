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

export interface ApiErrorInfo {
  message: string;
  status?: number;
}
