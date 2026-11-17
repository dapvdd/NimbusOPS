import React from "react";

export interface FieldProps {
  id: string;
  label: string;
  required?: boolean;
  error?: string;
  hint?: string;
  children?: React.ReactNode;
}

export function Field({
  id,
  label,
  required = false,
  error,
  hint,
  children,
}: FieldProps) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium text-ink-200">
        {label}
        {required && <span className="ml-1 text-signal-bad">*</span>}
      </label>
      {children ? (
        children
      ) : (
        <input
          id={id}
          required={required}
          className="block w-full rounded-lg border border-border-strong bg-surface-1 p-2.5 text-sm text-ink-100 placeholder-ink-500 focus:border-signal-info focus:outline-none"
        />
      )}
      {hint && !error && <p className="text-xs text-ink-400">{hint}</p>}
      {error && (
        <p id={`${id}-error`} role="alert" className="text-xs text-signal-bad">
          {error}
        </p>
      )}
    </div>
  );
}
