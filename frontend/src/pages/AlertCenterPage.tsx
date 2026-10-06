import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertRow } from "../components/AlertRow";
import { useAuth } from "../hooks/useAuth";
import { useWsEvent } from "../hooks/useWebSocket";
import { listAlerts, transitionAlert } from "../services/alerts";
import type { AlertListItem, AlertStatus } from "../types/api";
import type { DetectionAlertEvent } from "../types/ws";

const STATUS_FILTERS: { label: string; value: AlertStatus | "all" }[] = [
  { label: "Todas", value: "all" },
  { label: "Nuevas", value: "new" },
  { label: "Reconocidas", value: "acknowledged" },
  { label: "Descartadas", value: "dismissed" },
  { label: "Falso positivo", value: "false_positive" },
];

export function AlertCenterPage() {
  const { token } = useAuth();
  const [alerts, setAlerts] = useState<AlertListItem[]>([]);
  const [filter, setFilter] = useState<AlertStatus | "all">("all");
  const [isLoading, setIsLoading] = useState(true);

  const refetch = useCallback(() => {
    if (!token) return;
    listAlerts(token, filter === "all" ? undefined : filter)
      .then(setAlerts)
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, [token, filter]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  useWsEvent<DetectionAlertEvent>("detection.alert", refetch);

  const handleTransition = async (alertId: number, status: AlertStatus) => {
    if (!token) return;
    try {
      await transitionAlert(token, alertId, status);
      refetch();
    } catch {
      // Backend already validates the transition (409 on an invalid one) - a stale
      // button click just gets a no-op refetch showing the alert's real current state.
      refetch();
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white px-4 py-3 sm:px-6">
        <Link to="/" className="text-sm text-slate-500 hover:text-slate-700">
          &larr; Volver al dashboard
        </Link>
        <h1 className="mt-1 text-lg font-bold text-slate-900">Centro de alertas</h1>
      </header>

      <main className="p-4 sm:p-6">
        <div className="mb-4 flex flex-wrap gap-2">
          {STATUS_FILTERS.map((option) => (
            <button
              key={option.value}
              onClick={() => setFilter(option.value)}
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                filter === option.value ? "bg-slate-900 text-white" : "bg-slate-200 text-slate-600 hover:bg-slate-300"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>

        {isLoading && <p className="text-slate-500">Cargando alertas...</p>}
        {!isLoading && alerts.length === 0 && <p className="text-slate-500">No hay alertas para este filtro.</p>}

        <div className="flex flex-col gap-2">
          {alerts.map((alert) => (
            <AlertRow key={alert.id} alert={alert} onTransition={handleTransition} />
          ))}
        </div>
      </main>
    </div>
  );
}
