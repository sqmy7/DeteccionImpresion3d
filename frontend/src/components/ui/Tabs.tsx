import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

export interface TabItem<T extends string> {
  value: T;
  label: ReactNode;
  icon?: ReactNode;
  count?: number;
}

/** Tabs that switch local state. Arrow keys move between them, as in the WAI-ARIA tabs pattern. */
export function Tabs<T extends string>({
  items,
  value,
  onChange,
  className = "",
}: {
  items: TabItem<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
}) {
  const move = (direction: number) => {
    const index = items.findIndex((item) => item.value === value);
    const next = items[(index + direction + items.length) % items.length];
    onChange(next.value);
  };

  return (
    <div
      role="tablist"
      className={`flex gap-1 overflow-x-auto border-b border-line ${className}`}
      onKeyDown={(event) => {
        if (event.key === "ArrowRight") move(1);
        if (event.key === "ArrowLeft") move(-1);
      }}
    >
      {items.map((item) => {
        const selected = item.value === value;
        return (
          <button
            key={item.value}
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(item.value)}
            className={`-mb-px inline-flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
              selected ? "border-accent text-fg" : "border-transparent text-muted hover:text-fg"
            }`}
          >
            {item.icon}
            {item.label}
            {item.count !== undefined && (
              <span className="rounded bg-surface-3 px-1.5 text-[11px] tabular text-muted">{item.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** Same look, but each tab is a route. */
export function RouteTabs({ items }: { items: { to: string; label: ReactNode; icon?: ReactNode; end?: boolean }[] }) {
  return (
    <nav className="flex gap-1 overflow-x-auto border-b border-line">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            `-mb-px inline-flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
              isActive ? "border-accent text-fg" : "border-transparent text-muted hover:text-fg"
            }`
          }
        >
          {item.icon}
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}
