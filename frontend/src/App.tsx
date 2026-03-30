import { RunSessionProvider, useRunSession } from "./context/RunSessionContext";
import { SetupPage } from "./pages/SetupPage";
import { AnalyzingPage } from "./pages/AnalyzingPage";
import { WorkbenchPage } from "./pages/WorkbenchPage";

function AppRouter() {
  const { viewState } = useRunSession();

  if (viewState === "analyzing") return <AnalyzingPage />;
  if (viewState === "workbench") return <WorkbenchPage />;
  return <SetupPage />;
}

function App() {
  return (
    <RunSessionProvider>
      <AppRouter />
    </RunSessionProvider>
  );
}

export default App;
