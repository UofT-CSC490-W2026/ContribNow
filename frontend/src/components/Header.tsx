interface HeaderProps {
  repoUrl?: string;
  onNewAnalysis?: () => void;
}

export function Header({ repoUrl, onNewAnalysis }: HeaderProps = {}) {
  const repoLabel = repoUrl
    ? (() => { try { return new URL(repoUrl).pathname.slice(1); } catch { return repoUrl; } })()
    : null;

  return (
    <header className="border-b border-gray-200 bg-white px-6 py-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-gray-900">ContribNow</h1>
          <span className="rounded-full bg-purple-100 px-2.5 py-0.5 text-xs font-medium text-purple-700">
            beta
          </span>
          {repoLabel && (
            <span className="text-sm text-gray-500 font-mono">{repoLabel}</span>
          )}
        </div>
        {onNewAnalysis && (
          <button
            onClick={onNewAnalysis}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
          >
            New Analysis
          </button>
        )}
      </div>
    </header>
  );
}
