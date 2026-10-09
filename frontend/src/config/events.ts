// How event-log entries read in Spanish. The backend stores codes (event_type, origin, field);
// every word shown to people lives here.
import type { Tone } from "../components/ui";
import type { EventOrigin, PrinterEvent } from "../types/api";

export const ORIGIN_INFO: Record<EventOrigin, { label: string; tone: Tone; description: string }> = {
  printwatch: {
    label: "PrintWatch",
    tone: "accent",
    description: "Orden enviada por PrintWatch: pausa automática o botones de la web.",
  },
  console: {
    label: "Consola",
    tone: "info",
    description: "Comando de G-code que aparece en el registro de consola de Moonraker (Fluidd, Mainsail u otro cliente).",
  },
  gcode_file: {
    label: "Archivo G-code",
    tone: "neutral",
    description: "Programado en el archivo que se imprime o en una macro que el archivo llama.",
  },
  printer: {
    label: "Impresora",
    tone: "neutral",
    description: "Lo hizo la propia impresora: errores de Klipper, fin del archivo, sensores.",
  },
  external: {
    label: "Externo",
    tone: "warn",
    description:
      "Sin evidencia de quién lo hizo: la pantalla de la impresora, los botones de pausa de Fluidd u otra aplicación. No se puede saber cuál.",
  },
  monitor: {
    label: "Monitor",
    tone: "neutral",
    description: "La conexión de PrintWatch con la impresora.",
  },
};

export const EVENT_LABELS: Record<string, string> = {
  monitor_connected: "PrintWatch se conectó",
  monitor_disconnected: "PrintWatch perdió la conexión",
  state_changed: "Cambio de estado",
  printwatch_command: "Orden de PrintWatch",
  "auto_pause.would_pause": "Habría pausado (modo aviso)",
  "auto_pause.pending": "Cuenta regresiva de la pausa automática",
  "auto_pause.aborted": "Cuenta abortada",
  "auto_pause.confirmed": "Pausa confirmada por la impresora",
  "auto_pause.not_confirmed": "Pausa NO confirmada",
  target_changed: "Temperatura objetivo",
  speed_factor_changed: "Factor de velocidad",
  flow_factor_changed: "Factor de flujo",
  fan_changed: "Ventilador",
  z_offset_changed: "Desfase de Z (babystepping)",
  object_excluded: "Objeto excluido",
  filament_sensor_changed: "Sensor de filamento",
  klippy_state_changed: "Estado de Klipper",
  klippy_disconnected: "Klipper desconectado",
  klippy_shutdown: "Klipper apagado",
  klippy_ready: "Klipper listo",
  console_command: "Comando de consola",
  gcode_error: "Error de G-code",
};

// Interventions: what someone did to the print, as opposed to the printer's own state changes.
export const INTERVENTION_TYPES = [
  "target_changed",
  "speed_factor_changed",
  "flow_factor_changed",
  "fan_changed",
  "z_offset_changed",
  "object_excluded",
  "console_command",
];

export const PRINT_STATE_LABELS: Record<string, string> = {
  standby: "En espera",
  printing: "Imprimiendo",
  paused: "Pausada",
  complete: "Completada",
  cancelled: "Cancelada",
  error: "Error",
};

const PHASE_LABELS: Record<string, string> = {
  start: "secuencia de inicio",
  printing: "durante la impresión",
  end: "secuencia final",
  paused: "en pausa",
  idle: "sin impresión",
};

export function phaseLabel(phase: unknown): string | null {
  return typeof phase === "string" ? PHASE_LABELS[phase] ?? phase : null;
}

function fieldName(field: string | null): string {
  if (!field) return "";
  if (field === "extruder.target") return "Boquilla";
  if (field === "heater_bed.target") return "Cama";
  if (field.endsWith(".target")) return field.replace(/^heater_generic |^temperature_fan /, "").replace(".target", "");
  if (field === "gcode_move.speed_factor") return "Velocidad";
  if (field === "gcode_move.extrude_factor") return "Flujo";
  if (field === "fan.speed") return "Ventilador de capa";
  if (field.startsWith("fan_generic ")) return `Ventilador ${field.slice(12).replace(".speed", "")}`;
  if (field === "gcode_move.homing_origin[2]") return "Desfase de Z";
  if (field.endsWith(".filament_detected")) return "Filamento";
  return field;
}

function formatValue(field: string | null, value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "sí" : "no";
  if (typeof value === "number") {
    if (field?.endsWith(".target")) return `${value.toFixed(0)} °C`;
    if (field === "gcode_move.speed_factor" || field === "gcode_move.extrude_factor" || field?.endsWith(".speed")) {
      return `${Math.round(value * 100)} %`;
    }
    if (field === "gcode_move.homing_origin[2]") return `${value >= 0 ? "+" : ""}${value.toFixed(3)} mm`;
    return String(value);
  }
  if (field === "print_stats.state" && typeof value === "string") return PRINT_STATE_LABELS[value] ?? value;
  return String(value);
}

/** One line describing what changed, e.g. "Boquilla: 240 °C → 245 °C". */
export function describeEvent(event: PrinterEvent): string {
  const { event_type: type, field, value_before: before, value_after: after, detail } = event;
  switch (type) {
    case "state_changed":
      return `${formatValue(field, before)} → ${formatValue(field, after)}`;
    case "printwatch_command": {
      const action = (detail?.action as string) ?? "";
      const verb = { pause: "pausar", resume: "reanudar", cancel: "cancelar" }[action] ?? action;
      const who = detail?.source === "auto_pause" ? "pausa automática por spaghetti" : (detail?.requested_by as string) ?? "web";
      const failed = detail?.ok === false ? ` — falló: ${detail?.error ?? "sin detalle"}` : "";
      return `Pidió ${verb} (${who})${failed}`;
    }
    case "auto_pause.would_pause": {
      const layer = detail?.layer != null ? `capa ${String(detail.layer)}` : "capa desconocida";
      const confidence = typeof detail?.confidence === "number" ? `, confianza ${Math.round(detail.confidence * 100)} %` : "";
      return `Spaghetti en ${detail?.consecutive_layers ?? 3} capas seguidas (${layer}${confidence}); no se envió nada`;
    }
    case "auto_pause.pending": {
      const grace = typeof detail?.grace_seconds === "number" ? `${detail.grace_seconds} s` : "unos segundos";
      return `Spaghetti en ${detail?.streak ? (detail.streak as unknown[]).length : 3} capas seguidas: la pausa se enviará en ${grace} si nadie la aborta`;
    }
    case "auto_pause.aborted":
      return `La cuenta se abortó${detail?.requested_by ? ` (${String(detail.requested_by)})` : ""}: no se envió la pausa`;
    case "auto_pause.confirmed":
      return `Klipper pasó a «pausa» ${typeof detail?.seconds_after_sending === "number" ? `${detail.seconds_after_sending} s después de enviar la orden` : "tras la orden"}`;
    case "auto_pause.not_confirmed":
      return detail?.reason === "send_failed"
        ? `No se pudo enviar la pausa${detail?.error ? `: ${String(detail.error)}` : ""}`
        : `La impresora no confirmó la pausa en ${String(detail?.timeout_seconds ?? 20)} s (estado leído: ${String(detail?.last_state ?? "desconocido")})`;
    case "object_excluded":
      return String(after);
    case "console_command":
      return String(after);
    case "gcode_error":
      return String(after);
    case "monitor_connected":
      return `Estado al conectar: ${formatValue("print_stats.state", after)}`;
    case "monitor_disconnected":
      return String(detail?.reason ?? "");
    default:
      if (field) return `${fieldName(field)}: ${formatValue(field, before)} → ${formatValue(field, after)}`;
      return "";
  }
}

/** The evidence behind an origin, in words: the console command, the file line, who asked. */
export function describeEvidence(event: PrinterEvent): string | null {
  const detail = event.detail ?? {};
  if (event.origin === "console" && detail.command) return `Comando: ${String(detail.command)}`;
  if (event.origin === "gcode_file" && detail.line) {
    const via = detail.via_macro ? ` (vía macro ${String(detail.via_macro)})` : "";
    return `Línea del archivo: ${String(detail.line)}${via}`;
  }
  const order = detail.printwatch_order as Record<string, unknown> | undefined;
  if (event.origin === "printwatch" && order) {
    return order.source === "auto_pause" ? "Pausa automática por spaghetti" : `Pedido por ${String(order.requested_by ?? "la web")}`;
  }
  if (event.origin === "external" && detail.file_checked === false) {
    return "No se pudo revisar el archivo: también pudo estar programado";
  }
  const error = detail.error as Record<string, unknown> | undefined;
  if (error) return String(error.msg ?? error.message ?? "");
  return null;
}

export function eventTone(event: PrinterEvent): Tone {
  if (event.event_type === "gcode_error" || event.value_after === "error" || event.event_type === "klippy_shutdown") {
    return "danger";
  }
  if (event.event_type === "printwatch_command" && event.detail?.ok === false) return "danger";
  if (event.event_type === "auto_pause.not_confirmed") return "danger";
  return ORIGIN_INFO[event.origin]?.tone ?? "neutral";
}
