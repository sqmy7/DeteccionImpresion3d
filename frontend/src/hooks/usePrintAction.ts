import { useCallback, useEffect, useRef, useState } from "react";
import { usePrinters } from "../context/PrintersContext";
import { actionPhase, timeoutNote, type PendingPrintAction, type PrintActionKind } from "../lib/printAction";
import { ApiError } from "../services/apiClient";
import { useAuth } from "./useAuth";

/** Sends a pause, resume or cancel and follows it: the backend answers "accepted" at once and the printer takes its time
 * (a resume, up to ~65 s), so this keeps `pending` until the printer's state changes (or 2 minutes pass) instead of
 * showing an error because the request was slow. */
export function usePrintAction(printerId: number) {
  const { token } = useAuth();
  const { printers } = usePrinters();
  const status = printers.find((printer) => printer.id === printerId)?.last_known_status;
  const [pending, setPending] = useState<PendingPrintAction | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const statusRef = useRef(status);
  statusRef.current = status;

  useEffect(() => {
    if (!pending) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [pending]);

  const phase = pending ? actionPhase(pending, status, now) : null;
  useEffect(() => {
    if (!pending || phase === "waiting" || phase === null) return;
    if (phase === "timeout") setNotice(timeoutNote(pending.kind));
    setPending(null);
  }, [phase, pending]);

  /** Sends the order with `call`; true if the backend accepted it. */
  const start = useCallback(
    async (kind: PrintActionKind, call: (accessToken: string) => Promise<unknown>): Promise<boolean> => {
      if (!token || sending || pending) return false;
      const from = statusRef.current; // before the call: a pause shows within a second, before the answer
      setSending(true);
      setError(null);
      setNotice(null);
      try {
        await call(token);
        const startedAt = Date.now();
        setNow(startedAt);
        setPending({ kind, from, startedAt });
        return true;
      } catch (reason) {
        setError(reason instanceof ApiError ? reason.message : "No se pudo completar la acción.");
        return false;
      } finally {
        setSending(false);
      }
    },
    [token, sending, pending],
  );

  const seconds = pending ? (now - pending.startedAt) / 1000 : 0;
  return { pending, seconds, sending, error, notice, start, clearMessages: () => { setError(null); setNotice(null); } };
}
