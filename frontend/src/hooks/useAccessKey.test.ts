import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useAccessKey } from "./useAccessKey";

describe("useAccessKey", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("returns empty string when no stored key", () => {
    const { result } = renderHook(() => useAccessKey());
    expect(result.current[0]).toBe("");
  });

  it("reads initial value from localStorage", () => {
    localStorage.setItem("contribnow_access_key", "stored-key");
    const { result } = renderHook(() => useAccessKey());
    expect(result.current[0]).toBe("stored-key");
  });

  it("updates state and localStorage when setter is called", () => {
    const { result } = renderHook(() => useAccessKey());

    act(() => {
      result.current[1]("new-key");
    });

    expect(result.current[0]).toBe("new-key");
    expect(localStorage.getItem("contribnow_access_key")).toBe("new-key");
  });

  it("overwrites existing localStorage value", () => {
    localStorage.setItem("contribnow_access_key", "old-key");
    const { result } = renderHook(() => useAccessKey());

    act(() => {
      result.current[1]("updated-key");
    });

    expect(result.current[0]).toBe("updated-key");
    expect(localStorage.getItem("contribnow_access_key")).toBe("updated-key");
  });
});
