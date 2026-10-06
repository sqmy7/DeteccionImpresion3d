import { api } from "./apiClient";
import type { JobSummary, PrintJob, TimelineEntry } from "../types/api";

export function listPrintJobsForPrinter(token: string, printerId: number): Promise<PrintJob[]> {
  return api.get<PrintJob[]>(`/api/v1/printers/${printerId}/print-jobs`, token);
}

export function getPrintJob(token: string, jobId: number): Promise<PrintJob> {
  return api.get<PrintJob>(`/api/v1/print-jobs/${jobId}`, token);
}

export function getJobTimeline(token: string, jobId: number): Promise<TimelineEntry[]> {
  return api.get<TimelineEntry[]>(`/api/v1/print-jobs/${jobId}/timeline`, token);
}

export function getJobSummary(token: string, jobId: number): Promise<JobSummary> {
  return api.get<JobSummary>(`/api/v1/print-jobs/${jobId}/summary`, token);
}

export function abortAutoPause(token: string, jobId: number): Promise<void> {
  return api.post<void>(`/api/v1/print-jobs/${jobId}/auto-pause/abort`, undefined, token);
}
