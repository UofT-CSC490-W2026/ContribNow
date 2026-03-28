import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AccessKeyInput } from "./AccessKeyInput";

describe("AccessKeyInput", () => {
  it("renders with label", () => {
    render(<AccessKeyInput value="" onChange={() => {}} />);
    expect(screen.getByLabelText("Access Key")).toBeInTheDocument();
  });

  it("displays the provided value", () => {
    render(<AccessKeyInput value="my-key" onChange={() => {}} />);
    expect(screen.getByLabelText("Access Key")).toHaveValue("my-key");
  });

  it("defaults to password type", () => {
    render(<AccessKeyInput value="" onChange={() => {}} />);
    expect(screen.getByLabelText("Access Key")).toHaveAttribute(
      "type",
      "password"
    );
  });

  it("toggles visibility when Show/Hide is clicked", async () => {
    const user = userEvent.setup();
    render(<AccessKeyInput value="secret" onChange={() => {}} />);

    const input = screen.getByLabelText("Access Key");
    expect(input).toHaveAttribute("type", "password");

    await user.click(screen.getByText("Show"));
    expect(input).toHaveAttribute("type", "text");

    await user.click(screen.getByText("Hide"));
    expect(input).toHaveAttribute("type", "password");
  });

  it("calls onChange when typing", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<AccessKeyInput value="" onChange={onChange} />);

    await user.type(screen.getByLabelText("Access Key"), "a");
    expect(onChange).toHaveBeenCalledWith("a");
  });
});
