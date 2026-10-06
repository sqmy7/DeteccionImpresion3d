import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PrinterCard } from "../components/PrinterCard";
import { useActiveAlertsCount } from "../hooks/useActiveAlertsCount";
import { useAuth } from "../hooks/useAuth";
import { useWebSocket, useWsEvent } from "../hooks/useWebSocket";
import { listPrinters } from "../services/printers";
import type { Printer } from "../types/api";
import type { PrinterStatusEvent } from "../types/ws";

export function DashboardPage() {
  const { token, user, logout } = useAuth();
  const { connected } = useWebSocket();
  const activeAlertsCount = useActiveAlertsCount();
  const [printers, setPrinters] = useState<Printer[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    listPrinters(token)
      .then((result) => {
        if (!cancelled) setPrinters(result);
      })
      .catch(() => {
        if (!cancelled) setError("No se pudo cargar la lista de impresoras.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  const handlePrinterStatus = useCallback((envelope: { data: PrinterStatusEvent }) => {
    const { printer_id, status } = envelope.data;
    setPrinters((current) =>
      current.map((printer) => (printer.id === printer_id ? { ...printer, last_known_status: status } : printer)),
    );
  }, []);

  useWsEvent<PrinterStatusEvent>("printer.status", handlePrinterStatus);

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 sm:px-6">
        <div>
          <h1 className="text-lg font-bold text-slate-900">PrintWatch</h1>
          <p className="text-xs text-slate-500">{user?.username}</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5 text-xs text-slate-500">
            <span className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-500" : "bg-red-500"}`} />
            {connected ? "En vivo" : "Reconectando..."}
          </span>
          <Link
            to="/alerts"
            className="relative rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100"
          >
            Alertas
            {activeAlertsCount > 0 && (
              <span className="absolute -right-2 -top-2 flex h-5 min-w-5 items-center justify-center rounded-full bg-red-600 px-1 text-xs font-bold text-white">
                {activeAlertsCount}
              </span>
            )}
          </Link>
          <button
            onClick={logout}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100"
          >
            Salir
          </button>
        </div>
      </header>

      <main className="p-4 sm:p-6">
        <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-slate-500">Impresoras</h2>

        {isLoading && <p className="text-slate-500">Cargando impresoras...</p>}
        {error && <p className="text-red-600">{error}</p>}

        {!isLoading && !error && printers.length === 0 && (
          <p className="text-slate-500">No hay impresoras registradas todavía.</p>
        )}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {printers.map((printer) => (
            <PrinterCard key={printer.id} printer={printer} />
          ))}
        </div>
      </main>
    </div>
  );
}
