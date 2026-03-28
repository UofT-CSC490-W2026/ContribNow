import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ErrorDisplay } from "./ErrorDisplay";

describe("ErrorDisplay", () => {
  it("shows invalid access key message for 401", () => {
    render(<ErrorDisplay error={{ message: "Unauthorized", status: 401 }} />);
    expect(
      screen.getByText(/Invalid access key/)
    ).toBeInTheDocument();
  });

  it("shows server error message for 500", () => {
    render(<ErrorDisplay error={{ message: "Internal error", status: 500 }} />);
    expect(screen.getByText(/Server error/)).toBeInTheDocument();
  });

  it("shows server error message for other 5xx", () => {
    render(<ErrorDisplay error={{ message: "Bad gateway", status: 502 }} />);
    expect(screen.getByText(/Server error/)).toBeInTheDocument();
  });

  it("shows network error message when no status", () => {
    render(
      <ErrorDisplay error={{ message: "Cannot reach the server. Check your connection." }} />
    );
    expect(screen.getByText(/Cannot reach the server/)).toBeInTheDocument();
  });

  it("shows raw message for other status codes", () => {
    render(
      <ErrorDisplay error={{ message: "Something weird happened", status: 422 }} />
    );
    expect(
      screen.getByText("Something weird happened")
    ).toBeInTheDocument();
  });
});
