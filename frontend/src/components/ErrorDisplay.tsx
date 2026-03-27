import type { ApiErrorInfo } from "../types";

interface ErrorDisplayProps {
  error: ApiErrorInfo;
}

function getErrorMessage(error: ApiErrorInfo): string {
  if (error.status === 401) {
    return "Invalid access key. Please check your key and try again.";
  }
  if (error.status && error.status >= 500) {
    return "Server error. The generation service may be temporarily unavailable.";
  }
  if (!error.status) {
    return "Cannot reach the server. Check your connection.";
  }
  return error.message;
}

export function ErrorDisplay({ error }: ErrorDisplayProps) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3">
      <p className="text-sm text-red-700">{getErrorMessage(error)}</p>
    </div>
  );
}
