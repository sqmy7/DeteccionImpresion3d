import { api, downloadFile } from "./apiClient";
import type { CostSettings, CostSettingsRead, JobCost, JobFusion, PrinterHealth } from "../types/api";

export function getJobCost(token: string, jobId: number): Promise<JobCost> {
  return api.get<JobCost>(`/api/v1/print-jobs/${jobId}/cost`, token);
}

export function saveCostSettings(token: string, settings: CostSettings): Promise<CostSettingsRead> {
  return api.put<CostSettingsRead>("/api/v1/settings/costs", settings, token);
}

export function downloadJobReport(token: string, jobId: number): Promise<void> {
  return downloadFile(`/api/v1/print-jobs/${jobId}/report.pdf`, token, `reporte_trabajo_${jobId}.pdf`);
}

export function getJobFusion(token: string, jobId: number): Promise<JobFusion> {
  return api.get<JobFusion>(`/api/v1/print-jobs/${jobId}/fusion`, token);
}

export function getPrinterHealth(token: string, printerId: number): Promise<PrinterHealth> {
  return api.get<PrinterHealth>(`/api/v1/printers/${printerId}/health`, token);
}
