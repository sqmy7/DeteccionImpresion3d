import { useCallback, useEffect, useState } from "react";
import { AlertRow } from "./AlertRow";
import { useAuth } from "../hooks/useAuth";
import { useWsEvent } from "../hooks/useWebSocket";
import { listAlerts, transitionAlert } from "../services/alerts";
import type { AlertListItem, AlertStatus } from "../types/api";
import type { DetectionAlertEvent } from "../types/ws";

/** Same list/transition logic as AlertCenterPage, scoped to one job instead of every printer -
 * reuses listAlerts' job_id filter and the shared AlertRow rather than a second implementation. */
export function JobAlertsPanel({ jobId }: { jobId: number }) {
  const { token } = useAuth();
  const [alerts, setAlerts] = useState<AlertListItem[]>([]);

  const refetch = useCallback(() => {
    if (!token) return;
    listAlerts(token, undefined, jobId)
      .then(setAlerts)
      .catch(() => {});
  }, [token, jobId]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  useWsEvent<DetectionAlertEvent>("detection.alert", refetch);

  const handleTransition = async (alertId: number, status: AlertStatus) => {
    if (!token) return;
    try {
      await transitionAlert(token, alertId, status);
    } finally {
      refetch();
    }
  };

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-400">Alertas de este trabajo</h2>
      {alerts.length === 0 ? (
        <p className="text-sm text-slate-500">Sin alertas en este trabajo.</p>
      ) : (
        <div className="flex flex-col gap-2">
          {alerts.map((alert) => (
            <AlertRow key={alert.id} alert={alert} onTransition={handleTransition} />
          ))}
        </div>
      )}
    </div>
  );
}
