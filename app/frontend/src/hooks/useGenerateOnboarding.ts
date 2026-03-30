import { useCallback, useRef, useState } from "react";
import { generateOnboarding, ApiError } from "../api/client";
import type {
  GenerateOnboardingRequest,
  GenerateOnboardingResponse,
  ApiErrorInfo,
} from "../types";

export function useGenerateOnboarding() {
  const [result, setResult] = useState<GenerateOnboardingResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ApiErrorInfo | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const generate = useCallback(async (params: GenerateOnboardingRequest) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await generateOnboarding(params, controller.signal);
      setResult(data);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;

      if (err instanceof ApiError) {
        setError({ message: err.message, status: err.status });
      } else {
        setError({ message: "Cannot reach the server. Check your connection." });
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setResult(null);
    setError(null);
    setIsLoading(false);
  }, []);

  return { result, isLoading, error, generate, reset };
}
