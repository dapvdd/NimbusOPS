import React from "react";

export interface DescriptionItem {
  term: React.ReactNode;
  detail: React.ReactNode;
}

export interface DescriptionListProps {
  items: DescriptionItem[];
  className?: string;
}

export function DescriptionList({ items, className = "" }: DescriptionListProps) {
  return (
    <dl className={`divide-y divide-border-subtle ${className}`}>
      {items.map((item, idx) => (
        <div key={idx} className="flex flex-wrap justify-between py-2.5 text-sm">
          <dt className="text-ink-400">{item.term}</dt>
          <dd className="font-medium text-ink-100">{item.detail}</dd>
        </div>
      ))}
    </dl>
  );
}
