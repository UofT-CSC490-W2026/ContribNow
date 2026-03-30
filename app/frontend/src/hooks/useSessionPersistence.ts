import { useCallback } from "react";
import type { TaskType } from "../types";

const SESSION_KEY = "contribnow_last_session";

export interface PersistedSession {
  runId: string;
  documentRaw: string;
  repoUrl: string;
  accessKey: string;
  taskType?: TaskType;
  taskDescription?: string;
  storageKey?: string | null;
  version: number | null;
  savedAt: string; // ISO 8601
}

export function useSessionPersistence() {
  const getSession = useCallback((): PersistedSession | null => {
    try {
      const raw = localStorage.getItem(SESSION_KEY);
      return raw ? (JSON.parse(raw) as PersistedSession) : null;
    } catch {
      return null;
    }
  }, []);

  const saveSession = useCallback((session: PersistedSession) => {
    localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  }, []);

  const clearSession = useCallback(() => {
    localStorage.removeItem(SESSION_KEY);
  }, []);

  return { getSession, saveSession, clearSession };
}
