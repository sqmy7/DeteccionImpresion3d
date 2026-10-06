import { api } from "./apiClient";
import type { Detection, LayerCapture } from "../types/api";

export function getLayerCapture(token: string, captureId: number): Promise<LayerCapture> {
  return api.get<LayerCapture>(`/api/v1/layer-captures/${captureId}`, token);
}

export function listDetectionsForCapture(token: string, captureId: number): Promise<Detection[]> {
  return api.get<Detection[]>(`/api/v1/layer-captures/${captureId}/detections`, token);
}
