import { useCallback, useEffect, useState } from "react";
import { AlertRow } from "./AlertRow";
import { Card, EmptyState } from "./ui";
import { useAuth } from "../hooks/useAuth";
import { useWsEvent } from "../hooks/useWebSocket";
import { listAlerts, transitionAlert } from "../services/alerts";
import type { AlertListItem, AlertStatus } from "../types/api";
import type { DetectionAlertEvent } from "../types/ws";

/** Same list/transition logic as the alert center, scoped to one job. */
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
    <Card title="Alertas de este trabajo">
      {alerts.length === 0 ? (
        <EmptyState title="Sin alertas" description="Se generan cuando el modelo ve un atasco (sub-extrusión) varias capas seguidas." />
      ) : (
        <div className="flex flex-col gap-2">
          {alerts.map((alert) => (
            <AlertRow key={alert.id} alert={alert} onTransition={handleTransition} />
          ))}
        </div>
      )}
    </Card>
  );
}
