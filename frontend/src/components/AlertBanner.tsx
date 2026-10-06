import type { AlertListItem } from "../types/api";

const SEVERITY_RANK: Record<AlertListItem["severity"], number> = { critical: 0, warning: 1 };

/** Picks the single most urgent thing to show: critical over warning, most recent as the
 * tiebreaker. Only unresolved alerts (new/acknowledged) are candidates - a dismissed or
 * false-positive alert isn't "the most urgent problem right now". Renders nothing when
 * there's nothing active to show, rather than an empty/placeholder banner. */
export function AlertBanner({ alerts }: { alerts: AlertListItem[] }) {
  const active = alerts.filter((a) => a.status === "new" || a.status === "acknowledged");
  if (active.length === 0) return null;

  const top = [...active].sort((a, b) => {
    const severityDiff = SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity];
    if (severityDiff !== 0) return severityDiff;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  })[0];

  const isCritical = top.severity === "critical";

  return (
    <div
      className={`mb-3 flex items-center gap-3 rounded-lg border px-4 py-3 ${
        isCritical ? "border-red-500/40 bg-red-500/10" : "border-amber-500/40 bg-amber-500/10"
      }`}
    >
      <span className={`text-lg ${isCritical ? "text-red-400" : "text-amber-400"}`}>⚠</span>
      <div className="min-w-0 flex-1">
        <p className={`text-sm font-semibold ${isCritical ? "text-red-300" : "text-amber-300"}`}>
          {isCritical ? "Alerta crítica" : "Alerta"} · {top.status === "new" ? "sin revisar" : "reconocida"}
        </p>
        <p className="text-xs text-slate-400">{new Date(top.created_at).toLocaleString()}</p>
      </div>
      {active.length > 1 && (
        <span className="shrink-0 text-xs text-slate-400">+{active.length - 1} más</span>
      )}
    </div>
  );
}
