import { useEffect, useState } from "react";
import { getRiskLevels, ApiError } from "../api/client";
import type { ApiErrorInfo, RiskLevel } from "../types";

export function useRiskLevels(runId: string | null) {
  const [data, setData] = useState<RiskLevel[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ApiErrorInfo | null>(null);

  useEffect(() => {
    if (!runId) {
      setData([]);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    getRiskLevels(runId)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((err) => {
        if (!cancelled)
          setError(
            err instanceof ApiError
              ? { message: err.message, status: err.status }
              : { message: "Failed to load risk levels" }
          );
      })
      .finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [runId]);

  return { data, isLoading, error };
}
