import React, { useState } from "react";

export interface TabItem {
  id: string;
  label: string;
  content: React.ReactNode;
}

export interface TabsProps {
  tabs: TabItem[];
  defaultTab?: string;
  className?: string;
}

export function Tabs({ tabs, defaultTab, className = "" }: TabsProps) {
  const [activeTab, setActiveTab] = useState(defaultTab || tabs[0]?.id);

  const currentTab = tabs.find((t) => t.id === activeTab) || tabs[0];

  return (
    <div className={`space-y-4 ${className}`}>
      <div
        role="tablist"
        aria-label="Configuration Options"
        className="flex gap-2 border-b border-border-subtle"
      >
        {tabs.map((tab) => {
          const isSelected = tab.id === activeTab;
          return (
            <button
              key={tab.id}
              role="tab"
              id={`tab-${tab.id}`}
              aria-controls={`panel-${tab.id}`}
              aria-selected={isSelected}
              tabIndex={isSelected ? 0 : -1}
              onClick={() => setActiveTab(tab.id)}
              className={`border-b-2 px-4 py-2.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-info ${
                isSelected
                  ? "border-signal-info text-signal-info"
                  : "border-transparent text-ink-400 hover:text-ink-200"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      {currentTab && (
        <div
          role="tabpanel"
          id={`panel-${currentTab.id}`}
          aria-labelledby={`tab-${currentTab.id}`}
          tabIndex={0}
          className="focus-visible:outline-none"
        >
          {currentTab.content}
        </div>
      )}
    </div>
  );
}
