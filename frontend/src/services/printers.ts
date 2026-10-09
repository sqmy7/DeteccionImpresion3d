import { api } from "./apiClient";
import type { Printer } from "../types/api";

export function listPrinters(token: string): Promise<Printer[]> {
  return api.get<Printer[]>("/api/v1/printers", token);
}

export function getPrinter(token: string, printerId: number): Promise<Printer> {
  return api.get<Printer>(`/api/v1/printers/${printerId}`, token);
}

/** What the backend answers to pause, resume and cancel: the order is on its way ("accepted"). The printer carries it out
 * on its own time (a resume takes 45 to 65 s), so the confirmation is its state changing, not this answer
 * (see hooks/usePrintAction.ts). */
export interface ActionAccepted {
  action: string;
  accepted: boolean;
  pending: boolean;
  sent_at: string;
}

export function pausePrinter(token: string, printerId: number): Promise<ActionAccepted> {
  return api.post<ActionAccepted>(`/api/v1/printers/${printerId}/pause`, undefined, token);
}

export function resumePrinter(token: string, printerId: number): Promise<ActionAccepted> {
  return api.post<ActionAccepted>(`/api/v1/printers/${printerId}/resume`, undefined, token);
}

/** Cancels the print in progress. The server also demands the typed word and checks the printer's own state. */
export function cancelPrinter(token: string, printerId: number, confirmation: string): Promise<ActionAccepted> {
  return api.post<ActionAccepted>(`/api/v1/printers/${printerId}/cancel`, { confirmation }, token);
}
