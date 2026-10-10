import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useAuth } from "../hooks/useAuth";
import { useWsEvent } from "../hooks/useWebSocket";
import { pushReading } from "../lib/telemetryStore";
import { listPrinters } from "../services/printers";
import type { Printer } from "../types/api";
import type { PrinterStatusEvent, TelemetrySampleEvent } from "../types/ws";

interface PrintersContextValue {
  printers: Printer[];
  loading: boolean;
  error: string | null;
  reload: () => void;
}

const PrintersContext = createContext<PrintersContextValue | undefined>(undefined);

/** The printer list every screen shares (menu, overview, printer pages), kept in step with
 * printer.status, plus the feed of live readings into the telemetry store. */
export function PrintersProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  const [printers, setPrinters] = useState<Printer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    listPrinters(token)
      .then((result) => {
        if (cancelled) return;
        setPrinters(result);
        setError(null);
      })
      .catch(() => !cancelled && setError("No se pudo cargar la lista de impresoras."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [token, version]);

  useWsEvent<PrinterStatusEvent>("printer.status", (envelope) => {
    const { printer_id, status } = envelope.data;
    setPrinters((current) => current.map((printer) => (printer.id === printer_id ? { ...printer, last_known_status: status } : printer)));
  });

  useWsEvent<TelemetrySampleEvent>("telemetry.sample", (envelope) => pushReading(envelope.data));

  const reload = useCallback(() => setVersion((value) => value + 1), []);
  const value = useMemo(() => ({ printers, loading, error, reload }), [printers, loading, error, reload]);
  return <PrintersContext.Provider value={value}>{children}</PrintersContext.Provider>;
}

export function usePrinters(): PrintersContextValue {
  const context = useContext(PrintersContext);
  if (!context) throw new Error("usePrinters must be used within a PrintersProvider");
  return context;
}
