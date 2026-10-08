import { api } from "./apiClient";
import type { JobFusion, PrinterHealth } from "../types/api";

export function getJobFusion(token: string, jobId: number): Promise<JobFusion> {
  return api.get<JobFusion>(`/api/v1/print-jobs/${jobId}/fusion`, token);
}

export function getPrinterHealth(token: string, printerId: number): Promise<PrinterHealth> {
  return api.get<PrinterHealth>(`/api/v1/printers/${printerId}/health`, token);
}
