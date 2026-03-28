import { type FormEvent, useState } from "react";

interface RepoFormProps {
  onSubmit: (repoUrl: string, userPrompt: string | undefined) => void;
  isLoading: boolean;
  accessKeyPresent: boolean;
}

export function RepoForm({
  onSubmit,
  isLoading,
  accessKeyPresent,
}: RepoFormProps) {
  const [repoUrl, setRepoUrl] = useState("");
  const [userPrompt, setUserPrompt] = useState("");
  const [showPrompt, setShowPrompt] = useState(false);

  const isValidUrl = repoUrl.startsWith("https://") || repoUrl.startsWith("http://");
  const canSubmit = accessKeyPresent && isValidUrl && !isLoading;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    /* v8 ignore next */
    if (!canSubmit) return;

    const normalizedUrl = repoUrl.trim();
    onSubmit(normalizedUrl, userPrompt.trim() || undefined);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label
          htmlFor="repo-url"
          className="block text-sm font-medium text-gray-700"
        >
          Repository URL
        </label>
        <input
          id="repo-url"
          type="url"
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
          placeholder="https://github.com/owner/repo"
          className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-purple-500 focus:ring-1 focus:ring-purple-500 focus:outline-none"
        />
      </div>

      <div>
        <button
          type="button"
          onClick={() => setShowPrompt(!showPrompt)}
          className="text-sm text-purple-600 hover:text-purple-800"
        >
          {showPrompt ? "- Hide custom prompt" : "+ Add custom prompt"}
        </button>
        {showPrompt && (
          <textarea
            value={userPrompt}
            onChange={(e) => setUserPrompt(e.target.value)}
            placeholder="e.g., Focus on the authentication module..."
            rows={3}
            className="mt-2 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-purple-500 focus:ring-1 focus:ring-purple-500 focus:outline-none"
          />
        )}
      </div>

      <button
        type="submit"
        disabled={!canSubmit}
        className="w-full rounded-lg bg-purple-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-purple-700 focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 focus:outline-none disabled:cursor-not-allowed disabled:bg-gray-300"
      >
        {isLoading ? "Generating..." : "Generate Onboarding Guide"}
      </button>

      {!accessKeyPresent && (
        <p className="text-center text-xs text-amber-600">
          Please enter your access key above
        </p>
      )}
    </form>
  );
}
