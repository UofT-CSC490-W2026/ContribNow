import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { analyze, ApiError, loadChatHistory, loadOnboardingDoc } from "../api/client";
import type {
  AnalyzeRequest,
  ApiErrorInfo,
  ChatHistoryEntry,
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
  accessKey: string;
  taskType: TaskType | undefined;
  taskDescription: string | undefined;
  runId: string | null;
  documentRaw: string | null;
  documentSections: DocumentSection[];
  selectedFilePath: string | null;
  analysisError: ApiErrorInfo | null;
  analysisComplete: boolean;
  initialChatHistory: ChatHistoryEntry[];
}

interface RunSessionContextType extends RunSessionState {
  startAnalysis: (req: AnalyzeRequest) => Promise<void>;
  restoreSession: (session: PersistedSession) => Promise<void>;
  selectFile: (path: string | null) => void;
  resetSession: () => void;
}

const INITIAL_STATE: RunSessionState = {
  viewState: "setup",
  repoUrl: "",
  accessKey: "",
  taskType: undefined,
  taskDescription: undefined,
  runId: null,
  documentRaw: null,
  documentSections: [],
  selectedFilePath: null,
  analysisError: null,
  analysisComplete: false,
  initialChatHistory: [],
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
        accessKey: req.accessKey,
        taskType: req.taskType,
        taskDescription: req.taskDescription,
        analysisError: null,
        initialChatHistory: [],
      }));

      try {
        const response = await analyze(req, controller.signal);
        if (controller.signal.aborted) return;

        const sections = parseSections(response.document);
        saveSession({
          runId: response.runId,
          documentRaw: response.document,
          repoUrl: req.repoUrl,
          accessKey: req.accessKey,
          taskType: req.taskType,
          taskDescription: req.taskDescription,
          storageKey: response.storageKey,
          version: response.version,
          savedAt: new Date().toISOString(),
        });

        // Store result but stay on analyzing page briefly so user sees all steps complete
        setState((prev) => ({
          ...prev,
          runId: response.runId,
          documentRaw: response.document,
          documentSections: sections,
          analysisComplete: true,
        }));

        await new Promise((r) => setTimeout(r, 2000));
        if (controller.signal.aborted) return;

        setState((prev) => ({
          ...prev,
          viewState: "workbench",
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

  const restoreSession = useCallback(async (session: PersistedSession) => {
    const sections = parseSections(session.documentRaw);
    setState({
      viewState: "workbench",
      repoUrl: session.repoUrl,
      accessKey: session.accessKey,
      taskType: session.taskType,
      taskDescription: session.taskDescription,
      runId: session.runId,
      documentRaw: session.documentRaw,
      documentSections: sections,
      selectedFilePath: null,
      analysisError: null,
      initialChatHistory: [],
    });

    // Refresh onboarding doc from cloud when possible (avoids re-running analysis)
    try {
      const doc = await loadOnboardingDoc(
        session.runId,
        session.accessKey,
        session.storageKey ?? null
      );
      if (doc.onboarding_docs) {
        const updatedSections = parseSections(doc.onboarding_docs);
        setState((prev) => ({
          ...prev,
          documentRaw: doc.onboarding_docs,
          documentSections: updatedSections,
        }));
        saveSession({
          ...session,
          documentRaw: doc.onboarding_docs,
          savedAt: new Date().toISOString(),
        });
      }
    } catch {
      // Non-fatal: fall back to locally persisted document
    }

    // Load persisted chat history from cloud
    try {
      const result = await loadChatHistory(session.runId, session.accessKey);
      if (result.history.length > 0) {
        setState((prev) => ({ ...prev, initialChatHistory: result.history }));
      }
    } catch {
      // Non-fatal: chat history simply starts empty
    }
  }, [saveSession]);

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
