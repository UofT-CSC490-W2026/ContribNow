import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  analyze,
  ask,
  generateOnboarding,
  getAuthorship,
  getCoChanges,
  getConventions,
  getDependencies,
  getHotspots,
  getRiskLevels,
  healthCheck,
  ApiError,
} from "./client";
import {
  MOCK_AUTHORSHIP,
  MOCK_CO_CHANGES,
  MOCK_CONVENTIONS,
  MOCK_DEPENDENCIES,
  MOCK_HOTSPOTS,
  MOCK_RISK_LEVELS,
  MOCK_RUN_ID,
} from "./mock-data";

// ── Helpers ───────────────────────────────────────────────────────────────────

function okResponse(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200 });
}

function errResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status });
}

function errResponseText(status: number, text: string) {
  return new Response(text, { status });
}

// ── ApiError ──────────────────────────────────────────────────────────────────

describe("ApiError", () => {
  it("stores status and message", () => {
    const err = new ApiError(401, "Unauthorized");
    expect(err.status).toBe(401);
    expect(err.message).toBe("Unauthorized");
    expect(err.name).toBe("ApiError");
    expect(err).toBeInstanceOf(Error);
  });
});

// ── generateOnboarding (legacy — real mode) ───────────────────────────────────

describe("generateOnboarding", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_USE_MOCK", "false");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  it("sends POST request and returns response", async () => {
    const mockBody = {
      success: true,
      document: "# Onboarding",
      storageKey: "outputs/abc/v1.md",
      fromCache: false,
      version: 1,
    };
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okResponse(mockBody));

    const result = await generateOnboarding({
      repoUrl: "https://github.com/owner/repo",
      accessKey: "key123",
    });

    expect(fetchSpy).toHaveBeenCalledOnce();
    const [url, options] = fetchSpy.mock.calls[0];
    expect(url).toContain("/generate-onboarding");
    expect(options?.method).toBe("POST");
    expect(options?.headers).toEqual({ "Content-Type": "application/json" });
    const body = JSON.parse(options?.body as string);
    expect(body.repoUrl).toBe("https://github.com/owner/repo");
    expect(body.accessKey).toBe("key123");
    expect(result).toEqual(mockBody);
  });

  it("passes abort signal", async () => {
    const controller = new AbortController();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okResponse({ success: true, document: "#", storageKey: null, fromCache: false, version: 1 })
    );

    await generateOnboarding(
      { repoUrl: "https://github.com/a/b", accessKey: "k" },
      controller.signal
    );

    const [, options] = vi.mocked(fetch).mock.calls[0];
    expect(options?.signal).toBe(controller.signal);
  });

  it("throws ApiError with detail on non-ok response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      errResponse(401, { detail: "Invalid access key" })
    );

    await expect(
      generateOnboarding({ repoUrl: "https://github.com/a/b", accessKey: "bad" })
    ).rejects.toSatisfy(
      (e: unknown) => e instanceof ApiError && (e as ApiError).status === 401
    );
  });

  it("throws ApiError with fallback message on non-JSON error body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      errResponseText(500, "Internal Server Error")
    );

    await expect(
      generateOnboarding({ repoUrl: "https://github.com/a/b", accessKey: "k" })
    ).rejects.toSatisfy(
      (e: unknown) => e instanceof ApiError && (e as ApiError).message === "Request failed"
    );
  });

  it("includes optional fields in request body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okResponse({ success: true, document: "#", storageKey: null, fromCache: false, version: 1 })
    );

    await generateOnboarding({
      repoUrl: "https://github.com/a/b",
      accessKey: "k",
      userPrompt: "Focus on auth",
      forceRegenerate: true,
    });

    const body = JSON.parse(vi.mocked(fetch).mock.calls[0][1]?.body as string);
    expect(body.userPrompt).toBe("Focus on auth");
    expect(body.forceRegenerate).toBe(true);
  });
});

// ── generateOnboarding (legacy — mock mode) ───────────────────────────────────

describe("generateOnboarding (mock mode)", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_USE_MOCK", "true");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  it("returns mock data with access key 'test'", async () => {
    const result = await generateOnboarding({
      repoUrl: "https://github.com/pallets/flask",
      accessKey: "test",
    });

    expect(result.success).toBe(true);
    expect(result.document).toContain("pallets/flask");
    expect(result.version).toBe(1);
    expect(result.storageKey).toBeTruthy();
  });

  it("returns fromCache false when forceRegenerate is true", async () => {
    const result = await generateOnboarding({
      repoUrl: "https://github.com/pallets/flask",
      accessKey: "test",
      forceRegenerate: true,
    });

    expect(result.fromCache).toBe(false);
  });

  it("throws 401 for wrong access key in mock mode", async () => {
    await expect(
      generateOnboarding({ repoUrl: "https://github.com/a/b", accessKey: "wrong" })
    ).rejects.toThrow(ApiError);
  });
});

// ── analyze (real mode) ───────────────────────────────────────────────────────

describe("analyze (real mode)", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_USE_MOCK", "false");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  const ANALYZE_RESPONSE = {
    success: true,
    runId: "run-abc",
    document: "# Guide",
    version: 1,
  };

  it("sends POST /analyze and returns response", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okResponse(ANALYZE_RESPONSE));

    const result = await analyze({
      repoUrl: "https://github.com/owner/repo",
      accessKey: "key",
    });

    const [url, options] = fetchSpy.mock.calls[0];
    expect(url).toContain("/analyze");
    expect(options?.method).toBe("POST");
    const body = JSON.parse(options?.body as string);
    expect(body.repoUrl).toBe("https://github.com/owner/repo");
    expect(result).toEqual(ANALYZE_RESPONSE);
  });

  it("includes optional task fields", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(okResponse(ANALYZE_RESPONSE));

    await analyze({
      repoUrl: "https://github.com/a/b",
      accessKey: "k",
      taskType: "fix_bug",
      taskDescription: "Fix the auth bug",
    });

    const body = JSON.parse(vi.mocked(fetch).mock.calls[0][1]?.body as string);
    expect(body.taskType).toBe("fix_bug");
    expect(body.taskDescription).toBe("Fix the auth bug");
  });

  it("passes abort signal", async () => {
    const controller = new AbortController();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(okResponse(ANALYZE_RESPONSE));

    await analyze({ repoUrl: "https://github.com/a/b", accessKey: "k" }, controller.signal);

    const [, options] = vi.mocked(fetch).mock.calls[0];
    expect(options?.signal).toBe(controller.signal);
  });

  it("throws ApiError with detail on non-ok response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      errResponse(401, { detail: "Unauthorized" })
    );

    await expect(
      analyze({ repoUrl: "https://github.com/a/b", accessKey: "bad" })
    ).rejects.toSatisfy(
      (e: unknown) => e instanceof ApiError && (e as ApiError).status === 401 && (e as ApiError).message === "Unauthorized"
    );
  });

  it("throws ApiError with fallback on JSON error without detail", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(errResponse(500, {}));

    await expect(
      analyze({ repoUrl: "https://github.com/a/b", accessKey: "k" })
    ).rejects.toSatisfy(
      (e: unknown) => e instanceof ApiError && (e as ApiError).message === "Request failed"
    );
  });

  it("throws ApiError with fallback on non-JSON error body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      errResponseText(500, "Internal Server Error")
    );

    await expect(
      analyze({ repoUrl: "https://github.com/a/b", accessKey: "k" })
    ).rejects.toSatisfy(
      (e: unknown) => e instanceof ApiError && (e as ApiError).message === "Request failed"
    );
  });
});

// ── analyze (mock mode) ───────────────────────────────────────────────────────

describe("analyze (mock mode)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubEnv("VITE_USE_MOCK", "true");
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllEnvs();
  });

  it("returns runId and document for valid access key", async () => {
    const promise = analyze({
      repoUrl: "https://github.com/pallets/flask",
      accessKey: "test",
    });
    await vi.runAllTimersAsync();
    const result = await promise;

    expect(result.success).toBe(true);
    expect(result.runId).toBe(MOCK_RUN_ID);
    expect(result.document).toContain("pallets/flask");
    expect(result.version).toBe(1);
  });

  it("throws 401 for wrong access key", async () => {
    await expect(
      analyze({ repoUrl: "https://github.com/a/b", accessKey: "wrong" })
    ).rejects.toSatisfy(
      (e: unknown) => e instanceof ApiError && (e as ApiError).status === 401
    );
  });
});

// ── Snapshot functions (real mode) ────────────────────────────────────────────

describe("getHotspots (real mode)", () => {
  beforeEach(() => vi.stubEnv("VITE_USE_MOCK", "false"));
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllEnvs(); });

  it("fetches /snapshot/:runId/hotspots and returns data", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(okResponse(MOCK_HOTSPOTS));
    const result = await getHotspots("run-1");
    expect(vi.mocked(fetch).mock.calls[0][0]).toContain("/snapshot/run-1/hotspots");
    expect(result).toEqual(MOCK_HOTSPOTS);
  });

  it("throws ApiError on non-ok response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(errResponse(404, { detail: "Not found" }));
    await expect(getHotspots("run-1")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("getHotspots (mock mode)", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("returns MOCK_HOTSPOTS without fetching", async () => {
    vi.stubEnv("VITE_USE_MOCK", "true");
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const result = await getHotspots("any");
    expect(result).toEqual(MOCK_HOTSPOTS);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("getRiskLevels (real mode)", () => {
  beforeEach(() => vi.stubEnv("VITE_USE_MOCK", "false"));
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllEnvs(); });

  it("fetches /snapshot/:runId/risk-levels and returns data", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(okResponse(MOCK_RISK_LEVELS));
    const result = await getRiskLevels("run-1");
    expect(vi.mocked(fetch).mock.calls[0][0]).toContain("/snapshot/run-1/risk-levels");
    expect(result).toEqual(MOCK_RISK_LEVELS);
  });

  it("throws ApiError on non-ok response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(errResponse(404, { detail: "Not found" }));
    await expect(getRiskLevels("run-1")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("getRiskLevels (mock mode)", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("returns MOCK_RISK_LEVELS without fetching", async () => {
    vi.stubEnv("VITE_USE_MOCK", "true");
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const result = await getRiskLevels("any");
    expect(result).toEqual(MOCK_RISK_LEVELS);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("getConventions (real mode)", () => {
  beforeEach(() => vi.stubEnv("VITE_USE_MOCK", "false"));
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllEnvs(); });

  it("fetches /snapshot/:runId/conventions and returns data", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(okResponse(MOCK_CONVENTIONS));
    const result = await getConventions("run-1");
    expect(vi.mocked(fetch).mock.calls[0][0]).toContain("/snapshot/run-1/conventions");
    expect(result).toEqual(MOCK_CONVENTIONS);
  });

  it("throws ApiError on non-ok response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(errResponse(500, {}));
    await expect(getConventions("run-1")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("getConventions (mock mode)", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("returns MOCK_CONVENTIONS without fetching", async () => {
    vi.stubEnv("VITE_USE_MOCK", "true");
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const result = await getConventions("any");
    expect(result).toEqual(MOCK_CONVENTIONS);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("getAuthorship (real mode)", () => {
  beforeEach(() => vi.stubEnv("VITE_USE_MOCK", "false"));
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllEnvs(); });

  it("fetches /snapshot/:runId/authorship and returns data", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(okResponse(MOCK_AUTHORSHIP));
    const result = await getAuthorship("run-1");
    expect(vi.mocked(fetch).mock.calls[0][0]).toContain("/snapshot/run-1/authorship");
    expect(result).toEqual(MOCK_AUTHORSHIP);
  });

  it("throws ApiError on non-ok response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(errResponse(404, { detail: "Not found" }));
    await expect(getAuthorship("run-1")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("getAuthorship (mock mode)", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("returns MOCK_AUTHORSHIP without fetching", async () => {
    vi.stubEnv("VITE_USE_MOCK", "true");
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const result = await getAuthorship("any");
    expect(result).toEqual(MOCK_AUTHORSHIP);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("getCoChanges (real mode)", () => {
  beforeEach(() => vi.stubEnv("VITE_USE_MOCK", "false"));
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllEnvs(); });

  it("fetches /snapshot/:runId/co-changes and returns data", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(okResponse(MOCK_CO_CHANGES));
    const result = await getCoChanges("run-1");
    expect(vi.mocked(fetch).mock.calls[0][0]).toContain("/snapshot/run-1/co-changes");
    expect(result).toEqual(MOCK_CO_CHANGES);
  });

  it("throws ApiError on non-ok response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(errResponse(404, { detail: "Not found" }));
    await expect(getCoChanges("run-1")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("getCoChanges (mock mode)", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("returns MOCK_CO_CHANGES without fetching", async () => {
    vi.stubEnv("VITE_USE_MOCK", "true");
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const result = await getCoChanges("any");
    expect(result).toEqual(MOCK_CO_CHANGES);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("getDependencies (real mode)", () => {
  beforeEach(() => vi.stubEnv("VITE_USE_MOCK", "false"));
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllEnvs(); });

  it("fetches /snapshot/:runId/dependencies and returns data", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(okResponse(MOCK_DEPENDENCIES));
    const result = await getDependencies("run-1");
    expect(vi.mocked(fetch).mock.calls[0][0]).toContain("/snapshot/run-1/dependencies");
    expect(result).toEqual(MOCK_DEPENDENCIES);
  });

  it("throws ApiError on non-ok response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(errResponse(404, { detail: "Not found" }));
    await expect(getDependencies("run-1")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("getDependencies (mock mode)", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("returns MOCK_DEPENDENCIES without fetching", async () => {
    vi.stubEnv("VITE_USE_MOCK", "true");
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const result = await getDependencies("any");
    expect(result).toEqual(MOCK_DEPENDENCIES);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

// ── ask (real mode) ───────────────────────────────────────────────────────────

describe("ask (real mode)", () => {
  beforeEach(() => vi.stubEnv("VITE_USE_MOCK", "false"));
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllEnvs(); });

  const ASK_RESPONSE = { answer: "Yes it uses pytest", citations: [] };

  it("sends POST /ask and returns response", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okResponse(ASK_RESPONSE));

    const result = await ask({ runId: "run-1", question: "What test framework?" });

    const [url, options] = fetchSpy.mock.calls[0];
    expect(url).toContain("/ask");
    expect(options?.method).toBe("POST");
    const body = JSON.parse(options?.body as string);
    expect(body.runId).toBe("run-1");
    expect(body.question).toBe("What test framework?");
    expect(result).toEqual(ASK_RESPONSE);
  });

  it("includes conversationHistory in request body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(okResponse(ASK_RESPONSE));

    await ask({
      runId: "run-1",
      question: "Follow-up?",
      conversationHistory: [{ role: "user", content: "Hello" }],
    });

    const body = JSON.parse(vi.mocked(fetch).mock.calls[0][1]?.body as string);
    expect(body.conversationHistory).toHaveLength(1);
  });

  it("throws ApiError on non-ok response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      errResponse(500, { detail: "Server error" })
    );

    await expect(ask({ runId: "run-1", question: "Q?" })).rejects.toBeInstanceOf(ApiError);
  });
});

// ── ask (mock mode) ───────────────────────────────────────────────────────────

describe("ask (mock mode)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubEnv("VITE_USE_MOCK", "true");
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllEnvs();
  });

  it("returns testing answer for 'test' keyword", async () => {
    const promise = ask({ runId: "run-1", question: "How do I run the tests?" });
    await vi.runAllTimersAsync();
    const result = await promise;
    expect(result.answer).toContain("pytest");
    expect(result.citations).toHaveLength(1);
  });

  it("returns testing answer for 'testing' keyword", async () => {
    const promise = ask({ runId: "run-1", question: "What is the testing strategy?" });
    await vi.runAllTimersAsync();
    const result = await promise;
    expect(result.answer).toContain("pytest");
  });

  it("returns setup answer for 'setup' keyword", async () => {
    const promise = ask({ runId: "run-1", question: "How do I setup the project?" });
    await vi.runAllTimersAsync();
    const result = await promise;
    expect(result.answer).toContain("pip install");
    expect(result.citations).toHaveLength(1);
  });

  it("returns setup answer for 'install' keyword", async () => {
    const promise = ask({ runId: "run-1", question: "How do I install dependencies?" });
    await vi.runAllTimersAsync();
    const result = await promise;
    expect(result.answer).toContain("pip install");
  });

  it("returns default answer for unrecognised question", async () => {
    const promise = ask({ runId: "run-1", question: "Who wrote this?" });
    await vi.runAllTimersAsync();
    const result = await promise;
    expect(result.citations).toHaveLength(0);
  });
});

// ── healthCheck ───────────────────────────────────────────────────────────────

describe("healthCheck", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  it("returns true when server responds ok", async () => {
    vi.stubEnv("VITE_USE_MOCK", "false");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response('{"message":"ok"}', { status: 200 })
    );

    expect(await healthCheck()).toBe(true);
  });

  it("returns false when server responds with error", async () => {
    vi.stubEnv("VITE_USE_MOCK", "false");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 500 }));

    expect(await healthCheck()).toBe(false);
  });

  it("returns false when fetch throws", async () => {
    vi.stubEnv("VITE_USE_MOCK", "false");
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("Network error"));

    expect(await healthCheck()).toBe(false);
  });

  it("returns true in mock mode without fetching", async () => {
    vi.stubEnv("VITE_USE_MOCK", "true");
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    expect(await healthCheck()).toBe(true);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
