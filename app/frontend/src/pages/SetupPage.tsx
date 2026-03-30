import { type FormEvent, useState } from "react";
import { Header } from "../components/Header";
import { AccessKeyInput } from "../components/AccessKeyInput";
import { TaskSelector } from "../components/TaskSelector";
import { ResumeSessionBanner } from "../components/ResumeSessionBanner";
import { useAccessKey } from "../hooks/useAccessKey";
import { useRunSession } from "../context/RunSessionContext";
import type { TaskType } from "../types";

export function SetupPage() {
  const [accessKey, setAccessKey] = useAccessKey();
  const { startAnalysis } = useRunSession();

  const [repoUrl, setRepoUrl] = useState("");
  const [taskType, setTaskType] = useState<TaskType | undefined>(undefined);
  const [taskDescription, setTaskDescription] = useState<string | undefined>(undefined);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const isValidUrl =
    repoUrl.startsWith("https://") || repoUrl.startsWith("http://");
  const canSubmit = accessKey.length > 0 && isValidUrl && !isSubmitting;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setIsSubmitting(true);
    await startAnalysis({
      repoUrl: repoUrl.trim(),
      accessKey,
      taskType,
      taskDescription: taskType === "other" ? taskDescription : undefined,
    });
    setIsSubmitting(false);
  };

  const handleTaskChange = (
    type: TaskType | undefined,
    desc: string | undefined
  ) => {
    setTaskType(type);
    setTaskDescription(desc);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main className="mx-auto max-w-xl px-4 py-8">
        <div className="space-y-4">
          <ResumeSessionBanner />

          <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
            <form onSubmit={handleSubmit} className="space-y-5">
              <AccessKeyInput value={accessKey} onChange={setAccessKey} />

              <hr className="border-gray-200" />

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

              <hr className="border-gray-200" />

              <TaskSelector
                value={taskType}
                description={taskDescription}
                onChange={handleTaskChange}
              />

              <button
                type="submit"
                disabled={!canSubmit}
                className="w-full rounded-lg bg-purple-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-purple-700 focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 focus:outline-none disabled:cursor-not-allowed disabled:bg-gray-300"
              >
                {isSubmitting ? "Analyzing..." : "Analyze Repository"}
              </button>

              {accessKey.length === 0 && (
                <p className="text-center text-xs text-amber-600">
                  Please enter your access key above
                </p>
              )}
            </form>
          </div>
        </div>
      </main>
    </div>
  );
}
