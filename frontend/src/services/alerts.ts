import { api } from "./apiClient";
import type { Alert, AlertListItem, AlertStatus } from "../types/api";

export function listAlerts(token: string, status?: AlertStatus, jobId?: number): Promise<AlertListItem[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (jobId !== undefined) params.set("job_id", String(jobId));
  const query = params.toString() ? `?${params.toString()}` : "";
  return api.get<AlertListItem[]>(`/api/v1/alerts${query}`, token);
}

// Backend exposes this as POST /alerts/{id}/transition, not PATCH /alerts/{id} - the
// contract draft had the latter, but the former was already built and tested with the
// WS broadcast wired to it, so this reuses it instead of adding a duplicate route.
export function transitionAlert(token: string, alertId: number, status: AlertStatus): Promise<Alert> {
  return api.post<Alert>(`/api/v1/alerts/${alertId}/transition`, { status }, token);
}
