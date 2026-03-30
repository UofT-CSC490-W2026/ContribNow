import { useEffect, useState } from "react";
import { getAuthorship, ApiError } from "../api/client";
import type { ApiErrorInfo, FileAuthorship } from "../types";

export function useAuthorship(runId: string | null) {
  const [data, setData] = useState<FileAuthorship[]>([]);
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
    getAuthorship(runId)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((err) => {
        if (!cancelled)
          setError(
            err instanceof ApiError
              ? { message: err.message, status: err.status }
              : { message: "Failed to load authorship data" }
          );
      })
      .finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [runId]);

  return { data, isLoading, error };
}
