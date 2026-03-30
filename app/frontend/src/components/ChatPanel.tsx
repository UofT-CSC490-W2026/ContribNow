import { useRef, useState, type FormEvent, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useChat } from "../hooks/useChat";
import type { Citation } from "../types";

interface ChatPanelProps {
  runId: string;
}

function SnippetModal({
  citation,
  onClose,
}: {
  citation: Citation;
  onClose: () => void;
}) {
  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-30 bg-black/30" onClick={onClose} />
      {/* Modal */}
      <div className="fixed left-1/2 top-1/2 z-40 w-[480px] max-w-[90vw] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-gray-200 bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
          <span className="font-mono text-sm font-medium text-gray-800">
            {citation.filePath}
            <span className="ml-2 text-xs font-normal text-gray-400">
              lines {citation.startLine}–{citation.endLine}
            </span>
          </span>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            aria-label="Close"
          >
            ✕
          </button>
        </div>
        <pre className="overflow-x-auto whitespace-pre-wrap break-words px-4 py-3 font-mono text-xs text-gray-700">
          {citation.snippet}
        </pre>
      </div>
    </>
  );
}

function CitationChip({ citation }: { citation: Citation }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="inline-block rounded bg-gray-100 px-1.5 py-0.5 font-mono text-xs text-gray-600 hover:bg-purple-100 hover:text-purple-700"
      >
        {citation.filePath}:{citation.startLine}-{citation.endLine}
      </button>
      {open && <SnippetModal citation={citation} onClose={() => setOpen(false)} />}
    </>
  );
}

export function ChatPanel({ runId }: ChatPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const [input, setInput] = useState("");
  const { entries, sendMessage } = useChat(runId);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (expanded) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries, expanded]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    const q = input.trim();
    setInput("");
    setExpanded(true);
    await sendMessage(q);
  };

  return (
    <div
      className={`border-t border-gray-200 bg-white transition-all duration-200 ${
        expanded ? "h-[40vh]" : "h-[52px]"
      }`}
    >
      {expanded && (
        <>
          {/* Thread header */}
          <div className="flex items-center justify-between border-b border-gray-100 px-4 py-2">
            <span className="text-sm font-medium text-gray-700">Chat</span>
            <button
              onClick={() => setExpanded(false)}
              className="text-xs text-gray-400 hover:text-gray-600"
            >
              Collapse ▾
            </button>
          </div>

          {/* Message thread */}
          <div className="flex-1 overflow-y-auto px-4 py-3" style={{ height: "calc(40vh - 100px)" }}>
            {entries.length === 0 ? (
              <p className="text-sm text-gray-400">Ask anything about this codebase.</p>
            ) : (
              entries.map((entry, i) => (
                <div
                  key={i}
                  className={`mb-3 ${entry.role === "user" ? "text-right" : "text-left"}`}
                >
                  {entry.role === "user" ? (
                    <span className="inline-block rounded-lg bg-purple-600 px-3 py-2 text-sm text-white">
                      {entry.content}
                    </span>
                  ) : entry.isLoading ? (
                    <span className="inline-flex items-center gap-1.5 text-sm text-gray-400">
                      <span className="h-3 w-3 animate-spin rounded-full border-2 border-gray-300 border-t-purple-500" />
                      Thinking...
                    </span>
                  ) : (
                    <div className="inline-block max-w-[90%] rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-left">
                      <article className="prose prose-sm prose-slate max-w-none">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {entry.content}
                        </ReactMarkdown>
                      </article>
                      {entry.citations && entry.citations.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {entry.citations.map((c, j) => (
                            <CitationChip key={j} citation={c} />
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))
            )}
            <div ref={bottomRef} />
          </div>
        </>
      )}

      {/* Input bar — always visible */}
      <form onSubmit={handleSubmit} className="flex items-center gap-2 px-4 py-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onFocus={() => setExpanded(true)}
          placeholder="Ask a question about this codebase..."
          className="flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:border-purple-500 focus:ring-1 focus:ring-purple-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={!input.trim()}
          className="rounded-lg bg-purple-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-purple-700 disabled:bg-gray-300"
        >
          Send
        </button>
      </form>
    </div>
  );
}
