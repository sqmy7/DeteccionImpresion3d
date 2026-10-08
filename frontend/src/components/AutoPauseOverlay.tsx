import { AlertTriangle, PauseCircle, XCircle } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Button } from "./ui";
import { useAuth } from "../hooks/useAuth";
import { useWsEvent } from "../hooks/useWebSocket";
import { ApiError } from "../services/apiClient";
import { abortAutoPause } from "../services/printJobs";
import { listPrinters, resumePrinter } from "../services/printers";
import type {
  AutoPauseAbortedEvent,
  AutoPauseExecutedEvent,
  AutoPauseFailedEvent,
  AutoPausePendingEvent,
  AutoPauseWouldPauseEvent,
} from "../types/ws";

type PendingState = { phase: "pending"; printerId: number; consecutiveLayers: number; executesAt: string };
type ExecutedState = { phase: "executed"; printerId: number };
type FailedState = { phase: "failed"; printerId: number; reason: string };
type WouldPauseState = { phase: "would_pause"; printerId: number; consecutiveLayers: number; layer: number | null; confidence: number | null };
type AutoPauseState = PendingState | ExecutedState | FailedState | WouldPauseState;

/** Mounted once at the app root (see App.tsx), not inside a job page - an auto-pause is
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

  // Warn mode (AUTO_PAUSE_MODE=warn): the pause would have fired, and nothing was sent to the printer.
  useWsEvent<AutoPauseWouldPauseEvent>("auto_pause.would_pause", (envelope) => {
    const { job_id, printer_id, consecutive_layers, layer, confidence } = envelope.data;
    setByJob((prev) => ({
      ...prev,
      [job_id]: { phase: "would_pause", printerId: printer_id, consecutiveLayers: consecutive_layers, layer, confidence },
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
  const [error, setError] = useState<string | null>(null);

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
      <Banner tone="danger" icon={<AlertTriangle size={20} />}>
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-fg">
            Spaghetti detectado {state.consecutiveLayers} capas seguidas en {printerName}
          </p>
          <p className="text-sm text-muted">
            Se va a pausar la impresión automáticamente en{" "}
            {/* Not re-announced by screen readers every second. */}
            <span aria-live="off" className="font-mono text-lg font-bold tabular text-danger-fg">
              {remainingSeconds}s
            </span>{" "}
            si no se aborta.
          </p>
        </div>
        <Button variant="danger" onClick={handleAbort} disabled={busy}>
          Abortar pausa
        </Button>
      </Banner>
    );
  }

  if (state.phase === "would_pause") {
    return (
      <Banner tone="warn" icon={<AlertTriangle size={20} />}>
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-fg">
            Spaghetti detectado {state.consecutiveLayers} capas seguidas en {printerName}
            {state.layer != null ? ` (capa ${state.layer}` : ""}
            {state.layer != null && state.confidence != null ? `, confianza ${Math.round(state.confidence * 100)} %` : ""}
            {state.layer != null ? ")" : ""}
          </p>
          <p className="text-sm text-muted">Modo aviso: habría pausado la impresión, pero no se envió nada a la impresora.</p>
        </div>
        <Button variant="ghost" onClick={onDismiss}>
          Cerrar
        </Button>
      </Banner>
    );
  }

  if (state.phase === "executed") {
    const handleResume = async () => {
      if (!token || busy) return;
      setBusy(true);
      setError(null);
      try {
        await resumePrinter(token, state.printerId);
        onDismiss();
      } catch (reason) {
        // Left visible on failure so the user can see the resume didn't take, and why (the backend
        // refuses a resume when the printer isn't paused or one was just sent).
        setError(reason instanceof ApiError ? reason.message : "No se pudo reanudar.");
      } finally {
        setBusy(false);
      }
    };

    return (
      <Banner tone="warn" icon={<PauseCircle size={20} />}>
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-fg">{printerName} pausada automáticamente</p>
          <p className="text-sm text-muted">Motivo: spaghetti detectado en varias capas seguidas.</p>
          {error && <p className="mt-1 text-sm text-danger-fg">{error}</p>}
        </div>
        <div className="flex shrink-0 gap-2">
          <Button variant="warn" onClick={handleResume} disabled={busy}>
            Reanudar impresión
          </Button>
          <Button variant="ghost" onClick={onDismiss}>
            Cerrar
          </Button>
        </div>
      </Banner>
    );
  }

  return (
    <Banner tone="danger" icon={<XCircle size={20} />}>
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-fg">No se pudo pausar {printerName} automáticamente</p>
        <p className="text-sm text-muted">{state.reason}</p>
      </div>
      <Button variant="ghost" onClick={onDismiss}>
        Cerrar
      </Button>
    </Banner>
  );
}

const BANNER_TONES = {
  danger: "border-danger/70 text-danger-fg",
  warn: "border-warn/70 text-warn-fg",
};

function Banner({ tone, icon, children }: { tone: keyof typeof BANNER_TONES; icon: ReactNode; children: ReactNode }) {
  return (
    <div
      role="alert"
      className={`mx-auto flex w-full max-w-2xl flex-col gap-3 rounded-xl border-2 bg-surface-2/95 p-4 shadow-2xl backdrop-blur sm:flex-row sm:items-center ${BANNER_TONES[tone]}`}
    >
      <span className="hidden shrink-0 sm:block">{icon}</span>
      {children}
    </div>
  );
}
