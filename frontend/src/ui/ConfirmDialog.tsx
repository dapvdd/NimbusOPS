import { useState, useEffect, useRef, type KeyboardEvent } from "react";
import { Button } from "./Button";

export interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  description?: string;
  consequences?: string[];
  expectedValue?: string;
  inputLabel?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "danger" | "warn" | "primary";
  busy?: boolean;
  error?: string | null;
  onConfirm: () => void | Promise<void>;
  onClose: () => void;
}

export function ConfirmDialog({
  isOpen,
  title,
  description,
  consequences,
  expectedValue,
  inputLabel,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  variant = "danger",
  busy = false,
  error,
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  const [typedValue, setTypedValue] = useState("");
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    const trigger = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const dialog = dialogRef.current;
    setTypedValue("");
    const initialFocus = dialog?.querySelector<HTMLElement>("input, button:not(:disabled)");
    (initialFocus ?? dialog)?.focus();

    return () => {
      if (trigger?.isConnected) trigger.focus();
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || !busy) return;
    const dialog = dialogRef.current;
    if (!dialog) return;
    const active = document.activeElement;
    // Disabling the submitting button can leave focus there or drop it to body.
    // Keep this separate from the open lifecycle so trigger restoration is preserved.
    if (!dialog.contains(active) || active?.matches(":disabled")) {
      const enabledControl = dialog.querySelector<HTMLElement>("input:not(:disabled), button:not(:disabled)");
      (enabledControl ?? dialog).focus();
    }
  }, [isOpen, busy]);

  if (!isOpen) return null;

  const requiresMatch = expectedValue !== undefined && expectedValue !== "";
  const isMatch = !requiresMatch || typedValue.trim() === expectedValue.trim();
  const canConfirm = isMatch && !busy;

  const handleConfirm = () => {
    if (!canConfirm) return;
    void onConfirm();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      if (!busy) onClose();
      return;
    }
    if (event.key !== "Tab") return;

    const dialog = dialogRef.current;
    if (!dialog) return;
    const controls = Array.from(dialog.querySelectorAll<HTMLElement>("input:not(:disabled), button:not(:disabled)"));
    const first = controls[0];
    const last = controls[controls.length - 1];
    const active = document.activeElement;

    if (!first || !controls.some((control) => control === active)) {
      event.preventDefault();
      (event.shiftKey ? last ?? dialog : first ?? dialog).focus();
    } else if (event.shiftKey && active === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <div
      ref={dialogRef}
      role="dialog"
      tabIndex={-1}
      onKeyDown={handleKeyDown}
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-950/80 backdrop-blur-sm"
    >
      <div className="w-full max-w-lg rounded-xl border border-ink-700 bg-surface-2 p-6 shadow-2xl">
        <h2 id="confirm-dialog-title" className="text-xl font-semibold text-ink-50">
          {title}
        </h2>

        {description && <p className="mt-2 text-sm text-ink-300">{description}</p>}

        {consequences && consequences.length > 0 && (
          <ul className="my-4 list-disc space-y-1 pl-5 text-sm text-ink-300">
            {consequences.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        )}

        {requiresMatch && (
          <div className="my-4 space-y-1.5">
            <label htmlFor="confirm-typed-input" className="block text-sm font-medium text-ink-200">
              {inputLabel || (
                <>
                  Type <span className="font-mono text-signal-bad font-semibold">{expectedValue}</span> to confirm
                </>
              )}
            </label>
            <input
              id="confirm-typed-input"
              type="text"
              className="block w-full rounded-lg border border-ink-600 bg-ink-900 p-2.5 font-mono text-sm text-ink-100 placeholder-ink-500 focus:border-signal-info focus:outline-none"
              placeholder={expectedValue}
              value={typedValue}
              onChange={(e) => setTypedValue(e.target.value)}
            />
          </div>
        )}

        {error && (
          <p role="alert" className="mt-3 text-sm text-signal-bad">
            {error}
          </p>
        )}

        <div className="mt-6 flex items-center justify-end gap-3">
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
            disabled={busy}
          >
            {cancelLabel}
          </Button>
          <Button
            type="button"
            variant={variant === "danger" ? "danger" : "primary"}
            onClick={handleConfirm}
            disabled={!canConfirm}
            loading={busy}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
