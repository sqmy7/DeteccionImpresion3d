import { useSyncExternalStore } from "react";
import type { TelemetryReading } from "../types/api";

// Live readings arrive once per second per printer (telemetry.sample). One store keeps the latest
// reading and the last few minutes of them, so every screen reads the same series instead of
// each one subscribing and buffering on its own.
const KEEP_SECONDS = 15 * 60;

interface PrinterSeries {
  latest: TelemetryReading | null;
  recent: TelemetryReading[];
}

const series = new Map<number, PrinterSeries>();
const listeners = new Set<() => void>();
const EMPTY: PrinterSeries = { latest: null, recent: [] };

export function pushReading(reading: TelemetryReading): void {
  const current = series.get(reading.printer_id) ?? EMPTY;
  const cutoff = new Date(reading.ts).getTime() - KEEP_SECONDS * 1000;
  const recent = [...current.recent, reading].filter((item) => new Date(item.ts).getTime() >= cutoff);
  series.set(reading.printer_id, { latest: reading, recent });
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useLiveTelemetry(printerId: number | null): PrinterSeries {
  return useSyncExternalStore(subscribe, () => (printerId === null ? EMPTY : series.get(printerId) ?? EMPTY));
}

/** Seconds since the latest reading of a printer, or null if none arrived in this session. */
export function readingAge(reading: TelemetryReading | null): number | null {
  return reading ? (Date.now() - new Date(reading.ts).getTime()) / 1000 : null;
}
