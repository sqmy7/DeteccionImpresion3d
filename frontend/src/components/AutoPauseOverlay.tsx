import { useEffect, useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { useWsEvent } from "../hooks/useWebSocket";
import { abortAutoPause } from "../services/printJobs";
import { listPrinters, resumePrinter } from "../services/printers";
import type {
  AutoPauseAbortedEvent,
  AutoPauseExecutedEvent,
  AutoPauseFailedEvent,
  AutoPausePendingEvent,
} from "../types/ws";

type PendingState = { phase: "pending"; printerId: number; consecutiveLayers: number; executesAt: string };
type ExecutedState = { phase: "executed"; printerId: number };
type FailedState = { phase: "failed"; printerId: number; reason: string };
type AutoPauseState = PendingState | ExecutedState | FailedState;

/** Mounted once at the app root (see App.tsx), not inside JobDetailPage - an auto-pause is
 * severe enough that it must interrupt whatever screen the user is on, not just the one for
 * the affected job. Keyed by job_id so more than one printer's pause can be shown at once,
 * though today there is exactly one printer. */
export function AutoPauseOverlay() {
  const { token } = useAuth();
  const [byJob, setByJob] = useState<Record<number, AutoPauseState>>({});
  const [printerNames, setPrinterNames] = useState<Record<number, string>>({});
  const [, setTick] = useState(0);

  useEffect(() => {
    if (!token) return;
    listPrinters(token)
      .then((printers) => setPrinterNames(Object.fromEntries(printers.map((p) => [p.id, p.name]))))
      .catch(() => {});
  }, [token]);

  // Re-render every 250ms so the countdown below is always recomputed from executesAt (the
  // backend's clock) instead of decrementing a local counter that could drift or survive a
  // background tab throttling differently than the real deadline does.
  useEffect(() => {
    const interval = window.setInterval(() => setTick((t) => t + 1), 250);
    return () => window.clearInterval(interval);
  }, []);

  useWsEvent<AutoPausePendingEvent>("auto_pause.pending", (envelope) => {
    const { job_id, printer_id, consecutive_layers, executes_at } = envelope.data;
    setByJob((prev) => ({
      ...prev,
      [job_id]: { phase: "pending", printerId: printer_id, consecutiveLayers: consecutive_layers, executesAt: executes_at },
    }));
  });

  useWsEvent<AutoPauseAbortedEvent>("auto_pause.aborted", (envelope) => {
    setByJob((prev) => {
      const next = { ...prev };
      delete next[envelope.data.job_id];
      return next;
    });
  });

  useWsEvent<AutoPauseExecutedEvent>("auto_pause.executed", (envelope) => {
    const { job_id, printer_id } = envelope.data;
    setByJob((prev) => ({ ...prev, [job_id]: { phase: "executed", printerId: printer_id } }));
  });

  useWsEvent<AutoPauseFailedEvent>("auto_pause.failed", (envelope) => {
    const { job_id, printer_id, reason } = envelope.data;
    setByJob((prev) => ({ ...prev, [job_id]: { phase: "failed", printerId: printer_id, reason } }));
  });

  const entries = Object.entries(byJob);
  if (entries.length === 0) return null;

  return (
    <div className="fixed inset-x-0 top-0 z-50 flex flex-col gap-2 p-3">
      {entries.map(([jobIdStr, state]) => (
        <AutoPauseBanner
          key={jobIdStr}
          jobId={Number(jobIdStr)}
          state={state}
          printerName={printerNames[state.printerId] ?? `Impresora #${state.printerId}`}
          onDismiss={() => setByJob((prev) => { const next = { ...prev }; delete next[Number(jobIdStr)]; return next; })}
        />
      ))}
    </div>
  );
}

function AutoPauseBanner({
  jobId,
  state,
  printerName,
  onDismiss,
}: {
  jobId: number;
  state: AutoPauseState;
  printerName: string;
  onDismiss: () => void;
}) {
  const { token } = useAuth();
  const [busy, setBusy] = useState(false);

  if (state.phase === "pending") {
    const remainingMs = new Date(state.executesAt).getTime() - Date.now();
    const remainingSeconds = Math.max(0, Math.ceil(remainingMs / 1000));

    const handleAbort = async () => {
      if (!token || busy) return;
      setBusy(true);
      try {
        await abortAutoPause(token, jobId);
      } catch {
        // 409 (already executed) or a network blip - the corresponding auto_pause.* event,
        // if any, is the source of truth; nothing to reconcile here by hand.
      } finally {
        setBusy(false);
      }
    };

    return (
      <div className="mx-auto flex w-full max-w-2xl flex-col items-center gap-3 rounded-lg border-2 border-red-500 bg-red-950/95 p-4 shadow-xl sm:flex-row sm:justify-between">
        <div>
          <p className="text-base font-bold text-red-100">
            ⚠ Spaghetti detectado {state.consecutiveLayers} capas seguidas en {printerName}
          </p>
          <p className="text-sm text-red-200">
            Se va a pausar la impresión automáticamente en{" "}
            <span className="font-mono text-lg font-bold">{remainingSeconds}s</span> si no se aborta.
          </p>
        </div>
        <button
          onClick={handleAbort}
          disabled={busy}
          className="shrink-0 rounded-md bg-white px-5 py-2.5 text-sm font-bold text-red-900 hover:bg-red-50 disabled:opacity-60"
        >
          Abortar pausa
        </button>
      </div>
    );
  }

  if (state.phase === "executed") {
    const handleResume = async () => {
      if (!token || busy) return;
      setBusy(true);
      try {
        await resumePrinter(token, state.printerId);
        onDismiss();
      } catch {
        // Left visible on failure so the user can see the resume didn't take and retry.
      } finally {
        setBusy(false);
      }
    };

    return (
      <div className="mx-auto flex w-full max-w-2xl flex-col items-center gap-3 rounded-lg border-2 border-amber-500 bg-amber-950/95 p-4 shadow-xl sm:flex-row sm:justify-between">
        <div>
          <p className="text-base font-bold text-amber-100">⏸ {printerName} pausada automáticamente</p>
          <p className="text-sm text-amber-200">Motivo: spaghetti detectado en varias capas seguidas.</p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            onClick={handleResume}
            disabled={busy}
            className="rounded-md bg-white px-5 py-2.5 text-sm font-bold text-amber-900 hover:bg-amber-50 disabled:opacity-60"
          >
            Reanudar impresión
          </button>
          <button onClick={onDismiss} className="rounded-md px-3 py-2.5 text-sm text-amber-300 hover:text-amber-100">
            Cerrar
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl items-center justify-between gap-3 rounded-lg border-2 border-red-500 bg-red-950/95 p-4 shadow-xl">
      <div>
        <p className="text-base font-bold text-red-100">✗ No se pudo pausar {printerName} automáticamente</p>
        <p className="text-sm text-red-200">{state.reason}</p>
      </div>
      <button onClick={onDismiss} className="shrink-0 rounded-md px-3 py-2.5 text-sm text-red-300 hover:text-red-100">
        Cerrar
      </button>
    </div>
  );
}
