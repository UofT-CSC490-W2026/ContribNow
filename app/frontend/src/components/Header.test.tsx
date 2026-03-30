import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Header } from "./Header";

describe("Header", () => {
  it("renders the app name", () => {
    render(<Header />);
    expect(screen.getByText("ContribNow")).toBeInTheDocument();
  });

  it("renders beta badge", () => {
    render(<Header />);
    expect(screen.getByText("beta")).toBeInTheDocument();
  });

  it("renders tagline", () => {
    render(<Header />);
    expect(
      screen.getByText(/AI-powered onboarding guides/)
    ).toBeInTheDocument();
  });
});
