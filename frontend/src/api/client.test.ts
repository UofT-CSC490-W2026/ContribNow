import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { generateOnboarding, healthCheck, ApiError } from "./client";

const MOCK_RESPONSE = {
  success: true,
  document: "# Onboarding",
  storageKey: "outputs/abc/v1.md",
  fromCache: false,
  version: 1,
};

describe("ApiError", () => {
  it("stores status and message", () => {
    const err = new ApiError(401, "Unauthorized");
    expect(err.status).toBe(401);
    expect(err.message).toBe("Unauthorized");
    expect(err.name).toBe("ApiError");
    expect(err).toBeInstanceOf(Error);
  });
});

describe("generateOnboarding", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_USE_MOCK", "false");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  it("sends POST request and returns response", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(MOCK_RESPONSE), { status: 200 })
    );

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

    expect(result).toEqual(MOCK_RESPONSE);
  });

  it("passes abort signal", async () => {
    const controller = new AbortController();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(MOCK_RESPONSE), { status: 200 })
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
      new Response(JSON.stringify({ detail: "Invalid access key" }), {
        status: 401,
      })
    );

    try {
      await generateOnboarding({
        repoUrl: "https://github.com/a/b",
        accessKey: "bad",
      });
      expect.fail("should have thrown");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as ApiError).status).toBe(401);
      expect((e as ApiError).message).toBe("Invalid access key");
    }
  });

  it("throws ApiError with fallback message on non-JSON error body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("Internal Server Error", { status: 500 })
    );

    try {
      await generateOnboarding({
        repoUrl: "https://github.com/a/b",
        accessKey: "k",
      });
      expect.fail("should have thrown");
    } catch (e) {
      expect((e as ApiError).status).toBe(500);
      expect((e as ApiError).message).toBe("Request failed");
    }
  });

  it("includes optional fields in request body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(MOCK_RESPONSE), { status: 200 })
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
      generateOnboarding({
        repoUrl: "https://github.com/a/b",
        accessKey: "wrong",
      })
    ).rejects.toThrow(ApiError);
  });
});

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
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("", { status: 500 })
    );

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
