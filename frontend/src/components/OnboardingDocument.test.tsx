import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OnboardingDocument } from "./OnboardingDocument";

describe("OnboardingDocument", () => {
  const defaultProps = {
    document: "# Hello World\n\nThis is a test.",
    fromCache: false,
    version: 1,
    onForceRegenerate: vi.fn(),
  };

  it("renders markdown content", () => {
    render(<OnboardingDocument {...defaultProps} />);
    expect(screen.getByText("Hello World")).toBeInTheDocument();
    expect(screen.getByText("This is a test.")).toBeInTheDocument();
  });

  it("shows freshly generated badge when not from cache", () => {
    render(<OnboardingDocument {...defaultProps} fromCache={false} />);
    expect(screen.getByText("Freshly generated")).toBeInTheDocument();
  });

  it("shows version number", () => {
    render(<OnboardingDocument {...defaultProps} version={3} />);
    expect(screen.getByText(/v3/)).toBeInTheDocument();
  });

  it("does not show version when null", () => {
    render(<OnboardingDocument {...defaultProps} version={null} />);
    expect(screen.queryByText(/- v/)).not.toBeInTheDocument();
  });

  it("shows cached badge when from cache", () => {
    render(<OnboardingDocument {...defaultProps} fromCache={true} />);
    expect(screen.getByText("Cached")).toBeInTheDocument();
  });

  it("shows regenerate button when from cache", () => {
    render(<OnboardingDocument {...defaultProps} fromCache={true} />);
    expect(
      screen.getByRole("button", { name: "Regenerate" })
    ).toBeInTheDocument();
  });

  it("does not show regenerate button when not from cache", () => {
    render(<OnboardingDocument {...defaultProps} fromCache={false} />);
    expect(screen.queryByRole("button", { name: "Regenerate" })).not.toBeInTheDocument();
  });

  it("calls onForceRegenerate when regenerate is clicked", async () => {
    const user = userEvent.setup();
    const onForceRegenerate = vi.fn();
    render(
      <OnboardingDocument
        {...defaultProps}
        fromCache={true}
        onForceRegenerate={onForceRegenerate}
      />
    );

    await user.click(screen.getByRole("button", { name: "Regenerate" }));
    expect(onForceRegenerate).toHaveBeenCalledOnce();
  });

  it("renders GFM tables", () => {
    const md = "| Col A | Col B |\n|---|---|\n| val1 | val2 |";
    render(<OnboardingDocument {...defaultProps} document={md} />);
    expect(screen.getByText("val1")).toBeInTheDocument();
    expect(screen.getByText("val2")).toBeInTheDocument();
  });
});
