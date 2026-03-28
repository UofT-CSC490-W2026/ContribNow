import { useRef } from "react";
import { useAccessKey } from "./hooks/useAccessKey";
import { useGenerateOnboarding } from "./hooks/useGenerateOnboarding";
import { Header } from "./components/Header";
import { AccessKeyInput } from "./components/AccessKeyInput";
import { RepoForm } from "./components/RepoForm";
import { LoadingIndicator } from "./components/LoadingIndicator";
import { ErrorDisplay } from "./components/ErrorDisplay";
import { OnboardingDocument } from "./components/OnboardingDocument";

function App() {
  const [accessKey, setAccessKey] = useAccessKey();
  const { result, isLoading, error, generate, reset } =
    useGenerateOnboarding();
  const lastRequestRef = useRef<{ repoUrl: string; userPrompt?: string } | null>(null);

  const handleSubmit = (repoUrl: string, userPrompt: string | undefined) => {
    lastRequestRef.current = { repoUrl, userPrompt };
    reset();
    generate({ repoUrl, accessKey, userPrompt });
  };

  const handleForceRegenerate = () => {
    if (!lastRequestRef.current) return;
    const { repoUrl, userPrompt } = lastRequestRef.current;
    generate({ repoUrl, accessKey, userPrompt, forceRegenerate: true });
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main className="mx-auto max-w-3xl px-4 py-8">
        <div className="space-y-6">
          <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
            <div className="space-y-4">
              <AccessKeyInput value={accessKey} onChange={setAccessKey} />
              <hr className="border-gray-200" />
              <RepoForm
                onSubmit={handleSubmit}
                isLoading={isLoading}
                accessKeyPresent={accessKey.length > 0}
              />
            </div>
          </div>

          {isLoading && <LoadingIndicator />}
          {error && <ErrorDisplay error={error} />}
          {result?.success && (
            <OnboardingDocument
              document={result.document}
              fromCache={result.fromCache}
              version={result.version}
              onForceRegenerate={handleForceRegenerate}
            />
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
