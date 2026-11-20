import React from "react";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
}

export function Card({ children, className = "", ...props }: CardProps) {
  return (
    <div
      className={`rounded-xl border border-border-subtle bg-surface-2 p-5 text-ink-100 ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
