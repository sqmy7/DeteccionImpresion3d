import { api } from "./apiClient";
import type { Camera } from "../types/api";

export function listCamerasForPrinter(token: string, printerId: number): Promise<Camera[]> {
  return api.get<Camera[]>(`/api/v1/printers/${printerId}/cameras`, token);
}
