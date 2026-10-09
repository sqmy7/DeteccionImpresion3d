import type { PrinterStatus } from "../types/api";

export type PrintActionKind = "pause" | "resume" | "cancel";

/** An order the backend accepted. The printer answers it by changing state, which can take a while: on the Creality Hi
 * a pause shows within a second but the request only ends when the head has parked (~9 s), and a resume takes 45 to
 * 65 s (measured 2026-10-09). So the web does not wait for the request: it follows the printer's state. */
export interface PendingPrintAction {
  kind: PrintActionKind;
  /** The printer's state when the button was pressed: the action is done when it is no longer that. */
  from: PrinterStatus | undefined;
  startedAt: number;
}

export type ActionPhase = "waiting" | "done" | "timeout";

/** How long to wait for the state to change before saying so (the longest resume seen was 65 s). */
export const CONFIRM_TIMEOUT_MS = 120_000;

export function actionPhase(pending: PendingPrintAction, status: PrinterStatus | undefined, now: number): ActionPhase {
  if (status !== undefined && pending.from !== undefined && status !== pending.from) return "done";
  if (now - pending.startedAt >= CONFIRM_TIMEOUT_MS) return "timeout";
  return "waiting";
}

const PROGRESS: Record<PrintActionKind, string> = { pause: "Pausando…", resume: "Reanudando…", cancel: "Cancelando…" };

export function progressLabel(kind: PrintActionKind, seconds: number): string {
  return `${PROGRESS[kind]} ${Math.max(0, Math.floor(seconds))} s`;
}

const VERB: Record<PrintActionKind, string> = { pause: "pausar", resume: "reanudar", cancel: "cancelar" };

export function timeoutNote(kind: PrintActionKind): string {
  return `La orden de ${VERB[kind]} se envió, pero la impresora no cambió de estado en ${CONFIRM_TIMEOUT_MS / 60_000} minutos. Revisa la impresora.`;
}
