import type { Tone } from "../components/ui";
import type { Incident, IncidentLabel, IncidentOutcome, IncidentReason, IncidentStatus, PrinterStatus } from "../types/api";

export const REASON_LABELS: Record<IncidentReason, string> = {
  would_pause: "Habría pausado (modo aviso)",
  auto_pause: "Pausa automática",
  pause: "La impresora se pausó",
  detection: "Detección sobre el umbral",
};

export const STATUS_INFO: Record<IncidentStatus, { label: string; tone: Tone }> = {
  open: { label: "Abierto", tone: "warn" },
  paused: { label: "Pausado", tone: "warn" },
  unconfirmed: { label: "Pausa no confirmada", tone: "danger" },
  closed: { label: "Cerrado", tone: "neutral" },
};

export const OUTCOME_LABELS: Record<IncidentOutcome, string> = {
  resumed: "Se reanudó",
  cancelled: "Se canceló",
  ignored: "Ignorado",
  error: "Terminó en error",
};

export const LABEL_INFO: Record<IncidentLabel, { label: string; tone: Tone }> = {
  unlabeled: { label: "Sin etiquetar", tone: "neutral" },
  correct: { label: "Acierto", tone: "ok" },
  false_positive: { label: "Falso positivo", tone: "info" },
};

/** The class shown for an incident: a pause with no detection behind it has the class "pausa". */
export function incidentClassLabel(defectClass: string, label: (name: string) => string): string {
  return defectClass === "pausa" ? "Pausa" : label(defectClass);
}

/** An incident that still asks for a decision (everything but a closed one). */
export function needsAttention(incident: Pick<Incident, "status">): boolean {
  return incident.status !== "closed";
}

/** The countdown of an automatic pause can still be aborted: it was announced and the pause was not sent. */
export function isAbortable(incident: Pick<Incident, "status" | "reason" | "pause_sent_at">): boolean {
  return incident.status === "open" && incident.reason === "auto_pause" && !incident.pause_sent_at;
}

/** What the printer is doing decides what can be ordered: resume only from a pause; cancel while printing or
 * paused. The server checks the printer's own state again before sending anything. */
export function canResume(printerStatus: PrinterStatus, isAdmin: boolean): boolean {
  return isAdmin && printerStatus === "paused";
}

export function canCancel(printerStatus: PrinterStatus, isAdmin: boolean): boolean {
  return isAdmin && (printerStatus === "printing" || printerStatus === "paused");
}

/** One sentence on where the incident stands and what is left to do. */
export function statusExplanation(incident: Incident): string {
  if (incident.status === "closed") {
    const how = incident.outcome ? OUTCOME_LABELS[incident.outcome] : "Cerrado";
    return incident.decided_by ? `${how} (${incident.decided_by}).` : `${how}.`;
  }
  if (incident.status === "unconfirmed") {
    return "Se envió la pausa y la impresora no confirmó que quedara en pausa dentro de 20 s, o no se pudo enviar. Revisa la impresora ya.";
  }
  if (incident.status === "paused") return "La impresora está en pausa. Decide: reanudar, cancelar o ignorar el incidente.";
  if (incident.reason === "would_pause") return "Modo aviso: se habría pausado, pero no se envió ninguna orden a la impresora.";
  if (incident.reason === "auto_pause") {
    return incident.pause_sent_at
      ? "Pausa enviada; esperando que la impresora confirme."
      : "Cuenta regresiva en curso: la pausa se enviará salvo que se aborte.";
  }
  return "El modelo vio algo sobre el umbral, sin llegar a la regla de la pausa automática (3 capas seguidas de spaghetti). No se envió ninguna orden.";
}

export interface Milestone {
  key: string;
  label: string;
  at: string;
  /** Seconds since the first photo with the defect (null when that moment is unknown). */
  offsetS: number | null;
}

/** The incident's own timeline, oldest first: when the defect first showed, the warning, the pause sent and
 * confirmed, and the decision. */
export function milestones(incident: Incident): Milestone[] {
  const base = incident.first_defect_at ?? incident.opened_at;
  const baseMs = new Date(base).getTime();
  const steps: [string, string, string | null][] = [
    ["first_defect", "Primera foto con el defecto", incident.first_defect_at],
    ["opened", "Incidente abierto", incident.opened_at],
    ["announced", incident.reason === "would_pause" ? "Aviso (modo aviso)" : "Aviso y cuenta regresiva", incident.announced_at],
    ["pause_sent", "Pausa enviada a la impresora", incident.pause_sent_at],
    ["paused", "Klipper confirmó la pausa", incident.paused_at],
    ["decided", incident.outcome ? `Decisión: ${OUTCOME_LABELS[incident.outcome]}` : "Decisión", incident.decided_at],
  ];
  return steps
    .filter((step): step is [string, string, string] => step[2] !== null)
    .map(([key, label, at]) => ({ key, label, at, offsetS: Number.isFinite(baseMs) ? (new Date(at).getTime() - baseMs) / 1000 : null }))
    .sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());
}

/** The text of the banner that follows the user across the web while an incident is unclosed. */
export function noticeText(incident: Incident, printerName: string, className: string): string {
  const layer = incident.streak.length > 0 ? incident.streak[incident.streak.length - 1].layer : null;
  const where = layer !== null ? `${className}, capa ${layer}` : className;
  return `${REASON_LABELS[incident.reason]} en ${printerName}: ${where}`;
}
