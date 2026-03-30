import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { DocumentSection } from "../types";

interface OnboardingGuideProps {
  sections: DocumentSection[];
  rawDocument: string;
}

export function OnboardingGuide({ sections, rawDocument }: OnboardingGuideProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Fallback: no sections parsed — render full document
  if (sections.length === 0) {
    return (
      <div className="h-full overflow-y-auto p-6">
        <article className="prose prose-slate max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{rawDocument}</ReactMarkdown>
        </article>
      </div>
    );
  }

  const activeSection = sections[activeIndex];

  return (
    <div className="flex h-full overflow-hidden">
      {/* Sidebar */}
      <div
        className={`flex flex-shrink-0 flex-col border-r border-gray-200 bg-gray-50 transition-all duration-200 ${
          sidebarOpen ? "w-44" : "w-10"
        }`}
      >
        {/* Toggle button */}
        <button
          onClick={() => setSidebarOpen((o) => !o)}
          className="flex h-9 w-full items-center justify-center border-b border-gray-200 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          aria-label={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
        >
          {sidebarOpen ? "‹" : "›"}
        </button>

        {/* Section list */}
        <nav className="flex-1 overflow-y-auto py-2">
          {sections.map((section, i) => (
            <button
              key={i}
              onClick={() => setActiveIndex(i)}
              className={`w-full px-2 py-1.5 text-left transition-colors ${
                i === activeIndex
                  ? "bg-purple-50 text-purple-700"
                  : "text-gray-600 hover:bg-gray-100"
              }`}
              title={sidebarOpen ? undefined : section.title}
            >
              {sidebarOpen ? (
                <span className="block truncate text-xs font-medium leading-snug">
                  {section.title}
                </span>
              ) : (
                <span
                  className={`mx-auto block h-2 w-2 rounded-full ${
                    i === activeIndex ? "bg-purple-500" : "bg-gray-300"
                  }`}
                />
              )}
            </button>
          ))}
        </nav>
      </div>

      {/* Section content */}
      <div className="min-w-0 flex-1 overflow-y-auto p-6">
        <h2 className="mb-4 text-lg font-semibold text-gray-900">
          {activeSection.title}
        </h2>
        <article className="prose prose-slate max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {activeSection.content}
          </ReactMarkdown>
        </article>
      </div>
    </div>
  );
}
