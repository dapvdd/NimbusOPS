import { useState, useEffect } from "react";
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

  useEffect(() => {
    if (isOpen) {
      setTypedValue("");
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const requiresMatch = expectedValue !== undefined && expectedValue !== "";
  const isMatch = !requiresMatch || typedValue.trim() === expectedValue.trim();
  const canConfirm = isMatch && !busy;

  const handleConfirm = () => {
    if (!canConfirm) return;
    void onConfirm();
  };

  return (
    <div
      role="dialog"
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
              autoFocus
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
