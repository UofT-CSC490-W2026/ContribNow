import { useCallback, useState } from "react";
import { ask, ApiError } from "../api/client";
import type { ChatMessage, Citation } from "../types";

interface ChatEntry {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  isLoading?: boolean;
}

export function useChat(runId: string | null) {
  const [entries, setEntries] = useState<ChatEntry[]>([]);

  const sendMessage = useCallback(
    async (question: string) => {
      if (!runId || !question.trim()) return;

      const userEntry: ChatEntry = { role: "user", content: question };
      const loadingEntry: ChatEntry = { role: "assistant", content: "", isLoading: true };

      setEntries((prev) => [...prev, userEntry, loadingEntry]);

      try {
        const history: ChatMessage[] = entries.map((e) => ({
          role: e.role,
          content: e.content,
        }));
        const response = await ask({ runId, question, conversationHistory: history });

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
    [runId, entries]
  );

  const clearHistory = useCallback(() => setEntries([]), []);

  return { entries, sendMessage, clearHistory };
}
