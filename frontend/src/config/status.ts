import type { Tone } from "../components/ui";
import type { JobStatus, PrinterStatus } from "../types/api";

export const PRINTER_STATUS: Record<PrinterStatus, { label: string; tone: Tone }> = {
  idle: { label: "Inactiva", tone: "neutral" },
  printing: { label: "Imprimiendo", tone: "ok" },
  paused: { label: "Pausada", tone: "warn" },
  error: { label: "Error", tone: "danger" },
  offline: { label: "Sin conexión", tone: "neutral" },
};

export const JOB_STATUS: Record<JobStatus, { label: string; tone: Tone }> = {
  running: { label: "En curso", tone: "accent" },
  completed: { label: "Completado", tone: "ok" },
  failed: { label: "Fallido", tone: "danger" },
  cancelled: { label: "Cancelado", tone: "neutral" },
};
