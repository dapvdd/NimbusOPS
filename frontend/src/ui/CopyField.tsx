import { useState } from "react";

export interface CopyFieldProps {
  value: string;
  label?: string;
  secret?: boolean;
  className?: string;
}

export function CopyField({ value, label, secret = false, className = "" }: CopyFieldProps) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState('');
  const [revealed, setRevealed] = useState(!secret);

  const handleCopy = async () => {
    setCopied(false); setCopyError('');
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 3000);
    } catch {
      setCopied(false);
      setCopyError('Copy failed. Select the text and copy it manually.');
    }
  };

  return (
    <div className={`space-y-1.5 ${className}`}>
      {label && <label className="block text-xs font-medium text-ink-300">{label}</label>}
      <div className="flex items-center gap-2">
        <code className="flex-1 break-all rounded-lg border border-border-strong bg-surface-0 p-3 font-mono text-sm text-ink-100 select-all">
          {secret && !revealed ? "•".repeat(Math.min(value.length, 32)) : value}
        </code>
        {secret && (
          <button
            type="button"
            onClick={() => setRevealed(!revealed)}
            className="inline-flex min-h-[44px] items-center justify-center rounded-lg border border-border-strong bg-surface-3 px-3 py-2 text-xs font-medium text-ink-100 transition-colors hover:bg-ink-700 focus-visible:outline-2 focus-visible:outline-signal-info"
          >
            {revealed ? "Hide" : "Show"}
          </button>
        )}
        <button
          type="button"
          onClick={handleCopy}
          aria-label={label ? `Copy ${label}` : "Copy to clipboard"}
          className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg border border-border-strong bg-surface-3 px-4 py-2 text-xs font-medium text-ink-100 transition-colors hover:bg-ink-700 focus-visible:outline-2 focus-visible:outline-signal-info"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <div aria-live="polite" className="h-4">
        {copyError && <p role="alert" className="text-xs text-signal-bad">{copyError}</p>}
        {copied && (
          <p role="status" className="text-xs text-signal-ok">
            Copied to clipboard.
          </p>
        )}
      </div>
    </div>
  );
}
