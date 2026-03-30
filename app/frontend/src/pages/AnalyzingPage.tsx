import { useEffect, useRef, useState } from "react";
import { useRunSession } from "../context/RunSessionContext";
import { ErrorDisplay } from "../components/ErrorDisplay";

const STEPS = [
  { label: "Cloning repository", delay: 0 },
  { label: "Analyzing code structure", delay: 5_000 },
  { label: "Generating embeddings", delay: 15_000 },
  { label: "Indexing vectors", delay: 30_000 },
  { label: "Generating onboarding guide", delay: 50_000 },
];

type StepStatus = "pending" | "active" | "done";

export function AnalyzingPage() {
  const { repoUrl, analysisError, resetSession, analysisComplete } = useRunSession();
  const [stepStatuses, setStepStatuses] = useState<StepStatus[]>(
    STEPS.map((_, i) => (i === 0 ? "active" : "pending"))
  );
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef(Date.now());

  // Elapsed timer
  useEffect(() => {
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startRef.current) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, []);

  // Timed step progression
  useEffect(() => {
    const timers = STEPS.slice(1).map((step, i) =>
      setTimeout(() => {
        setStepStatuses((prev) => {
          const next = [...prev];
          next[i] = "done";       // complete the previous step
          next[i + 1] = "active"; // activate the next one
          return next;
        });
      }, step.delay)
    );
    return () => timers.forEach(clearTimeout);
  }, []);

  // When analysis completes, snap all steps to done before transitioning
  useEffect(() => {
    if (analysisComplete) {
      setStepStatuses(STEPS.map(() => "done"));
    }
  }, [analysisComplete]);

  const repoLabel = (() => {
    try { return new URL(repoUrl).pathname.slice(1); }
    catch { return repoUrl; }
  })();

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md space-y-6">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Analyzing repository</h2>
          <p className="mt-0.5 truncate text-sm text-gray-500">{repoLabel}</p>
        </div>

        <ol className="space-y-3">
          {STEPS.map((step, i) => {
            const status = stepStatuses[i];
            return (
              <li key={step.label} className="flex items-center gap-3">
                <StepIcon status={status} />
                <span
                  className={`text-sm ${
                    status === "active"
                      ? "font-medium text-gray-900"
                      : status === "done"
                      ? "text-gray-500"
                      : "text-gray-400"
                  }`}
                >
                  {step.label}
                </span>
              </li>
            );
          })}
        </ol>

        <p className="text-xs text-gray-400">{elapsed}s elapsed</p>

        {analysisError && (
          <div className="space-y-2">
            <ErrorDisplay error={analysisError} />
            <button
              onClick={resetSession}
              className="w-full rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Back to Setup
            </button>
          </div>
        )}

        {!analysisError && (
          <button
            onClick={resetSession}
            className="text-sm text-gray-400 hover:text-gray-600"
          >
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}

function StepIcon({ status }: { status: StepStatus }) {
  if (status === "done") {
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-green-100 text-green-600 text-xs font-bold">
        ✓
      </span>
    );
  }
  if (status === "active") {
    return (
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-gray-200 border-t-purple-600" />
    );
  }
  return (
    <span className="h-5 w-5 rounded-full border-2 border-gray-200" />
  );
}
