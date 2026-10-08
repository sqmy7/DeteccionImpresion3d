import { Link } from "react-router-dom";
import { formatDateTime } from "../lib/format";
import type { AlertListItem, AlertStatus } from "../types/api";
import { Badge, Button } from "./ui";

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

const STATUS_LABELS: Record<AlertStatus, string> = {
  new: "Sin revisar",
  acknowledged: "Reconocida",
  dismissed: "Descartada",
  false_positive: "Falso positivo",
};

/** Shared by the alert center (every printer) and the job pages (one job's alerts). */
export function AlertRow({
  alert,
  onTransition,
}: {
  alert: AlertListItem;
  onTransition: (alertId: number, status: AlertStatus) => void;
}) {
  const nextStatuses = ALLOWED_TRANSITIONS[alert.status];
  const critical = alert.severity === "critical";

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-line bg-surface-2/60 p-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-center gap-3">
        <Badge tone={critical ? "danger" : "warn"}>{critical ? "Crítica" : "Aviso"}</Badge>
        <div className="min-w-0">
          <Link to={`/printers/${alert.printer_id}/live`} className="block truncate font-medium text-fg hover:text-accent-fg">
            {alert.printer_name}
          </Link>
          <p className="text-xs text-muted">
            {formatDateTime(alert.created_at)} · {STATUS_LABELS[alert.status]}
          </p>
        </div>
      </div>

      {nextStatuses.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {nextStatuses.map((status) => (
            <Button key={status} size="sm" variant="secondary" onClick={() => onTransition(alert.id, status)}>
              {TRANSITION_LABELS[status]}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}
