import { useState } from "react";
import { Header } from "../components/Header";
import { OnboardingGuide } from "../components/OnboardingGuide";
import { FileExplorer } from "../components/FileExplorer";
import { FileDetailPanel } from "../components/FileDetailPanel";
import { ConventionsChecklist } from "../components/ConventionsChecklist";
import { ChatPanel } from "../components/ChatPanel";
import { useRunSession } from "../context/RunSessionContext";
import { useHotspots } from "../hooks/useHotspots";
import { useRiskLevels } from "../hooks/useRiskLevels";
import { useAuthorship } from "../hooks/useAuthorship";
import { useCoChanges } from "../hooks/useCoChanges";
import { useConventions } from "../hooks/useConventions";

function LeftPanel() {
  const { runId, selectedFilePath, selectFile } = useRunSession();
  const [anchorRect, setAnchorRect] = useState<DOMRect | null>(null);

  const { data: hotspots } = useHotspots(runId);
  const { data: riskLevels } = useRiskLevels(runId);
  const { data: authorship, isLoading: authorshipLoading } = useAuthorship(runId);
  const { data: coChanges, isLoading: coChangesLoading } = useCoChanges(runId);
  const { data: conventions, isLoading: conventionsLoading } = useConventions(runId);

  const isDetailLoading = authorshipLoading || coChangesLoading;

  const handleSelectFile = (path: string, rect: DOMRect) => {
    setAnchorRect(rect);
    selectFile(path);
  };

  const handleClose = () => {
    setAnchorRect(null);
    selectFile(null);
  };

  const fileRisk = riskLevels.find((r) => r.path === selectedFilePath);
  const fileHotspot = hotspots.find((h) => h.path === selectedFilePath);
  const fileAuthorship = authorship.find((a) => a.path === selectedFilePath);
  const coChangedFiles = selectedFilePath
    ? coChanges
        .filter(
          (p) => p.file_a === selectedFilePath || p.file_b === selectedFilePath
        )
        .map((p) => ({
          path: p.file_a === selectedFilePath ? p.file_b : p.file_a,
          count: p.co_change_count,
        }))
        .sort((a, b) => b.count - a.count)
    : [];

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <FileExplorer
          hotspots={hotspots}
          riskLevels={riskLevels}
          selectedFilePath={selectedFilePath}
          onSelectFile={handleSelectFile}
        />
      </div>
      <ConventionsChecklist conventions={conventions} isLoading={conventionsLoading} />

      {selectedFilePath && anchorRect && (
        <FileDetailPanel
          filePath={selectedFilePath}
          anchorRect={anchorRect}
          riskLevel={fileRisk}
          hotspot={fileHotspot}
          authorship={fileAuthorship}
          coChangedFiles={coChangedFiles}
          isLoading={isDetailLoading}
          onClose={handleClose}
          onNavigateFile={(path) => {
            selectFile(path);
            // anchorRect stays the same when navigating between co-changed files
          }}
        />
      )}
    </div>
  );
}

function RightPanel() {
  const { documentSections, documentRaw } = useRunSession();
  return (
    <div className="h-full overflow-hidden">
      <OnboardingGuide
        sections={documentSections}
        rawDocument={documentRaw ?? ""}
      />
    </div>
  );
}


export function WorkbenchPage() {
  const { repoUrl, runId, resetSession } = useRunSession();

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-gray-50">
      <Header repoUrl={repoUrl} onNewAnalysis={resetSession} />

      <div className="flex min-h-0 flex-1">
        {/* Left panel — 35% */}
        <div className="w-[35%] min-w-0 border-r border-gray-200 bg-white">
          <LeftPanel />
        </div>

        {/* Right panel — 65% */}
        <div className="min-w-0 flex-1 bg-white">
          <RightPanel />
        </div>
      </div>

      {runId && <ChatPanel runId={runId} />}
    </div>
  );
}
