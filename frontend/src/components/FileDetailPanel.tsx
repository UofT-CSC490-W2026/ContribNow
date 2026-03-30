import type React from "react";
import type { FileAuthorship, Hotspot, RiskLevel } from "../types";

interface CoChangedFile {
  path: string;
  count: number;
}

interface FileDetailPanelProps {
  filePath: string;
  anchorRect: DOMRect;
  riskLevel: RiskLevel | undefined;
  hotspot: Hotspot | undefined;
  authorship: FileAuthorship | undefined;
  coChangedFiles: CoChangedFile[];
  isLoading: boolean;
  onClose: () => void;
  onNavigateFile: (path: string) => void;
}

function RiskBadge({ level, score }: { level: "high" | "medium" | "low"; score: number }) {
  const styles = {
    high: "bg-red-100 text-red-700",
    medium: "bg-yellow-100 text-yellow-700",
    low: "bg-green-100 text-green-700",
  };
  const labels = { high: "High", medium: "Medium", low: "Low" };
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${styles[level]}`}>
      {labels[level]} ({score.toFixed(2)})
    </span>
  );
}

export function FileDetailPanel({
  filePath,
  anchorRect,
  riskLevel,
  hotspot,
  authorship,
  coChangedFiles,
  isLoading,
  onClose,
  onNavigateFile,
}: FileDetailPanelProps) {
  const fileName = filePath.split("/").pop() ?? filePath;

  // Position just below the clicked row, clamped so it doesn't overflow the viewport
  const top = Math.min(anchorRect.bottom + 4, window.innerHeight - 320);
  const panelStyle: React.CSSProperties = {
    position: "fixed",
    top,
    left: anchorRect.left,
    width: anchorRect.width,
    zIndex: 20,
  };

  return (
    <>
      {/* Backdrop — click outside to close */}
      <div className="fixed inset-0 z-10" onClick={onClose} />

      <div style={panelStyle} className="rounded-lg border border-gray-200 bg-white shadow-lg">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
        <span className="truncate font-mono text-sm font-medium text-gray-900" title={filePath}>
          {fileName}
        </span>
        <button
          onClick={onClose}
          className="ml-2 flex-shrink-0 text-gray-400 hover:text-gray-600"
          aria-label="Close"
        >
          ✕
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center p-6">
          <span className="h-5 w-5 animate-spin rounded-full border-2 border-gray-200 border-t-purple-600" />
        </div>
      ) : (
        <div className="space-y-4 p-4">
          {/* Risk + touches */}
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-gray-600">
            {riskLevel && (
              <span className="flex items-center gap-1.5">
                Risk: <RiskBadge level={riskLevel.risk_level} score={riskLevel.risk_score} />
              </span>
            )}
            {hotspot && (
              <span>{hotspot.touch_count} commits</span>
            )}
            {authorship && (
              <span>{authorship.distinct_authors} authors</span>
            )}
          </div>

          {/* Top contributors */}
          {authorship && authorship.primary_contributors.length > 0 && (
            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500">
                Top Contributors
              </p>
              <ul className="space-y-0.5">
                {authorship.primary_contributors.slice(0, 3).map((c) => (
                  <li key={c.name} className="flex items-center justify-between text-sm">
                    <span className="text-gray-700">{c.name}</span>
                    <span className="text-xs text-gray-400">{c.commit_count} commits</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Co-changed files */}
          {coChangedFiles.length > 0 && (
            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500">
                ⚠ Often changed with
              </p>
              <ul className="space-y-0.5">
                {coChangedFiles.slice(0, 4).map((f) => (
                  <li key={f.path}>
                    <button
                      onClick={() => onNavigateFile(f.path)}
                      className="flex w-full items-center justify-between text-left hover:underline"
                    >
                      <span className="truncate font-mono text-xs text-purple-600">
                        {f.path}
                      </span>
                      <span className="ml-2 flex-shrink-0 text-xs text-gray-400">
                        {f.count}×
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
    </>
  );
}
