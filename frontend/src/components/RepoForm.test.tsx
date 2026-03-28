import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RepoForm } from "./RepoForm";

describe("RepoForm", () => {
  const defaultProps = {
    onSubmit: vi.fn(),
    isLoading: false,
    accessKeyPresent: true,
  };

  it("renders URL input and submit button", () => {
    render(<RepoForm {...defaultProps} />);
    expect(screen.getByLabelText("Repository URL")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Generate Onboarding Guide" })
    ).toBeInTheDocument();
  });

  it("submit button is disabled without valid URL", () => {
    render(<RepoForm {...defaultProps} />);
    expect(
      screen.getByRole("button", { name: "Generate Onboarding Guide" })
    ).toBeDisabled();
  });

  it("submit button is disabled when access key is missing", () => {
    render(<RepoForm {...defaultProps} accessKeyPresent={false} />);
    expect(
      screen.getByRole("button", { name: "Generate Onboarding Guide" })
    ).toBeDisabled();
  });

  it("shows warning when access key is missing", () => {
    render(<RepoForm {...defaultProps} accessKeyPresent={false} />);
    expect(
      screen.getByText(/Please enter your access key/)
    ).toBeInTheDocument();
  });

  it("does not show warning when access key is present", () => {
    render(<RepoForm {...defaultProps} accessKeyPresent={true} />);
    expect(
      screen.queryByText(/Please enter your access key/)
    ).not.toBeInTheDocument();
  });

  it("submit button shows Generating... when loading", () => {
    render(<RepoForm {...defaultProps} isLoading={true} />);
    expect(
      screen.getByRole("button", { name: "Generating..." })
    ).toBeInTheDocument();
  });

  it("calls onSubmit with URL on form submission", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<RepoForm {...defaultProps} onSubmit={onSubmit} />);

    await user.type(
      screen.getByLabelText("Repository URL"),
      "https://github.com/owner/repo"
    );
    await user.click(
      screen.getByRole("button", { name: "Generate Onboarding Guide" })
    );

    expect(onSubmit).toHaveBeenCalledWith(
      "https://github.com/owner/repo",
      undefined
    );
  });

  it("shows and hides custom prompt textarea", async () => {
    const user = userEvent.setup();
    render(<RepoForm {...defaultProps} />);

    expect(screen.queryByPlaceholderText(/Focus on/)).not.toBeInTheDocument();

    await user.click(screen.getByText("+ Add custom prompt"));
    expect(screen.getByPlaceholderText(/Focus on/)).toBeInTheDocument();

    await user.click(screen.getByText("- Hide custom prompt"));
    expect(screen.queryByPlaceholderText(/Focus on/)).not.toBeInTheDocument();
  });

  it("passes custom prompt in onSubmit", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<RepoForm {...defaultProps} onSubmit={onSubmit} />);

    await user.type(
      screen.getByLabelText("Repository URL"),
      "https://github.com/a/b"
    );
    await user.click(screen.getByText("+ Add custom prompt"));
    await user.type(
      screen.getByPlaceholderText(/Focus on/),
      "Focus on auth"
    );
    await user.click(
      screen.getByRole("button", { name: "Generate Onboarding Guide" })
    );

    expect(onSubmit).toHaveBeenCalledWith(
      "https://github.com/a/b",
      "Focus on auth"
    );
  });

  it("does not submit when URL is not valid", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<RepoForm {...defaultProps} onSubmit={onSubmit} />);

    await user.type(
      screen.getByLabelText("Repository URL"),
      "not-a-url"
    );
    await user.click(
      screen.getByRole("button", { name: "Generate Onboarding Guide" })
    );

    expect(onSubmit).not.toHaveBeenCalled();
  });
});
