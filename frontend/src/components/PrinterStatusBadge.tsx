import type { PrinterStatus } from "../types/api";

const STATUS_STYLES: Record<PrinterStatus, string> = {
  idle: "bg-slate-100 text-slate-700",
  printing: "bg-emerald-100 text-emerald-700",
  paused: "bg-amber-100 text-amber-700",
  error: "bg-red-100 text-red-700",
  offline: "bg-slate-200 text-slate-500",
};

const STATUS_LABELS: Record<PrinterStatus, string> = {
  idle: "Inactiva",
  printing: "Imprimiendo",
  paused: "Pausada",
  error: "Error",
  offline: "Sin conexión",
};

export function PrinterStatusBadge({ status }: { status: PrinterStatus }) {
  return (
    <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ${STATUS_STYLES[status]}`}>
      <span className="mr-1.5 h-1.5 w-1.5 rounded-full bg-current" />
      {STATUS_LABELS[status]}
    </span>
  );
}
