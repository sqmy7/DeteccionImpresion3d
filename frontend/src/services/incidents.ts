import { api, API_BASE_URL } from "./apiClient";
import type { Incident, IncidentDetail, IncidentLabel } from "../types/api";

export type IncidentFilter = "all" | "unclosed" | "closed";

export function listIncidents(token: string, options: { printerId?: number; state?: IncidentFilter; limit?: number } = {}): Promise<Incident[]> {
  const params = new URLSearchParams({ state: options.state ?? "all", limit: String(options.limit ?? 100) });
  if (options.printerId !== undefined) params.set("printer_id", String(options.printerId));
  return api.get<Incident[]>(`/api/v1/incidents?${params.toString()}`, token);
}

export function getIncident(token: string, incidentId: number): Promise<IncidentDetail> {
  return api.get<IncidentDetail>(`/api/v1/incidents/${incidentId}`, token);
}

export function labelIncident(token: string, incidentId: number, label: IncidentLabel): Promise<Incident> {
  return api.post<Incident>(`/api/v1/incidents/${incidentId}/label`, { label }, token);
}

/** "Ignorar": closes the incident as ignored. Sends nothing to the printer. */
export function dismissIncident(token: string, incidentId: number): Promise<Incident> {
  return api.post<Incident>(`/api/v1/incidents/${incidentId}/dismiss`, undefined, token);
}

/** The photo of a layer as an <img> source (the token goes in the query: an <img> cannot send headers). */
export function incidentImageUrl(token: string, imagePath: string): string {
  return `${API_BASE_URL}${imagePath}?token=${encodeURIComponent(token)}`;
}
