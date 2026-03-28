import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useGenerateOnboarding } from "./useGenerateOnboarding";
import * as client from "../api/client";

vi.mock("../api/client", () => ({
  generateOnboarding: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
      this.name = "ApiError";
    }
  },
}));

const MOCK_RESULT = {
  success: true,
  document: "# Guide",
  storageKey: "key",
  fromCache: false,
  version: 1,
};

describe("useGenerateOnboarding", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("has correct initial state", () => {
    const { result } = renderHook(() => useGenerateOnboarding());
    expect(result.current.result).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("sets loading state and result on successful generate", async () => {
    vi.mocked(client.generateOnboarding).mockResolvedValue(MOCK_RESULT);

    const { result } = renderHook(() => useGenerateOnboarding());

    await act(async () => {
      await result.current.generate({
        repoUrl: "https://github.com/a/b",
        accessKey: "key",
      });
    });

    expect(result.current.result).toEqual(MOCK_RESULT);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("sets error on ApiError", async () => {
    vi.mocked(client.generateOnboarding).mockRejectedValue(
      new client.ApiError(401, "Invalid key")
    );

    const { result } = renderHook(() => useGenerateOnboarding());

    await act(async () => {
      await result.current.generate({
        repoUrl: "https://github.com/a/b",
        accessKey: "bad",
      });
    });

    expect(result.current.result).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toEqual({ message: "Invalid key", status: 401 });
  });

  it("sets generic error on network failure", async () => {
    vi.mocked(client.generateOnboarding).mockRejectedValue(
      new TypeError("Failed to fetch")
    );

    const { result } = renderHook(() => useGenerateOnboarding());

    await act(async () => {
      await result.current.generate({
        repoUrl: "https://github.com/a/b",
        accessKey: "key",
      });
    });

    expect(result.current.error).toEqual({
      message: "Cannot reach the server. Check your connection.",
    });
  });

  it("ignores AbortError", async () => {
    const abortError = new DOMException("Aborted", "AbortError");
    vi.mocked(client.generateOnboarding).mockRejectedValue(abortError);

    const { result } = renderHook(() => useGenerateOnboarding());

    await act(async () => {
      await result.current.generate({
        repoUrl: "https://github.com/a/b",
        accessKey: "key",
      });
    });

    expect(result.current.error).toBeNull();
  });

  it("reset clears all state", async () => {
    vi.mocked(client.generateOnboarding).mockResolvedValue(MOCK_RESULT);

    const { result } = renderHook(() => useGenerateOnboarding());

    await act(async () => {
      await result.current.generate({
        repoUrl: "https://github.com/a/b",
        accessKey: "key",
      });
    });

    expect(result.current.result).toBeTruthy();

    act(() => {
      result.current.reset();
    });

    expect(result.current.result).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("aborts previous request when generate is called again", async () => {
    let resolveFirst: (value: typeof MOCK_RESULT) => void;
    const firstCall = new Promise<typeof MOCK_RESULT>((resolve) => {
      resolveFirst = resolve;
    });

    vi.mocked(client.generateOnboarding)
      .mockImplementationOnce(() => firstCall)
      .mockResolvedValueOnce({ ...MOCK_RESULT, document: "# Second" });

    const { result } = renderHook(() => useGenerateOnboarding());

    // Start first request
    act(() => {
      result.current.generate({
        repoUrl: "https://github.com/a/b",
        accessKey: "key",
      });
    });

    // Start second request (should abort first)
    await act(async () => {
      await result.current.generate({
        repoUrl: "https://github.com/a/c",
        accessKey: "key",
      });
    });

    expect(result.current.result?.document).toBe("# Second");

    // Resolve first (should be ignored since it was aborted)
    resolveFirst!(MOCK_RESULT);
  });
});
