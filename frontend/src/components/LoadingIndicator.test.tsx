import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { LoadingIndicator } from "./LoadingIndicator";

describe("LoadingIndicator", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders initial message", () => {
    render(<LoadingIndicator />);
    expect(screen.getByText("Connecting to server...")).toBeInTheDocument();
  });

  it("renders spinner element", () => {
    const { container } = render(<LoadingIndicator />);
    expect(container.querySelector(".animate-spin")).toBeInTheDocument();
  });

  it("advances message after interval", () => {
    render(<LoadingIndicator />);
    expect(screen.getByText("Connecting to server...")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(
      screen.getByText("Analyzing repository structure...")
    ).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(
      screen.getByText("Generating onboarding guide...")
    ).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.getByText("Almost there...")).toBeInTheDocument();
  });

  it("stays on last message after all messages shown", () => {
    render(<LoadingIndicator />);

    act(() => {
      vi.advanceTimersByTime(20000);
    });
    expect(screen.getByText("Almost there...")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(10000);
    });
    expect(screen.getByText("Almost there...")).toBeInTheDocument();
  });
});
