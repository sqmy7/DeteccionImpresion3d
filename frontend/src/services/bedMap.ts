import { api, ApiError, API_BASE_URL } from "./apiClient";
import type { BedGeometry, BedHeatmap, CalibrationCreate, CameraCalibration, JobBedMap } from "../types/api";

export function getJobBedMap(token: string, jobId: number): Promise<JobBedMap> {
  return api.get<JobBedMap>(`/api/v1/print-jobs/${jobId}/bed-map`, token);
}

export function getBedHeatmap(token: string, printerId: number, cellMm = 20, classes?: string[]): Promise<BedHeatmap> {
  const params = new URLSearchParams({ cell_mm: String(cellMm) });
  if (classes?.length) params.set("classes", classes.join(","));
  return api.get<BedHeatmap>(`/api/v1/printers/${printerId}/bed-heatmap?${params.toString()}`, token);
}

export function getPrinterGeometry(token: string, printerId: number): Promise<BedGeometry> {
  return api.get<BedGeometry>(`/api/v1/printers/${printerId}/geometry`, token);
}

export function getLatestCalibration(token: string, cameraId: number): Promise<CameraCalibration> {
  return api.get<CameraCalibration>(`/api/v1/cameras/${cameraId}/calibration`, token);
}

export function listCalibrations(token: string, cameraId: number): Promise<CameraCalibration[]> {
  return api.get<CameraCalibration[]>(`/api/v1/cameras/${cameraId}/calibrations`, token);
}

export function createCalibration(token: string, cameraId: number, body: CalibrationCreate): Promise<CameraCalibration> {
  return api.post<CameraCalibration>(`/api/v1/cameras/${cameraId}/calibration`, body, token);
}

export interface Snapshot {
  url: string; // object URL, revoke when done
  ageSeconds: number | null; // null: the capture process doesn't record frame times yet
}

/** The camera's latest frame as a still, with how old it is (a frame can outlive the capture
 * process that wrote it). */
export async function fetchSnapshot(token: string, cameraId: number): Promise<Snapshot> {
  const response = await fetch(`${API_BASE_URL}/api/v1/cameras/${cameraId}/snapshot?token=${encodeURIComponent(token)}`);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail ?? detail;
    } catch {
      // not JSON
    }
    throw new ApiError(response.status, detail);
  }
  const age = response.headers.get("X-Frame-Age-Seconds");
  return { url: URL.createObjectURL(await response.blob()), ageSeconds: age === null ? null : Number(age) };
}
