import { api } from "./apiClient";
import type { ChainVerification, EventOrigin, JobTelemetry, Layer, PrinterEvent, TelemetryReading } from "../types/api";

export function getJobTelemetry(token: string, jobId: number, maxPoints = 1500): Promise<JobTelemetry> {
  return api.get<JobTelemetry>(`/api/v1/print-jobs/${jobId}/telemetry?max_points=${maxPoints}`, token);
}

export function getLatestReading(token: string, printerId: number): Promise<TelemetryReading> {
  return api.get<TelemetryReading>(`/api/v1/printers/${printerId}/telemetry/latest`, token);
}

export function listJobLayers(token: string, jobId: number): Promise<Layer[]> {
  return api.get<Layer[]>(`/api/v1/print-jobs/${jobId}/layers`, token);
}

export interface EventFilters {
  jobId?: number;
  beforeId?: number;
  origins?: EventOrigin[];
  eventTypes?: string[];
  limit?: number;
}

export function listPrinterEvents(token: string, printerId: number, filters: EventFilters = {}): Promise<PrinterEvent[]> {
  const params = new URLSearchParams();
  if (filters.jobId !== undefined) params.set("job_id", String(filters.jobId));
  if (filters.beforeId !== undefined) params.set("before_id", String(filters.beforeId));
  if (filters.origins?.length) params.set("origin", filters.origins.join(","));
  if (filters.eventTypes?.length) params.set("event_type", filters.eventTypes.join(","));
  params.set("limit", String(filters.limit ?? 200));
  return api.get<PrinterEvent[]>(`/api/v1/printers/${printerId}/events?${params.toString()}`, token);
}

export function listJobEvents(token: string, jobId: number): Promise<PrinterEvent[]> {
  return api.get<PrinterEvent[]>(`/api/v1/print-jobs/${jobId}/events`, token);
}

export function verifyPrinterEvents(token: string, printerId: number): Promise<ChainVerification> {
  return api.get<ChainVerification>(`/api/v1/printers/${printerId}/events/verify`, token);
}
