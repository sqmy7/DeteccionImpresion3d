import type { ReactNode } from "react";
import type { Tone } from "./Badge";

const VALUE_TONES: Record<Tone, string> = {
  neutral: "text-fg",
  accent: "text-accent-fg",
  ok: "text-ok-fg",
  warn: "text-warn-fg",
  danger: "text-danger-fg",
  info: "text-info-fg",
};

/** A labelled figure: value with unit, an optional secondary line (target, trend, context). */
export function Kpi({
  label,
  value,
  unit,
  hint,
  tone = "neutral",
  icon,
  title,
}: {
  label: ReactNode;
  value: ReactNode;
  unit?: ReactNode;
  hint?: ReactNode;
  tone?: Tone;
  icon?: ReactNode;
  title?: string;
}) {
  return (
    <div className="min-w-0 rounded-xl border border-line bg-surface px-4 py-3" title={title}>
      <div className="flex items-center gap-1.5 text-xs font-medium text-muted">
        {icon && <span className="shrink-0 text-faint">{icon}</span>}
        <span className="truncate">{label}</span>
      </div>
      <p className={`mt-1 truncate text-2xl font-semibold tabular ${VALUE_TONES[tone]}`}>
        {value}
        {unit && <span className="ml-1 text-sm font-normal text-muted">{unit}</span>}
      </p>
      {hint && <p className="mt-0.5 truncate text-xs text-faint">{hint}</p>}
    </div>
  );
}
