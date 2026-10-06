import { useCallback, useEffect, useState } from "react";
import { useAuth } from "./useAuth";
import { useWsEvent } from "./useWebSocket";
import { listAlerts } from "../services/alerts";
import type { DetectionAlertEvent } from "../types/ws";

/** Count of status="new" alerts, kept live via detection.alert - fired both when a new
 * alert is raised and when one transitions away from "new", so refetching on every
 * occurrence keeps this correct without manually tracking increments/decrements. */
export function useActiveAlertsCount(): number {
  const { token } = useAuth();
  const [count, setCount] = useState(0);

  const refetch = useCallback(() => {
    if (!token) return;
    listAlerts(token, "new")
      .then((alerts) => setCount(alerts.length))
      .catch(() => {});
  }, [token]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  useWsEvent<DetectionAlertEvent>("detection.alert", refetch);

  return count;
}
