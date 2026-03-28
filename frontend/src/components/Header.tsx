export function Header() {
  return (
    <header className="border-b border-gray-200 bg-white px-6 py-4">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold text-gray-900">ContribNow</h1>
        <span className="rounded-full bg-purple-100 px-2.5 py-0.5 text-xs font-medium text-purple-700">
          beta
        </span>
      </div>
      <p className="mt-1 text-sm text-gray-500">
        AI-powered onboarding guides for open-source repositories
      </p>
    </header>
  );
}
