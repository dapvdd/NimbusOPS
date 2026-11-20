import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import {
  Button,
  Card,
  CopyField,
  DescriptionList,
  Dialog,
  Field,
  IconButton,
  InlineAlert,
  Kpi,
  Panel,
  Skeleton,
  StatusBadge,
  Tabs,
  Toast,
} from "../index";

describe("UI Primitives", () => {
  describe("Button & IconButton", () => {
    it("renders primary, secondary, danger, and ghost variants", () => {
      const { rerender } = render(<Button variant="primary">Primary</Button>);
      expect(screen.getByRole("button", { name: "Primary" })).toBeInTheDocument();

      rerender(<Button variant="secondary">Secondary</Button>);
      expect(screen.getByRole("button", { name: "Secondary" })).toBeInTheDocument();

      rerender(<Button variant="danger">Danger</Button>);
      expect(screen.getByRole("button", { name: "Danger" })).toBeInTheDocument();

      rerender(<Button variant="ghost">Ghost</Button>);
      expect(screen.getByRole("button", { name: "Ghost" })).toBeInTheDocument();
    });

    it("displays disabled reason when disabled", () => {
      render(
        <Button disabled disabledReason="Action requires ADMIN role">
          Perform Action
        </Button>
      );
      const btn = screen.getByRole("button", { name: /perform action/i });
      expect(btn).toBeDisabled();
      expect(screen.getByText("Action requires ADMIN role")).toBeInTheDocument();
    });

    it("indicates loading with aria-busy and disabled state", () => {
      render(<Button loading>Submit</Button>);
      const btn = screen.getByRole("button", { name: /submit/i });
      expect(btn).toHaveAttribute("aria-busy", "true");
      expect(btn).toBeDisabled();
    });

    it("requires aria-label on IconButton", () => {
      render(<IconButton aria-label="Refresh list" icon={<span data-testid="icon">↻</span>} />);
      expect(screen.getByRole("button", { name: "Refresh list" })).toBeInTheDocument();
      expect(screen.getByTestId("icon")).toBeInTheDocument();
    });
  });

  describe("Dialog", () => {
    it("traps focus, closes on Escape, restores focus, and has accessible labelling", async () => {
      function DialogTestHarness() {
        const [open, setOpen] = useState(false);
        return (
          <div>
            <button data-testid="trigger" onClick={() => setOpen(true)}>
              Open Dialog
            </button>
            <Dialog
              isOpen={open}
              onClose={() => setOpen(false)}
              title="Confirm Destruction"
            >
              <p>Are you sure you want to delete this host?</p>
              <button data-testid="dialog-action">Confirm</button>
              <button data-testid="dialog-cancel" onClick={() => setOpen(false)}>
                Cancel
              </button>
            </Dialog>
          </div>
        );
      }

      render(<DialogTestHarness />);
      const trigger = screen.getByTestId("trigger");
      trigger.focus();
      expect(document.activeElement).toBe(trigger);

      fireEvent.click(trigger);

      const dialog = screen.getByRole("dialog");
      expect(dialog).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Confirm Destruction" })).toBeInTheDocument();
      expect(dialog).toHaveAttribute("aria-labelledby");

      // Verify focus is inside dialog
      await waitFor(() => {
        expect(dialog.contains(document.activeElement)).toBe(true);
      });

      // Press Escape
      fireEvent.keyDown(dialog, { key: "Escape", code: "Escape" });

      // Dialog should close and focus should be restored to trigger
      await waitFor(() => {
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      });
      expect(document.activeElement).toBe(trigger);
    });
  });

  describe("CopyField", () => {
    it("copies text to clipboard and announces politely", async () => {
      const writeText = vi.fn().mockResolvedValue(undefined);
      vi.stubGlobal("navigator", {
        clipboard: { writeText },
      });

      render(<CopyField value="bstrp-token-12345" label="Bootstrap Token" />);
      expect(screen.getByText("bstrp-token-12345")).toBeInTheDocument();

      const copyBtn = screen.getByRole("button", { name: /copy bootstrap token/i });
      fireEvent.click(copyBtn);

      expect(writeText).toHaveBeenCalledWith("bstrp-token-12345");
      const status = await screen.findByRole("status");
      expect(status).toHaveTextContent(/copied to clipboard/i);
    });
  });

  describe("Toast", () => {
    it("renders with aria-live polite", () => {
      render(<Toast message="Host credential rotated successfully" type="success" onDismiss={() => {}} />);
      const toast = screen.getByRole("status");
      expect(toast).toHaveAttribute("aria-live", "polite");
      expect(toast).toHaveTextContent("Host credential rotated successfully");
    });
  });

  describe("StatusBadge", () => {
    it("renders ONLINE, STALE, OFFLINE, REVOKED, AWAITING, and EXPIRED statuses", () => {
      const { rerender } = render(<StatusBadge status="ONLINE" />);
      expect(screen.getByText("Online")).toBeInTheDocument();

      rerender(<StatusBadge status="STALE" />);
      expect(screen.getByText("Stale")).toBeInTheDocument();

      rerender(<StatusBadge status="OFFLINE" />);
      expect(screen.getByText("Offline")).toBeInTheDocument();

      rerender(<StatusBadge status="REVOKED" />);
      expect(screen.getByText("Revoked")).toBeInTheDocument();

      rerender(<StatusBadge status="AWAITING" />);
      expect(screen.getByText("Awaiting enrollment")).toBeInTheDocument();

      rerender(<StatusBadge status="EXPIRED" />);
      expect(screen.getByText("Token expired")).toBeInTheDocument();

      // Defensive fallback for unknown status
      rerender(<StatusBadge status={"SOME_UNKNOWN" as any} />);
      expect(screen.getByText("Unknown")).toBeInTheDocument();
    });
  });

  describe("Card, Panel, Field, Tabs, DescriptionList, Skeleton, Kpi, InlineAlert", () => {
    it("renders Card and Panel with titles and content", () => {
      render(
        <Panel title="Host Details" actions={<button>Edit</button>}>
          <Card>Inner Card Content</Card>
        </Panel>
      );
      expect(screen.getByText("Host Details")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
      expect(screen.getByText("Inner Card Content")).toBeInTheDocument();
    });

    it("renders Field with accessible label and error alert", () => {
      render(<Field id="hostname" label="Server Hostname" error="Hostname already registered" required />);
      expect(screen.getByLabelText(/server hostname/i)).toBeInTheDocument();
      expect(screen.getByRole("alert")).toHaveTextContent("Hostname already registered");
    });

    it("renders Tabs and manages active tab panel", async () => {
      const tabs = [
        { id: "systemd", label: "systemd Service", content: <div>Systemd script</div> },
        { id: "foreground", label: "Foreground Run", content: <div>Foreground script</div> },
      ];
      render(<Tabs tabs={tabs} defaultTab="systemd" />);

      const tab1 = screen.getByRole("tab", { name: "systemd Service" });
      const tab2 = screen.getByRole("tab", { name: "Foreground Run" });

      expect(tab1).toHaveAttribute("aria-selected", "true");
      expect(screen.getByText("Systemd script")).toBeInTheDocument();
      expect(screen.queryByText("Foreground script")).not.toBeInTheDocument();

      fireEvent.click(tab2);
      expect(tab2).toHaveAttribute("aria-selected", "true");
      expect(screen.getByText("Foreground script")).toBeInTheDocument();
    });

    it("renders DescriptionList with key-value pairs", () => {
      const items = [
        { term: "Agent Version", detail: "0.2.0" },
        { term: "Cores", detail: "8" },
      ];
      render(<DescriptionList items={items} />);
      expect(screen.getByText("Agent Version")).toBeInTheDocument();
      expect(screen.getByText("0.2.0")).toBeInTheDocument();
    });

    it("renders Skeleton and Kpi with tabular numbers", () => {
      render(
        <div>
          <Skeleton className="h-6 w-24" />
          <Kpi label="CPU Usage" value="42.5%" unit="%" />
        </div>
      );
      expect(screen.getByText("CPU Usage")).toBeInTheDocument();
      expect(screen.getByText("42.5%")).toHaveClass("tabular-nums");
    });

    it("renders InlineAlert with alert and status semantics", () => {
      const { rerender } = render(<InlineAlert type="error" message="Fatal network error" />);
      expect(screen.getByRole("alert")).toHaveTextContent("Fatal network error");

      rerender(<InlineAlert type="info" message="Sync complete" />);
      expect(screen.getByRole("status")).toHaveTextContent("Sync complete");
    });
  });
});
