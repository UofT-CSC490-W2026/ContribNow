import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { analyze, ApiError } from "../api/client";
import type {
  AnalyzeRequest,
  ApiErrorInfo,
  DocumentSection,
  TaskType,
  ViewState,
} from "../types";
import { parseSections } from "../utils/parseSections";
import {
  useSessionPersistence,
  type PersistedSession,
} from "../hooks/useSessionPersistence";

interface RunSessionState {
  viewState: ViewState;
  repoUrl: string;
  taskType: TaskType | undefined;
  taskDescription: string | undefined;
  runId: string | null;
  documentRaw: string | null;
  documentSections: DocumentSection[];
  selectedFilePath: string | null;
  analysisError: ApiErrorInfo | null;
}

interface RunSessionContextType extends RunSessionState {
  startAnalysis: (req: AnalyzeRequest) => Promise<void>;
  restoreSession: (session: PersistedSession) => void;
  selectFile: (path: string | null) => void;
  resetSession: () => void;
}

const INITIAL_STATE: RunSessionState = {
  viewState: "setup",
  repoUrl: "",
  taskType: undefined,
  taskDescription: undefined,
  runId: null,
  documentRaw: null,
  documentSections: [],
  selectedFilePath: null,
  analysisError: null,
};

const RunSessionContext = createContext<RunSessionContextType | null>(null);

export function RunSessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<RunSessionState>(INITIAL_STATE);
  const abortRef = useRef<AbortController | null>(null);
  const { saveSession, clearSession } = useSessionPersistence();

  const startAnalysis = useCallback(
    async (req: AnalyzeRequest) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setState((prev) => ({
        ...prev,
        viewState: "analyzing",
        repoUrl: req.repoUrl,
        taskType: req.taskType,
        taskDescription: req.taskDescription,
        analysisError: null,
      }));

      try {
        const response = await analyze(req, controller.signal);
        if (controller.signal.aborted) return;

        const sections = parseSections(response.document);
        saveSession({
          runId: response.runId,
          documentRaw: response.document,
          repoUrl: req.repoUrl,
          taskType: req.taskType,
          taskDescription: req.taskDescription,
          version: response.version,
          savedAt: new Date().toISOString(),
        });

        setState((prev) => ({
          ...prev,
          viewState: "workbench",
          runId: response.runId,
          documentRaw: response.document,
          documentSections: sections,
        }));
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        const analysisError: ApiErrorInfo =
          err instanceof ApiError
            ? { message: err.message, status: err.status }
            : { message: "Analysis failed. Please try again." };
        setState((prev) => ({ ...prev, analysisError }));
      }
    },
    [saveSession]
  );

  const restoreSession = useCallback((session: PersistedSession) => {
    const sections = parseSections(session.documentRaw);
    setState({
      viewState: "workbench",
      repoUrl: session.repoUrl,
      taskType: session.taskType,
      taskDescription: session.taskDescription,
      runId: session.runId,
      documentRaw: session.documentRaw,
      documentSections: sections,
      selectedFilePath: null,
      analysisError: null,
    });
  }, []);

  const selectFile = useCallback((path: string | null) => {
    setState((prev) => ({ ...prev, selectedFilePath: path }));
  }, []);

  const resetSession = useCallback(() => {
    abortRef.current?.abort();
    clearSession();
    setState(INITIAL_STATE);
  }, [clearSession]);

  return (
    <RunSessionContext.Provider
      value={{ ...state, startAnalysis, restoreSession, selectFile, resetSession }}
    >
      {children}
    </RunSessionContext.Provider>
  );
}

export function useRunSession(): RunSessionContextType {
  const ctx = useContext(RunSessionContext);
  if (!ctx) throw new Error("useRunSession must be used inside RunSessionProvider");
  return ctx;
}
