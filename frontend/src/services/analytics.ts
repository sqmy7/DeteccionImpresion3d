import { api } from "./apiClient";
import type { AnalyticsSummary } from "../types/api";

export function getAnalyticsSummary(token: string, printerId: number | null, days: number | null): Promise<AnalyticsSummary> {
  const params = new URLSearchParams();
  if (printerId !== null) params.set("printer_id", String(printerId));
  if (days !== null) params.set("days", String(days));
  const query = params.toString();
  return api.get<AnalyticsSummary>(`/api/v1/analytics/summary${query ? `?${query}` : ""}`, token);
}
