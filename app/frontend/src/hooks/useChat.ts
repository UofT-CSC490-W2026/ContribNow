import { useCallback, useEffect, useRef, useState } from "react";
import { ask, ApiError } from "../api/client";
import type { ChatHistoryEntry, ChatMessage, Citation } from "../types";

interface ChatEntry {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  isLoading?: boolean;
}

export function useChat(
  runId: string | null,
  accessKey: string,
  initialHistory: ChatHistoryEntry[] = []
) {
  const [entries, setEntries] = useState<ChatEntry[]>(() =>
    initialHistory.map((h) => ({ role: h.role, content: h.message }))
  );
  const entriesRef = useRef<ChatEntry[]>(entries);

  useEffect(() => {
    entriesRef.current = entries;
  }, [entries]);

  // Sync when initialHistory changes (e.g. after session restore loads cloud history)
  useEffect(() => {
    if (initialHistory.length > 0) {
      const mapped = initialHistory.map((h) => ({ role: h.role, content: h.message }));
      setEntries(mapped);
      entriesRef.current = mapped;
    }
  }, [initialHistory]);

  const sendMessage = useCallback(
    async (question: string) => {
      if (!runId || !question.trim()) return;

      const userEntry: ChatEntry = { role: "user", content: question };
      const loadingEntry: ChatEntry = { role: "assistant", content: "", isLoading: true };

      setEntries((prev) => [...prev, userEntry, loadingEntry]);

      try {
        const history: ChatMessage[] = [...entriesRef.current, userEntry].map((e) => ({
          role: e.role,
          content: e.content,
        }));
        // Backend saves both messages to cloud after a successful response
        const response = await ask({
          runId,
          repoSlug: runId,
          accessKey,
          question,
          conversationHistory: history,
        });

        setEntries((prev) => [
          ...prev.slice(0, -1),
          { role: "assistant", content: response.answer, citations: response.citations },
        ]);
      } catch (err) {
        const message =
          err instanceof ApiError ? err.message : "Failed to get a response.";
        setEntries((prev) => [
          ...prev.slice(0, -1),
          { role: "assistant", content: message },
        ]);
      }
    },
    [runId, accessKey]
  );

  const clearHistory = useCallback(() => setEntries([]), []);

  return { entries, sendMessage, clearHistory };
}
