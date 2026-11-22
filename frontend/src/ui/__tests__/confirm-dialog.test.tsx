import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "../ConfirmDialog";

describe("ConfirmDialog keyboard reliability", () => {
  it.each([
    { typed: false, losesFocus: false },
    { typed: false, losesFocus: true },
    { typed: true, losesFocus: false },
    { typed: true, losesFocus: true },
  ])("keeps submission focus trapped while busy and restores the original trigger: %j", ({ typed, losesFocus }) => {
    function Harness({ open = true }: { open?: boolean }) {
      const [busy, setBusy] = useState(false);
      return <ConfirmDialog
        isOpen={open}
        busy={busy}
        title="Delete host"
        expectedValue={typed ? "DELETE" : undefined}
        onClose={() => {}}
        onConfirm={() => {
          // jsdom does not blur newly disabled buttons as Chromium may do.
          if (losesFocus && document.activeElement instanceof HTMLElement) document.activeElement.blur();
          setBusy(true);
        }}
      />;
    }
    const trigger = document.createElement("button");
    document.body.append(trigger);
    trigger.focus();
    const { rerender, unmount } = render(<Harness />);
    try {
      if (typed) fireEvent.change(screen.getByRole("textbox"), { target: { value: "DELETE" } });
      const confirm = screen.getByRole("button", { name: "Confirm" });
      confirm.focus();
      fireEvent.click(confirm);
      expect(confirm).toBeDisabled();
      const target = typed ? screen.getByRole("textbox") : screen.getByRole("dialog");
      expect(target).toHaveFocus();
      expect(fireEvent.keyDown(target, { key: "Tab" })).toBe(false);
      expect(target).toHaveFocus();
      expect(fireEvent.keyDown(target, { key: "Tab", shiftKey: true })).toBe(false);
      expect(target).toHaveFocus();
      rerender(<Harness open={false} />);
      expect(trigger).toHaveFocus();
    } finally {
      unmount();
      trigger.remove();
    }
  });

  it("focuses Cancel when no typed confirmation is required", () => {
    render(<ConfirmDialog isOpen title="Delete host" onClose={() => {}} onConfirm={() => {}} />);
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
  });

  it("focuses the typed input and skips the disabled confirmation when wrapping Tab", () => {
    render(<ConfirmDialog isOpen title="Delete host" expectedValue="DELETE" onClose={() => {}} onConfirm={() => {}} />);
    const input = screen.getByRole("textbox");
    const cancel = screen.getByRole("button", { name: "Cancel" });
    expect(input).toHaveFocus();
    fireEvent.keyDown(input, { key: "Tab", shiftKey: true });
    expect(cancel).toHaveFocus();
    fireEvent.keyDown(cancel, { key: "Tab" });
    expect(input).toHaveFocus();
  });

  it("includes confirmation in the focus loop only after the expected value matches", () => {
    render(<ConfirmDialog isOpen title="Delete host" expectedValue="DELETE" onClose={() => {}} onConfirm={() => {}} />);
    const input = screen.getByRole("textbox");
    const confirm = screen.getByRole("button", { name: "Confirm" });
    fireEvent.change(input, { target: { value: "DELETE" } });
    fireEvent.keyDown(input, { key: "Tab", shiftKey: true });
    expect(confirm).toHaveFocus();
    fireEvent.keyDown(confirm, { key: "Tab" });
    expect(input).toHaveFocus();
  });

  it("wraps both directions without a typed input", () => {
    render(<ConfirmDialog isOpen title="Delete host" onClose={() => {}} onConfirm={() => {}} />);
    const cancel = screen.getByRole("button", { name: "Cancel" });
    const confirm = screen.getByRole("button", { name: "Confirm" });
    cancel.focus();
    fireEvent.keyDown(cancel, { key: "Tab", shiftKey: true });
    expect(confirm).toHaveFocus();
    fireEvent.keyDown(confirm, { key: "Tab" });
    expect(cancel).toHaveFocus();
  });

  it("keeps focus on the dialog when busy leaves no enabled controls", () => {
    render(<ConfirmDialog isOpen busy title="Delete host" onClose={() => {}} onConfirm={() => {}} />);
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveFocus();
    expect(fireEvent.keyDown(dialog, { key: "Tab" })).toBe(false);
    expect(dialog).toHaveFocus();
    expect(fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true })).toBe(false);
    expect(dialog).toHaveFocus();
  });

  it("ignores Escape while busy and closes after busy clears", () => {
    const onClose = vi.fn();
    const props = { isOpen: true, title: "Delete host", onClose, onConfirm: vi.fn() };
    const { rerender } = render(<ConfirmDialog {...props} busy />);
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
    rerender(<ConfirmDialog {...props} busy={false} />);
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(props.onConfirm).not.toHaveBeenCalled();
  });

  it.each([false, true])("restores trigger focus on close and unmount (typed: %s)", (typed) => {
    function Harness({ mounted = true }: { mounted?: boolean }) {
      const [open, setOpen] = useState(false);
      return <>
        <button onClick={() => setOpen(true)}>Open</button>
        {mounted && <ConfirmDialog isOpen={open} title="Delete host" expectedValue={typed ? "DELETE" : undefined} onClose={() => setOpen(false)} onConfirm={() => {}} />}
      </>;
    }
    const { rerender } = render(<Harness />);
    const trigger = screen.getByRole("button", { name: "Open" });
    trigger.focus();
    fireEvent.click(trigger);
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    fireEvent.click(trigger);
    // Keep the trigger mounted while removing the dialog itself.
    rerender(<Harness mounted={false} />);
    expect(trigger).toHaveFocus();
  });

  it("preserves typed confirmation gating, busy protection, and reset on reopen", () => {
    const onConfirm = vi.fn();
    const props = { title: "Delete host", expectedValue: "DELETE", onClose: vi.fn(), onConfirm };
    const { rerender } = render(<ConfirmDialog {...props} isOpen />);
    const confirm = screen.getByRole("button", { name: "Confirm" });
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "delete" } });
    fireEvent.click(confirm);
    expect(onConfirm).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: " DELETE " } });
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledTimes(1);
    rerender(<ConfirmDialog {...props} isOpen busy />);
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    rerender(<ConfirmDialog {...props} isOpen={false} />);
    rerender(<ConfirmDialog {...props} isOpen />);
    expect(screen.getByRole("textbox")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
  });
});
