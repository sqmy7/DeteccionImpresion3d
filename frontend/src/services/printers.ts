import { api } from "./apiClient";
import type { Printer } from "../types/api";

export function listPrinters(token: string): Promise<Printer[]> {
  return api.get<Printer[]>("/api/v1/printers", token);
}

export function getPrinter(token: string, printerId: number): Promise<Printer> {
  return api.get<Printer>(`/api/v1/printers/${printerId}`, token);
}

export function pausePrinter(token: string, printerId: number): Promise<void> {
  return api.post<void>(`/api/v1/printers/${printerId}/pause`, undefined, token);
}

export function resumePrinter(token: string, printerId: number): Promise<void> {
  return api.post<void>(`/api/v1/printers/${printerId}/resume`, undefined, token);
}
