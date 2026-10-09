import { AlertTriangle, PauseCircle, XCircle } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Button } from "./ui";
import { useAuth } from "../hooks/useAuth";
import { usePrintAction } from "../hooks/usePrintAction";
import { progressLabel } from "../lib/printAction";
import { useWsEvent } from "../hooks/useWebSocket";
import { abortAutoPause } from "../services/printJobs";
import { listPrinters, resumePrinter } from "../services/printers";
import type {
  AutoPauseAbortedEvent,
  AutoPauseConfirmedEvent,
  AutoPauseExecutedEvent,
  AutoPauseFailedEvent,
  AutoPauseNotConfirmedEvent,
  AutoPausePendingEvent,
  AutoPauseWouldPauseEvent,
} from "../types/ws";

type PendingState = { phase: "pending"; printerId: number; consecutiveLayers: number; executesAt: string; incidentId: number | null };
// "sent": the order went out and Klipper has not said yet whether it paused; "executed": Klipper confirmed it.
type SentState = { phase: "sent"; printerId: number; incidentId: number | null };
type ExecutedState = { phase: "executed"; printerId: number; incidentId: number | null };
type NotConfirmedState = { phase: "not_confirmed"; printerId: number; incidentId: number | null; reason: string };
type FailedState = { phase: "failed"; printerId: number; reason: string; incidentId: number | null };
type WouldPauseState = {
  phase: "would_pause";
  printerId: number;
  consecutiveLayers: number;
  layer: number | null;
  confidence: number | null;
  incidentId: number | null;
};
type AutoPauseState = PendingState | SentState | ExecutedState | NotConfirmedState | FailedState | WouldPauseState;

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
    const { job_id, printer_id, consecutive_layers, executes_at, incident_id } = envelope.data;
    setByJob((prev) => ({
      ...prev,
      [job_id]: { phase: "pending", printerId: printer_id, consecutiveLayers: consecutive_layers, executesAt: executes_at, incidentId: incident_id ?? null },
    }));
  });

  // Warn mode (AUTO_PAUSE_MODE=warn): the pause would have fired, and nothing was sent to the printer.
  useWsEvent<AutoPauseWouldPauseEvent>("auto_pause.would_pause", (envelope) => {
    const { job_id, printer_id, consecutive_layers, layer, confidence, incident_id } = envelope.data;
    setByJob((prev) => ({
      ...prev,
      [job_id]: { phase: "would_pause", printerId: printer_id, consecutiveLayers: consecutive_layers, layer, confidence, incidentId: incident_id ?? null },
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
    const { job_id, printer_id, incident_id } = envelope.data;
    setByJob((prev) => ({ ...prev, [job_id]: { phase: "sent", printerId: printer_id, incidentId: incident_id ?? null } }));
  });

  useWsEvent<AutoPauseConfirmedEvent>("auto_pause.confirmed", (envelope) => {
    const { job_id, printer_id, incident_id } = envelope.data;
    setByJob((prev) => ({ ...prev, [job_id]: { phase: "executed", printerId: printer_id, incidentId: incident_id ?? null } }));
  });

  useWsEvent<AutoPauseNotConfirmedEvent>("auto_pause.not_confirmed", (envelope) => {
    const { job_id, printer_id, incident_id, reason } = envelope.data;
    setByJob((prev) => ({ ...prev, [job_id]: { phase: "not_confirmed", printerId: printer_id, incidentId: incident_id ?? null, reason } }));
  });

  useWsEvent<AutoPauseFailedEvent>("auto_pause.failed", (envelope) => {
    const { job_id, printer_id, reason, incident_id } = envelope.data;
    setByJob((prev) => ({ ...prev, [job_id]: { phase: "failed", printerId: printer_id, reason, incidentId: incident_id ?? null } }));
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
  const resumeAction = usePrintAction(state.printerId);
  const resumeSent = useRef(false);

  // Once the resume was accepted the banner stays ("Reanudando…") until the printer's state changes, then it goes away.
  useEffect(() => {
    if (resumeSent.current && !resumeAction.pending && !resumeAction.sending && !resumeAction.notice) onDismiss();
  }, [resumeAction.pending, resumeAction.sending, resumeAction.notice, onDismiss]);

  const incidentLink = state.incidentId ? (
    <Link
      to={`/printers/${state.printerId}/incidents/${state.incidentId}`}
      className="shrink-0 rounded-md border border-line px-3 py-1.5 text-xs font-semibold text-fg hover:bg-surface-3"
    >
      Ver incidente
    </Link>
  ) : null;

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
        {incidentLink}
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
        {incidentLink}
        <Button variant="ghost" onClick={onDismiss}>
          Cerrar
        </Button>
      </Banner>
    );
  }

  if (state.phase === "sent") {
    return (
      <Banner tone="warn" icon={<PauseCircle size={20} />}>
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-fg">Pausa enviada a {printerName}</p>
          <p className="text-sm text-muted">Esperando que la impresora confirme que quedó en pausa (hasta 20 s)…</p>
        </div>
        {incidentLink}
      </Banner>
    );
  }

  if (state.phase === "not_confirmed") {
    return (
      <Banner tone="danger" icon={<XCircle size={20} />}>
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-fg">Pausa NO confirmada en {printerName}</p>
          <p className="text-sm text-muted">
            {state.reason === "send_failed"
              ? "No se pudo enviar la pausa a la impresora."
              : "Se envió la pausa y la impresora no confirmó que quedara en pausa."}{" "}
            Revisa la impresora ahora.
          </p>
        </div>
        {incidentLink}
        <Button variant="ghost" onClick={onDismiss}>
          Cerrar
        </Button>
      </Banner>
    );
  }

  if (state.phase === "executed") {
    const handleResume = async () => {
      // Left visible on failure so the user can see the resume didn't take, and why (the backend
      // refuses a resume when the printer isn't paused or one was just sent).
      if (await resumeAction.start("resume", (accessToken) => resumePrinter(accessToken, state.printerId))) {
        resumeSent.current = true;
      }
    };

    return (
      <Banner tone="warn" icon={<PauseCircle size={20} />}>
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-fg">{printerName} pausada automáticamente</p>
          <p className="text-sm text-muted">Motivo: spaghetti detectado en varias capas seguidas. La impresora confirmó la pausa.</p>
          {resumeAction.error && <p className="mt-1 text-sm text-danger-fg">{resumeAction.error}</p>}
          {resumeAction.notice && <p className="mt-1 text-sm text-muted">{resumeAction.notice}</p>}
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {incidentLink}
          <Button variant="warn" onClick={handleResume} disabled={busy || resumeAction.sending || resumeAction.pending !== null}>
            {resumeAction.pending
              ? progressLabel(resumeAction.pending.kind, resumeAction.seconds)
              : resumeAction.sending
                ? "Enviando…"
                : "Reanudar impresión"}
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
      {incidentLink}
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
