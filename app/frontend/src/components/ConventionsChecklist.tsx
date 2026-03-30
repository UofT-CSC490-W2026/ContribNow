import { useState } from "react";
import type { Conventions } from "../types";

interface ConventionsChecklistProps {
  conventions: Conventions | null;
  isLoading: boolean;
}

interface CheckItem {
  label: string;
  detail?: string;
}

function buildItems(conventions: Conventions): CheckItem[] {
  const items: CheckItem[] = [];

  if (conventions.test_framework) {
    items.push({
      label: `Testing: ${conventions.test_framework.name}`,
      detail: conventions.test_framework.config_path,
    });
  }

  for (const ci of conventions.ci_pipelines ?? []) {
    items.push({ label: `CI: ${ci.platform}`, detail: ci.config_path });
  }

  if ((conventions.linters ?? []).length > 0) {
    items.push({ label: `Linters: ${conventions.linters.map((l) => l.name).join(", ")}` });
  }

  for (const doc of conventions.contribution_docs ?? []) {
    items.push({ label: `Docs: ${doc}` });
  }

  if (conventions.package_manager) {
    items.push({ label: `Package manager: ${conventions.package_manager}` });
  }

  if ((conventions.test_dirs ?? []).length > 0) {
    items.push({ label: `Test dirs: ${conventions.test_dirs.join(", ")}` });
  }

  return items;
}

export function ConventionsChecklist({ conventions, isLoading }: ConventionsChecklistProps) {
  const [open, setOpen] = useState(true);

  return (
    <div className="border-t border-gray-200">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-4 py-2 hover:bg-gray-50"
      >
        <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          Conventions
        </span>
        <span className="text-xs text-gray-400">{open ? "▾" : "▸"}</span>
      </button>

      {open && (
        <div className="px-4 pb-3">
          {isLoading ? (
            <p className="text-xs text-gray-400">Loading...</p>
          ) : !conventions ? (
            <p className="text-xs text-gray-400">No conventions detected.</p>
          ) : (
            (() => {
              const items = buildItems(conventions);
              if (items.length === 0)
                return <p className="text-xs text-gray-400">No conventions detected.</p>;
              return (
                <ul className="space-y-1">
                  {items.map((item, i) => (
                    <li key={i} className="flex items-start gap-1.5 text-xs text-gray-700">
                      <span className="mt-px flex-shrink-0 text-green-500">✅</span>
                      <span>
                        {item.label}
                        {item.detail && (
                          <span className="ml-1 font-mono text-gray-400">({item.detail})</span>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              );
            })()
          )}
        </div>
      )}
    </div>
  );
}
