import { CHART_COLORS, type ChartMarker } from "../components/telemetry/TelemetryChart";
import { getLayerStatus } from "../config/defectClasses";
import { EVENT_LABELS, INTERVENTION_TYPES, PRINT_STATE_LABELS } from "../config/events";
import type { Layer, PrinterEvent, TimelineEntry } from "../types/api";

/** Vertical marks for the charts: state changes, interventions that weren't programmed in the
 * file, and errors. */
export function eventMarkers(events: PrinterEvent[]): ChartMarker[] {
  const markers: ChartMarker[] = [];
  for (const event of events) {
    const t = Date.parse(event.ts);
    if (event.event_type === "state_changed") {
      const after = String(event.value_after);
      const color =
        after === "paused" ? CHART_COLORS.orange : after === "error" ? CHART_COLORS.vermillion : after === "printing" ? CHART_COLORS.green : CHART_COLORS.axis;
      markers.push({ t, color, label: PRINT_STATE_LABELS[after] ?? after });
    } else if (event.event_type === "gcode_error") {
      markers.push({ t, color: CHART_COLORS.vermillion, label: "Error de G-code" });
    } else if (INTERVENTION_TYPES.includes(event.event_type) && event.event_type !== "console_command" && event.origin !== "gcode_file") {
      markers.push({
        t,
        color: event.origin === "external" ? CHART_COLORS.yellow : CHART_COLORS.blue,
        label: EVENT_LABELS[event.event_type] ?? event.event_type,
      });
    }
  }
  return markers;
}

/** A mark at the time each layer with a defect started. */
export function defectMarkers(layers: Layer[], entries: TimelineEntry[]): ChartMarker[] {
  const defective = new Set(
    entries.filter((entry) => getLayerStatus(entry.has_defect, entry.defect_classes) === "defect").map((entry) => entry.layer_number),
  );
  return layers
    .filter((layer) => defective.has(layer.layer_number))
    .map((layer) => ({ t: Date.parse(layer.detected_at), color: CHART_COLORS.vermillion, label: `Defecto en la capa ${layer.layer_number}` }));
}
