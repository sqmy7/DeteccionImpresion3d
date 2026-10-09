import { Pause, Play } from "lucide-react";
import { useAuth } from "../hooks/useAuth";
import { usePrintAction } from "../hooks/usePrintAction";
import { progressLabel } from "../lib/printAction";
import { pausePrinter, resumePrinter } from "../services/printers";
import type { PrinterStatus } from "../types/api";
import { CancelPrintButton } from "./CancelPrintButton";
import { Button } from "./ui";

/** Manual pause/resume (and cancel, with its double confirmation), independent of the spaghetti auto-pause flow. No button in the "error"
 * state: Klipper can report "error" after a fault like a move out of range, and blindly resuming
 * in that state is how that got worse last time - check the printer in person and clear the fault
 * there first. Each click asks for confirmation, since it sends a real command to the printer. */
export function PrintControls({ printerId, status }: { printerId: number; status: PrinterStatus }) {
  const { user } = useAuth();
  const { pending, seconds, sending, error, notice, start } = usePrintAction(printerId);
  const busy = sending || pending !== null;

  if ((status !== "printing" && status !== "paused") || user?.role !== "admin") return null;

  const isPrinting = status === "printing";
  const confirmMessage = isPrinting
    ? "¿Pausar la impresión ahora? Esto manda la orden real a la impresora."
    : "¿Reanudar la impresión ahora? Verifica primero que la pieza y el cabezal estén bien.";

  // The backend answers "accepted" at once; the hook keeps the button on "Reanudando…" until the printer's state changes.
  const handleClick = async () => {
    if (busy || !window.confirm(confirmMessage)) return;
    await start(isPrinting ? "pause" : "resume", (token) => (isPrinting ? pausePrinter(token, printerId) : resumePrinter(token, printerId)));
  };

  return (
    <div className="flex flex-wrap items-start gap-2">
      <div className="flex flex-col items-start gap-1.5">
        <Button
          size="sm"
          variant={isPrinting ? "warn" : "ok"}
          icon={isPrinting ? <Pause size={14} /> : <Play size={14} />}
          onClick={handleClick}
          disabled={busy}
        >
          {pending ? progressLabel(pending.kind, seconds) : sending ? "Enviando…" : isPrinting ? "Pausar impresión" : "Reanudar impresión"}
        </Button>
        {error && <span className="max-w-xs text-xs text-danger-fg">{error}</span>}
        {notice && <span className="max-w-xs text-xs text-muted">{notice}</span>}
      </div>
      <CancelPrintButton printerId={printerId} />
    </div>
  );
}
