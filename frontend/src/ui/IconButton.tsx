import React from "react";

export interface IconButtonProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  "aria-label": string;
  icon: React.ReactNode;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md";
}

const VARIANTS = {
  primary: "bg-signal-info text-ink-950 hover:bg-blue-400 border border-signal-info",
  secondary: "bg-surface-3 text-ink-100 hover:bg-ink-700 border border-border-strong",
  danger: "bg-signal-bad text-ink-950 hover:bg-red-400 border border-signal-bad",
  ghost: "bg-transparent text-ink-200 hover:text-ink-100 hover:bg-surface-3 border border-transparent",
};

const SIZES = {
  sm: "w-8 h-8 p-1 text-xs",
  md: "w-10 h-10 p-2 text-sm",
};

export const IconButton = React.forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  {
    "aria-label": ariaLabel,
    icon,
    variant = "ghost",
    size = "md",
    className = "",
    ...props
  },
  ref
) {
  return (
    <button
      ref={ref}
      aria-label={ariaLabel}
      className={`inline-flex items-center justify-center rounded-lg transition-colors focus-visible:outline-2 focus-visible:outline-signal-info disabled:opacity-50 disabled:cursor-not-allowed ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...props}
    >
      {icon}
    </button>
  );
});
