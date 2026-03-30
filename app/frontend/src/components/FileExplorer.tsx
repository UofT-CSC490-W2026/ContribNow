import { useState } from "react";
import type { Hotspot, RiskLevel } from "../types";

interface FileExplorerProps {
  hotspots: Hotspot[];
  riskLevels: RiskLevel[];
  selectedFilePath: string | null;
  onSelectFile: (path: string, rect: DOMRect) => void;
}

interface FileEntry {
  path: string;
  name: string;
  touch_count: number;
  risk_level: "high" | "medium" | "low";
  risk_score: number;
}

interface FileGroup {
  directory: string;
  files: FileEntry[];
  aggregateRisk: "high" | "medium" | "low";
}

function riskDot(level: "high" | "medium" | "low") {
  if (level === "high") return <span className="h-2.5 w-2.5 flex-shrink-0 rounded-full bg-red-500" />;
  if (level === "medium") return <span className="h-2.5 w-2.5 flex-shrink-0 rounded-full bg-yellow-400" />;
  return <span className="h-2.5 w-2.5 flex-shrink-0 rounded-full bg-green-500" />;
}

const RISK_ORDER = { high: 0, medium: 1, low: 2 };

function aggregateRisk(files: FileEntry[]): "high" | "medium" | "low" {
  return files.reduce<"high" | "medium" | "low">(
    (best, f) => (RISK_ORDER[f.risk_level] < RISK_ORDER[best] ? f.risk_level : best),
    "low"
  );
}

function buildGroups(hotspots: Hotspot[], riskLevels: RiskLevel[]): FileGroup[] {
  const riskMap = new Map(riskLevels.map((r) => [r.path, r]));

  const entries: FileEntry[] = hotspots.map((h) => {
    const risk = riskMap.get(h.path);
    return {
      path: h.path,
      name: h.path.split("/").pop() ?? h.path,
      touch_count: h.touch_count,
      risk_level: risk?.risk_level ?? "low",
      risk_score: risk?.risk_score ?? 0,
    };
  });

  const groupMap = new Map<string, FileEntry[]>();
  for (const entry of entries) {
    const parts = entry.path.split("/");
    const dir = parts.length > 1 ? parts[0] : "(root)";
    if (!groupMap.has(dir)) groupMap.set(dir, []);
    groupMap.get(dir)!.push(entry);
  }

  return Array.from(groupMap.entries()).map(([directory, files]) => {
    files.sort((a, b) => b.touch_count - a.touch_count);
    return { directory, files, aggregateRisk: aggregateRisk(files) };
  });
}

export function FileExplorer({
  hotspots,
  riskLevels,
  selectedFilePath,
  onSelectFile,
}: FileExplorerProps) {
  const [collapsedDirs, setCollapsedDirs] = useState<Set<string>>(new Set());

  const groups = buildGroups(hotspots, riskLevels);

  const toggleDir = (dir: string) => {
    setCollapsedDirs((prev) => {
      const next = new Set(prev);
      next.has(dir) ? next.delete(dir) : next.add(dir);
      return next;
    });
  };

  if (groups.length === 0) {
    return (
      <div className="p-4 text-sm text-gray-400">No file data available.</div>
    );
  }

  return (
    <div className="flex flex-col">
      <div className="flex items-center justify-between border-b border-gray-100 px-4 py-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          File Explorer
        </span>
      </div>

      <div className="overflow-y-auto">
        {groups.map((group) => {
          const collapsed = collapsedDirs.has(group.directory);
          return (
            <div key={group.directory}>
              {/* Group header */}
              <button
                onClick={() => toggleDir(group.directory)}
                className="flex w-full items-center gap-2 px-4 py-1.5 hover:bg-gray-50"
              >
                <span className="text-xs text-gray-400">{collapsed ? "▶" : "▼"}</span>
                <span className="flex-1 truncate text-left text-xs font-semibold text-gray-700">
                  {group.directory}/
                </span>
                {riskDot(group.aggregateRisk)}
              </button>

              {/* File items */}
              {!collapsed &&
                group.files.map((file) => (
                  <button
                    key={file.path}
                    onClick={(e) => onSelectFile(file.path, e.currentTarget.getBoundingClientRect())}
                    className={`flex w-full items-center gap-2 py-1.5 pl-8 pr-4 text-left transition-colors hover:bg-gray-50 ${
                      selectedFilePath === file.path ? "bg-purple-50" : ""
                    }`}
                  >
                    <span
                      className={`flex-1 truncate text-xs ${
                        selectedFilePath === file.path
                          ? "font-medium text-purple-700"
                          : "text-gray-600"
                      }`}
                    >
                      {file.name}
                    </span>
                    <span className="flex-shrink-0 text-xs text-gray-400">
                      {file.touch_count}
                    </span>
                    {riskDot(file.risk_level)}
                  </button>
                ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
