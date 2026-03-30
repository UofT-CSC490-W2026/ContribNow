import { useEffect, useState } from "react";
import { getCoChanges, ApiError } from "../api/client";
import type { ApiErrorInfo, CoChangePair } from "../types";

export function useCoChanges(runId: string | null) {
  const [data, setData] = useState<CoChangePair[]>([]);
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
    getCoChanges(runId)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((err) => {
        if (!cancelled)
          setError(
            err instanceof ApiError
              ? { message: err.message, status: err.status }
              : { message: "Failed to load co-change data" }
          );
      })
      .finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [runId]);

  return { data, isLoading, error };
}
