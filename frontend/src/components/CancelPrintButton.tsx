import { OctagonX } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { CANCEL_WORD, isCancelConfirmed } from "../lib/cancelConfirm";
import { ApiError } from "../services/apiClient";
import { cancelPrinter } from "../services/printers";
import { Button } from "./ui";

/** Cancel the print in progress. It cannot be undone, so it asks twice: a browser confirmation first, then a
 * dialog where CANCELAR has to be typed. The server checks the same word and, besides, that the printer itself
 * says it is printing or paused (app/integrations/moonraker/print_guard.py). Administrators only. */
export function CancelPrintButton({
  printerId,
  size = "sm",
  onCancelled,
}: {
  printerId: number;
  size?: "sm" | "md";
  onCancelled?: () => void;
}) {
  const { token, user } = useAuth();
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (user?.role !== "admin") return null;

  const close = () => {
    setOpen(false);
    setTyped("");
    setError(null);
  };

  const first = () => {
    // First confirmation. The second one is the typed word.
    if (window.confirm("¿Cancelar la impresión? Esto manda la orden real a la impresora y NO se puede deshacer.")) {
      setDone(false);
      setOpen(true);
    }
  };

  const send = async () => {
    if (!token || busy || !isCancelConfirmed(typed)) return;
    setBusy(true);
    setError(null);
    try {
      await cancelPrinter(token, printerId, CANCEL_WORD);
      setDone(true);
      close();
      onCancelled?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo cancelar.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Button size={size} variant="danger" icon={<OctagonX size={14} />} onClick={first} disabled={done}>
        {done ? "Cancelación enviada" : "Cancelar impresión"}
      </Button>
      {open && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-canvas/80 p-4 backdrop-blur-sm" role="presentation">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="cancel-title"
            className="w-full max-w-md rounded-xl border-2 border-danger/70 bg-surface p-5 shadow-2xl"
          >
            <h2 id="cancel-title" className="text-base font-semibold text-fg">
              Confirma la cancelación
            </h2>
            <p className="mt-2 text-sm text-muted">
              La impresión se cancela y la pieza se pierde: no se puede reanudar. Para confirmar, escribe{" "}
              <strong className="font-mono text-danger-fg">{CANCEL_WORD}</strong>.
            </p>
            <input
              ref={input}
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void send();
              }}
              aria-label={`Escribe ${CANCEL_WORD} para confirmar`}
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              placeholder={CANCEL_WORD}
              className="mt-3 h-10 w-full rounded-md border border-line bg-surface-2 px-3 font-mono text-sm text-fg"
            />
            {error && (
              <p role="alert" className="mt-2 text-sm text-danger-fg">
                {error}
              </p>
            )}
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="ghost" onClick={close} disabled={busy}>
                Volver
              </Button>
              <Button variant="danger" onClick={send} disabled={busy || !isCancelConfirmed(typed)}>
                {busy ? "Enviando…" : "Cancelar la impresión"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
