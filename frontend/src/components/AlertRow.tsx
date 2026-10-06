import type { AlertListItem, AlertStatus } from "../types/api";

// new -> acknowledged/dismissed/false_positive; acknowledged -> dismissed/false_positive;
// mirrors app/services/alerts.py's _ALLOWED_TRANSITIONS exactly.
const ALLOWED_TRANSITIONS: Record<AlertStatus, AlertStatus[]> = {
  new: ["acknowledged", "dismissed", "false_positive"],
  acknowledged: ["dismissed", "false_positive"],
  dismissed: [],
  false_positive: [],
};

const TRANSITION_LABELS: Record<AlertStatus, string> = {
  new: "Nueva",
  acknowledged: "Reconocer",
  dismissed: "Descartar",
  false_positive: "Falso positivo",
};

/** Shared between AlertCenterPage (all alerts, light theme) and the embedded job dashboard
 * panel (this job's alerts, dark theme) - `dark` only swaps the row chrome, not the logic. */
export function AlertRow({
  alert,
  onTransition,
  dark = false,
}: {
  alert: AlertListItem;
  onTransition: (alertId: number, status: AlertStatus) => void;
  dark?: boolean;
}) {
  const severityClasses = dark
    ? alert.severity === "critical"
      ? "bg-red-500/15 text-red-400"
      : "bg-amber-500/15 text-amber-400"
    : alert.severity === "critical"
      ? "bg-red-100 text-red-700"
      : "bg-amber-100 text-amber-700";
  const nextStatuses = ALLOWED_TRANSITIONS[alert.status];

  return (
    <div
      className={
        dark
          ? "flex flex-col gap-2 rounded-lg border border-slate-800 bg-slate-900 p-3 sm:flex-row sm:items-center sm:justify-between"
          : "flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between"
      }
    >
      <div className="flex items-center gap-3">
        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold uppercase ${severityClasses}`}>
          {alert.severity}
        </span>
        <div>
          <p className={dark ? "font-medium text-slate-100" : "font-medium text-slate-900"}>{alert.printer_name}</p>
          <p className={dark ? "text-xs text-slate-400" : "text-xs text-slate-500"}>
            {new Date(alert.created_at).toLocaleString()} · {alert.status}
          </p>
        </div>
      </div>

      {nextStatuses.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {nextStatuses.map((status) => (
            <button
              key={status}
              onClick={() => onTransition(alert.id, status)}
              className={
                dark
                  ? "rounded-md border border-slate-700 px-2.5 py-1 text-xs font-medium text-slate-300 hover:bg-slate-800"
                  : "rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100"
              }
            >
              {TRANSITION_LABELS[status]}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
