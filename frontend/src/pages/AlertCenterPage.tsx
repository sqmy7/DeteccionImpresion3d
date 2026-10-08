import { BellOff } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AlertRow } from "../components/AlertRow";
import { PageHeader } from "../components/layout/PageHeader";
import { Card, EmptyState, Segmented, Skeleton } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { useWsEvent } from "../hooks/useWebSocket";
import { listAlerts, transitionAlert } from "../services/alerts";
import type { AlertListItem, AlertStatus } from "../types/api";
import type { DetectionAlertEvent } from "../types/ws";

type Filter = AlertStatus | "all";

export function AlertCenterPage() {
  const { token } = useAuth();
  const [alerts, setAlerts] = useState<AlertListItem[]>([]);
  const [filter, setFilter] = useState<Filter>("new");
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
    } finally {
      // The backend validates transitions (409 on an invalid one); a stale click just refetches
      // the alert's real state.
      refetch();
    }
  };

  return (
    <>
      <PageHeader
        title="Alertas"
        subtitle="Generadas por reglas sobre las detecciones (por ahora, atasco por sub-extrusión en capas seguidas)"
      />
      <Card
        actions={
          <Segmented
            label="Estado"
            value={filter}
            onChange={setFilter}
            options={[
              { value: "new", label: "Sin revisar" },
              { value: "acknowledged", label: "Reconocidas" },
              { value: "dismissed", label: "Descartadas" },
              { value: "false_positive", label: "Falsos positivos" },
              { value: "all", label: "Todas" },
            ]}
          />
        }
        title="Listado"
      >
        {isLoading ? (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-14 w-full" />
            ))}
          </div>
        ) : alerts.length === 0 ? (
          <EmptyState icon={<BellOff size={28} />} title="Sin alertas para este filtro" />
        ) : (
          <div className="flex flex-col gap-2">
            {alerts.map((alert) => (
              <AlertRow key={alert.id} alert={alert} onTransition={handleTransition} />
            ))}
          </div>
        )}
      </Card>
    </>
  );
}
