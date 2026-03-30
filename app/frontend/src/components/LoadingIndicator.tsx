import { useEffect, useState } from "react";

const MESSAGES = [
  "Connecting to server...",
  "Analyzing repository structure...",
  "Generating onboarding guide...",
  "Almost there...",
];

export function LoadingIndicator() {
  const [messageIndex, setMessageIndex] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setMessageIndex((i) => (i + 1 < MESSAGES.length ? i + 1 : i));
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex flex-col items-center gap-4 py-12">
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-gray-200 border-t-purple-600" />
      <p className="text-sm text-gray-600">{MESSAGES[messageIndex]}</p>
    </div>
  );
}
