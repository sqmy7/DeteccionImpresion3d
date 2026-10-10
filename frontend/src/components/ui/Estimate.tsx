import { ChevronDown, Info } from "lucide-react";
import type { ReactNode } from "react";

/** Marks a derived value as an estimate and explains, folded, how it is computed. Every derived
 * figure (position on the bed, combined score, printer health, energy and cost) carries one. */
export function EstimateNote({ title, children, className = "" }: { title: string; children: ReactNode; className?: string }) {
  return (
    <details className={`group rounded-lg border border-line/70 bg-surface-2/40 text-xs text-muted ${className}`}>
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 hover:text-fg [&::-webkit-details-marker]:hidden">
        <Info size={13} className="shrink-0 text-info-fg" />
        <span>
          <span className="font-medium text-info-fg">Estimación</span> · {title}
        </span>
        <ChevronDown size={13} className="ml-auto shrink-0 transition-transform group-open:rotate-180" />
      </summary>
      <div className="flex flex-col gap-2 border-t border-line/70 px-3 py-2.5 leading-relaxed">{children}</div>
    </details>
  );
}
