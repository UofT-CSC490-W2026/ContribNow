import { useEffect, useState } from "react";
import { getHotspots, ApiError } from "../api/client";
import type { ApiErrorInfo, Hotspot } from "../types";

export function useHotspots(runId: string | null) {
  const [data, setData] = useState<Hotspot[]>([]);
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
    getHotspots(runId)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((err) => {
        if (!cancelled)
          setError(
            err instanceof ApiError
              ? { message: err.message, status: err.status }
              : { message: "Failed to load hotspots" }
          );
      })
      .finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [runId]);

  return { data, isLoading, error };
}
