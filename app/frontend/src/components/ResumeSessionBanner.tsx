import { useState } from "react";
import { useRunSession } from "../context/RunSessionContext";
import { useSessionPersistence } from "../hooks/useSessionPersistence";

export function ResumeSessionBanner() {
  const { restoreSession } = useRunSession();
  const { getSession, clearSession } = useSessionPersistence();
  const [dismissed, setDismissed] = useState(false);

  const session = getSession();
  if (!session || dismissed) return null;

  const repoLabel = (() => {
    try {
      return new URL(session.repoUrl).pathname.slice(1);
    } catch {
      return session.repoUrl;
    }
  })();

  return (
    <div className="flex items-center justify-between rounded-lg border border-purple-200 bg-purple-50 px-4 py-3">
      <p className="text-sm text-purple-800">
        Resume analysis of{" "}
        <span className="font-mono font-medium">{repoLabel}</span>?
      </p>
      <div className="flex gap-2">
        <button
          onClick={() => restoreSession(session)}
          className="rounded-md bg-purple-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-purple-700"
        >
          Resume
        </button>
        <button
          onClick={() => { clearSession(); setDismissed(true); }}
          className="rounded-md border border-purple-300 px-3 py-1.5 text-xs font-medium text-purple-700 hover:bg-purple-100"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}
