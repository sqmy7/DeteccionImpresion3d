import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { ApiError } from "../services/apiClient";
import { pausePrinter, resumePrinter } from "../services/printers";
import type { JobSummary, Printer, PrinterStatus, PrintJob } from "../types/api";

const STATUS_DOT: Record<PrinterStatus, string> = {
  idle: "bg-slate-500",
  printing: "bg-emerald-400",
  paused: "bg-amber-400",
  error: "bg-red-400",
  offline: "bg-slate-600",
};

const STATUS_LABEL: Record<PrinterStatus, string> = {
  idle: "Inactiva",
  printing: "Imprimiendo",
  paused: "Pausada",
  error: "Error",
  offline: "Sin conexión",
};

export function JobTopBar({ printer, job, summary }: { printer: Printer; job: PrintJob; summary: JobSummary | null }) {
  const layerProgress =
    summary?.current_layer != null
      ? job.estimated_layers
        ? `Capa ${summary.current_layer} / ${job.estimated_layers}`
        : `Capa ${summary.current_layer}`
      : "Sin capas todavía";

  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 bg-slate-950 px-4 py-3 sm:px-6">
      <div className="flex items-center gap-4">
        <Link to="/" className="text-sm text-slate-500 hover:text-slate-300">
          &larr;
        </Link>
        <div>
          <h1 className="text-lg font-bold text-slate-50">{printer.name}</h1>
          <p className="text-xs text-slate-400">{job.file_name}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <StatChip>
          <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[printer.last_known_status]}`} />
          {STATUS_LABEL[printer.last_known_status]}
        </StatChip>
        <StatChip>{layerProgress}</StatChip>
        {summary?.latest_model_version && <StatChip>{summary.latest_model_version.name}</StatChip>}
        <PauseResumeControl printerId={printer.id} status={printer.last_known_status} />
      </div>
    </header>
  );
}

/** Manual pause/resume, independent of the spaghetti auto-pause flow - for deliberately testing
 * Moonraker's pause/resume against real hardware. No button in the "error" state: Klipper's
 * print_stats can report "error" after something like a move-out-of-range fault, and blindly
 * resuming a print in that state is how that got worse last time - check the printer in person
 * and clear the fault there first. */
function PauseResumeControl({ printerId, status }: { printerId: number; status: PrinterStatus }) {
  const { token } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (status !== "printing" && status !== "paused") return null;

  const isPrinting = status === "printing";
  const label = isPrinting ? "Pausar impresión" : "Reanudar impresión";
  const confirmMessage = isPrinting
    ? "¿Pausar la impresión ahora? Esto manda el comando real a la impresora."
    : "¿Reanudar la impresión ahora? Verificá primero que la pieza y el cabezal estén bien.";

  const handleClick = async () => {
    if (!token || busy) return;
    if (!window.confirm(confirmMessage)) return;

    setBusy(true);
    setError(null);
    try {
      await (isPrinting ? pausePrinter(token, printerId) : resumePrinter(token, printerId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo completar la acción.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={handleClick}
        disabled={busy}
        className={`rounded-md px-3 py-1 text-xs font-semibold disabled:opacity-50 ${
          isPrinting ? "bg-amber-500 text-amber-950 hover:bg-amber-400" : "bg-emerald-500 text-emerald-950 hover:bg-emerald-400"
        }`}
      >
        {busy ? "Enviando..." : label}
      </button>
      {error && <span className="max-w-xs text-xs text-red-400">{error}</span>}
    </div>
  );
}

function StatChip({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border border-slate-800 bg-slate-900 px-2.5 py-1 text-xs font-medium text-slate-300">
      {children}
    </span>
  );
}
