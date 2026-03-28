import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface OnboardingDocumentProps {
  document: string;
  fromCache: boolean;
  version: number | null;
  onForceRegenerate: () => void;
}

export function OnboardingDocument({
  document,
  fromCache,
  version,
  onForceRegenerate,
}: OnboardingDocumentProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between rounded-lg border border-gray-200 bg-gray-50 px-4 py-2">
        <span className="text-sm text-gray-600">
          {fromCache ? (
            <>
              <span className="font-medium text-amber-600">Cached</span>
              {version != null && ` - v${version}`}
            </>
          ) : (
            <>
              <span className="font-medium text-green-600">
                Freshly generated
              </span>
              {version != null && ` - v${version}`}
            </>
          )}
        </span>
        {fromCache && (
          <button
            onClick={onForceRegenerate}
            className="text-sm text-purple-600 hover:text-purple-800"
          >
            Regenerate
          </button>
        )}
      </div>

      <article className="prose prose-slate max-w-none rounded-lg border border-gray-200 bg-white p-6">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{document}</ReactMarkdown>
      </article>
    </div>
  );
}
