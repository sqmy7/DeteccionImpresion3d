import { Pause, Play } from "lucide-react";
import { useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { ApiError } from "../services/apiClient";
import { pausePrinter, resumePrinter } from "../services/printers";
import type { PrinterStatus } from "../types/api";
import { Button } from "./ui";

/** Manual pause/resume, independent of the spaghetti auto-pause flow. No button in the "error"
 * state: Klipper can report "error" after a fault like a move out of range, and blindly resuming
 * in that state is how that got worse last time - check the printer in person and clear the fault
 * there first. Each click asks for confirmation, since it sends a real command to the printer. */
export function PrintControls({ printerId, status }: { printerId: number; status: PrinterStatus }) {
  const { token, user } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if ((status !== "printing" && status !== "paused") || user?.role !== "admin") return null;

  const isPrinting = status === "printing";
  const confirmMessage = isPrinting
    ? "¿Pausar la impresión ahora? Esto manda la orden real a la impresora."
    : "¿Reanudar la impresión ahora? Verifica primero que la pieza y el cabezal estén bien.";

  const handleClick = async () => {
    if (!token || busy || !window.confirm(confirmMessage)) return;
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
    <div className="flex flex-col items-start gap-1.5">
      <Button
        size="sm"
        variant={isPrinting ? "warn" : "ok"}
        icon={isPrinting ? <Pause size={14} /> : <Play size={14} />}
        onClick={handleClick}
        disabled={busy}
      >
        {busy ? "Enviando…" : isPrinting ? "Pausar impresión" : "Reanudar impresión"}
      </Button>
      {error && <span className="max-w-xs text-xs text-danger-fg">{error}</span>}
    </div>
  );
}
