import { useEffect, useState } from "react";
import { getConventions, ApiError } from "../api/client";
import type { ApiErrorInfo, Conventions } from "../types";

export function useConventions(runId: string | null) {
  const [data, setData] = useState<Conventions | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ApiErrorInfo | null>(null);

  useEffect(() => {
    if (!runId) {
      setData(null);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    getConventions(runId)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((err) => {
        if (!cancelled)
          setError(
            err instanceof ApiError
              ? { message: err.message, status: err.status }
              : { message: "Failed to load conventions" }
          );
      })
      .finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [runId]);

  return { data, isLoading, error };
}
