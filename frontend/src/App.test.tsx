import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import * as useAccessKeyModule from "./hooks/useAccessKey";
import * as useGenerateModule from "./hooks/useGenerateOnboarding";

vi.mock("./hooks/useAccessKey");
vi.mock("./hooks/useGenerateOnboarding");

const mockGenerate = vi.fn();
const mockReset = vi.fn();

function setupMocks(overrides: {
  accessKey?: string;
  result?: ReturnType<typeof useGenerateModule.useGenerateOnboarding>["result"];
  isLoading?: boolean;
  error?: ReturnType<typeof useGenerateModule.useGenerateOnboarding>["error"];
} = {}) {
  const setAccessKey = vi.fn();
  vi.mocked(useAccessKeyModule.useAccessKey).mockReturnValue([
    overrides.accessKey ?? "",
    setAccessKey,
  ]);
  vi.mocked(useGenerateModule.useGenerateOnboarding).mockReturnValue({
    result: overrides.result ?? null,
    isLoading: overrides.isLoading ?? false,
    error: overrides.error ?? null,
    generate: mockGenerate,
    reset: mockReset,
  });
  return { setAccessKey };
}

describe("App", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders header, access key input, and form", () => {
    setupMocks();
    render(<App />);
    expect(screen.getByText("ContribNow")).toBeInTheDocument();
    expect(screen.getByLabelText("Access Key")).toBeInTheDocument();
    expect(screen.getByLabelText("Repository URL")).toBeInTheDocument();
  });

  it("shows loading indicator when isLoading", () => {
    setupMocks({ isLoading: true });
    render(<App />);
    expect(screen.getByText("Connecting to server...")).toBeInTheDocument();
  });

  it("does not show loading indicator when not loading", () => {
    setupMocks({ isLoading: false });
    render(<App />);
    expect(screen.queryByText("Connecting to server...")).not.toBeInTheDocument();
  });

  it("shows error display when error exists", () => {
    setupMocks({ error: { message: "Unauthorized", status: 401 } });
    render(<App />);
    expect(screen.getByText(/Invalid access key/)).toBeInTheDocument();
  });

  it("shows onboarding document when result is successful", () => {
    setupMocks({
      result: {
        success: true,
        document: "# Test Guide",
        storageKey: "k",
        fromCache: false,
        version: 1,
      },
    });
    render(<App />);
    expect(screen.getByText("Test Guide")).toBeInTheDocument();
    expect(screen.getByText("Freshly generated")).toBeInTheDocument();
  });

  it("does not show document when result is null", () => {
    setupMocks({ result: null });
    render(<App />);
    expect(screen.queryByText("Freshly generated")).not.toBeInTheDocument();
  });

  it("calls generate on form submit", async () => {
    const user = userEvent.setup();
    setupMocks({ accessKey: "test-key" });
    render(<App />);

    await user.type(
      screen.getByLabelText("Repository URL"),
      "https://github.com/a/b"
    );
    await user.click(
      screen.getByRole("button", { name: "Generate Onboarding Guide" })
    );

    expect(mockReset).toHaveBeenCalled();
    expect(mockGenerate).toHaveBeenCalledWith({
      repoUrl: "https://github.com/a/b",
      accessKey: "test-key",
      userPrompt: undefined,
    });
  });

  it("calls generate with forceRegenerate on regenerate click", async () => {
    const user = userEvent.setup();
    setupMocks({
      accessKey: "key",
      result: {
        success: true,
        document: "# Cached",
        storageKey: "k",
        fromCache: true,
        version: 2,
      },
    });
    render(<App />);

    // First we need to trigger a submit to populate lastRequestRef
    await user.type(
      screen.getByLabelText("Repository URL"),
      "https://github.com/a/b"
    );
    await user.click(
      screen.getByRole("button", { name: "Generate Onboarding Guide" })
    );

    mockGenerate.mockClear();

    await user.click(screen.getByRole("button", { name: "Regenerate" }));

    expect(mockGenerate).toHaveBeenCalledWith({
      repoUrl: "https://github.com/a/b",
      accessKey: "key",
      userPrompt: undefined,
      forceRegenerate: true,
    });
  });

  it("does nothing on regenerate if no previous request", async () => {
    const user = userEvent.setup();
    setupMocks({
      accessKey: "key",
      result: {
        success: true,
        document: "# Cached",
        storageKey: "k",
        fromCache: true,
        version: 2,
      },
    });
    render(<App />);

    // Click regenerate without ever submitting
    await user.click(screen.getByRole("button", { name: "Regenerate" }));
    expect(mockGenerate).not.toHaveBeenCalled();
  });
});
