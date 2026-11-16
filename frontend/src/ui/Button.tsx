import React from "react";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md";
  loading?: boolean;
  disabledReason?: string;
  icon?: React.ReactNode;
}

const VARIANTS = {
  primary: "bg-signal-info text-ink-950 font-semibold hover:bg-blue-400 border border-signal-info",
  secondary: "bg-surface-3 text-ink-100 hover:bg-ink-700 border border-border-strong",
  danger: "bg-signal-bad text-ink-950 font-semibold hover:bg-red-400 border border-signal-bad",
  ghost: "bg-transparent text-ink-200 hover:text-ink-100 hover:bg-surface-3 border border-transparent",
};

const SIZES = {
  sm: "px-2.5 py-1 text-xs min-h-[32px]",
  md: "px-4 py-2 text-sm min-h-[40px]",
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    children,
    variant = "primary",
    size = "md",
    loading = false,
    disabled = false,
    disabledReason,
    className = "",
    icon,
    ...props
  },
  ref
) {
  const isDisabled = disabled || loading;

  const buttonElement = (
    <button
      ref={ref}
      disabled={isDisabled}
      aria-busy={loading ? "true" : undefined}
      title={disabledReason || props.title}
      className={`inline-flex items-center justify-center gap-2 rounded-lg transition-colors focus-visible:outline-2 focus-visible:outline-signal-info disabled:opacity-50 disabled:cursor-not-allowed ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...props}
    >
      {loading ? (
        <>
          <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
          <span>{children}</span>
        </>
      ) : (
        <>
          {icon && <span className="inline-flex shrink-0">{icon}</span>}
          {children}
        </>
      )}
    </button>
  );

  if (disabledReason && disabled) {
    return (
      <div className="inline-flex flex-col items-start gap-1">
        {buttonElement}
        <span className="text-xs text-ink-400" role="note">
          {disabledReason}
        </span>
      </div>
    );
  }

  return buttonElement;
});
