// Every timestamp from the API is UTC; the people using PrintWatch are in Colombia.
export const TIME_ZONE = "America/Bogota";
const LOCALE = "es-CO";

const dateTimeFormat = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TIME_ZONE,
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});
const timeFormat = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});
const shortTimeFormat = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const dateFormat = new Intl.DateTimeFormat(LOCALE, { timeZone: TIME_ZONE, day: "2-digit", month: "short", year: "numeric" });

function toDate(value: string | number | Date): Date {
  return value instanceof Date ? value : new Date(value);
}

export function formatDateTime(value: string | number | Date | null | undefined): string {
  return value == null ? "—" : dateTimeFormat.format(toDate(value));
}

export function formatTime(value: string | number | Date | null | undefined): string {
  return value == null ? "—" : timeFormat.format(toDate(value));
}

export function formatShortTime(value: string | number | Date | null | undefined): string {
  return value == null ? "—" : shortTimeFormat.format(toDate(value));
}

export function formatDate(value: string | number | Date | null | undefined): string {
  return value == null ? "—" : dateFormat.format(toDate(value));
}

/** "1 h 05 min", "4 min 12 s", "38 s". */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  if (hours > 0) return `${hours} h ${String(minutes).padStart(2, "0")} min`;
  if (minutes > 0) return `${minutes} min ${String(rest).padStart(2, "0")} s`;
  return `${rest} s`;
}

export function secondsBetween(start: string | null | undefined, end?: string | null): number | null {
  if (!start) return null;
  const endTime = end ? new Date(end).getTime() : Date.now();
  return (endTime - new Date(start).getTime()) / 1000;
}

export function formatNumber(value: number | null | undefined, digits = 1, unit = ""): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const text = value.toLocaleString(LOCALE, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return unit ? `${text} ${unit}` : text;
}

export function formatPercent(fraction: number | null | undefined, digits = 0): string {
  if (fraction == null || !Number.isFinite(fraction)) return "—";
  return `${(fraction * 100).toLocaleString(LOCALE, { maximumFractionDigits: digits, minimumFractionDigits: digits })} %`;
}

/** "1 trabajo", "3 trabajos"; pass the plural when it isn't just an added "s". */
export function countOf(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

export function relativeAge(seconds: number): string {
  if (seconds < 5) return "ahora";
  if (seconds < 60) return `hace ${Math.round(seconds)} s`;
  if (seconds < 3600) return `hace ${Math.round(seconds / 60)} min`;
  if (seconds < 86400) return `hace ${Math.round(seconds / 3600)} h`;
  return `hace ${Math.round(seconds / 86400)} días`;
}
