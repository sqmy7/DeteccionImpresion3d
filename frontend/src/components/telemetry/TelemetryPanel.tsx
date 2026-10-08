import { useMemo, useState } from "react";
import type { TelemetryValues } from "../../types/api";
import { Card, EmptyState, Tabs } from "../ui";
import { CHART_COLORS, SeriesLegend, TelemetryChart, type ChartMarker, type ChartRow, type SeriesSpec } from "./TelemetryChart";

export type TimedValues = TelemetryValues & { ts: string };

type Group = "temperatures" | "motion" | "factors" | "extra";

const PERCENT_KEYS: (keyof TelemetryValues)[] = ["speed_factor", "extrude_factor", "fan_speed", "extruder_power", "bed_power"];
const EXTRA_COLORS = [CHART_COLORS.green, CHART_COLORS.yellow, CHART_COLORS.purple, CHART_COLORS.orange, CHART_COLORS.blue];

const GROUPS: Record<Exclude<Group, "extra">, { unit: string; series: SeriesSpec[] }> = {
  temperatures: {
    unit: "°C",
    series: [
      { key: "extruder_temp", name: "Boquilla", color: CHART_COLORS.vermillion },
      { key: "extruder_target", name: "Objetivo boquilla", color: CHART_COLORS.vermillion, dashed: true },
      { key: "bed_temp", name: "Cama", color: CHART_COLORS.sky },
      { key: "bed_target", name: "Objetivo cama", color: CHART_COLORS.sky, dashed: true },
    ],
  },
  motion: {
    unit: "mm/s",
    series: [
      { key: "velocity", name: "Velocidad del cabezal", color: CHART_COLORS.green },
      { key: "extruder_velocity", name: "Velocidad del filamento", color: CHART_COLORS.orange },
    ],
  },
  factors: {
    unit: "%",
    series: [
      { key: "speed_factor", name: "Factor de velocidad", color: CHART_COLORS.yellow },
      { key: "extrude_factor", name: "Factor de flujo", color: CHART_COLORS.purple },
      { key: "fan_speed", name: "Ventilador de capa", color: CHART_COLORS.sky },
      { key: "extruder_power", name: "Potencia boquilla", color: CHART_COLORS.vermillion, dashed: true },
      { key: "bed_power", name: "Potencia cama", color: CHART_COLORS.blue, dashed: true },
    ],
  },
};

function toRows(points: TimedValues[]): ChartRow[] {
  return points.map((point) => {
    const row: ChartRow = { t: Date.parse(point.ts) };
    for (const [key, value] of Object.entries(point)) {
      if (key === "ts" || key === "extra" || typeof value !== "number") continue;
      row[key] = PERCENT_KEYS.includes(key as keyof TelemetryValues) ? value * 100 : value;
    }
    for (const [key, value] of Object.entries(point.extra ?? {})) {
      // print_stats.* is bookkeeping (the clock the remaining-time estimate uses), not a sensor.
      if (typeof value === "number" && !key.startsWith("print_stats.")) row[`extra:${key}`] = value;
    }
    return row;
  });
}

function extraName(key: string): string {
  return key
    .replace(/^extra:/, "")
    .replace(/^temperature_sensor /, "")
    .replace(/^temperature_fan /, "")
    .replace(/^heater_fan /, "ventilador ")
    .replace(/^controller_fan /, "ventilador ")
    .replace(/\.temperature$/, " (°C)")
    .replace(/\.speed$/, " (0-1)");
}

/** Telemetry charts grouped by kind, sharing markers and (in the replay) a time cursor. */
export function TelemetryPanel({
  points,
  markers,
  cursor,
  onSeek,
  domain,
  title = "Telemetría",
  subtitle,
}: {
  points: TimedValues[];
  markers?: ChartMarker[];
  cursor?: number | null;
  onSeek?: (t: number) => void;
  domain?: [number, number];
  title?: string;
  subtitle?: string;
}) {
  const [group, setGroup] = useState<Group>("temperatures");
  const rows = useMemo(() => toRows(points), [points]);

  const extraSeries = useMemo<SeriesSpec[]>(() => {
    const keys = new Set<string>();
    rows.forEach((row) => Object.keys(row).forEach((key) => key.startsWith("extra:") && keys.add(key)));
    return [...keys].sort().map((key, index) => ({ key, name: extraName(key), color: EXTRA_COLORS[index % EXTRA_COLORS.length] }));
  }, [rows]);

  const current = group === "extra" ? { unit: "", series: extraSeries } : GROUPS[group];

  return (
    <Card title={title} subtitle={subtitle} padded={false}>
      <Tabs
        className="px-2"
        value={group}
        onChange={setGroup}
        items={[
          { value: "temperatures", label: "Temperaturas" },
          { value: "motion", label: "Movimiento" },
          { value: "factors", label: "Factores y potencia" },
          ...(extraSeries.length ? [{ value: "extra" as const, label: "Sensores extra" }] : []),
        ]}
      />
      {rows.length < 2 ? (
        <EmptyState
          title="Sin datos de telemetría"
          description="La telemetría se guarda una vez por segundo mientras hay una impresión en curso (desde que se activó esta función)."
        />
      ) : (
        <div className="flex flex-col gap-2 p-4 pt-3">
          <SeriesLegend series={current.series} />
          <TelemetryChart rows={rows} series={current.series} unit={current.unit} markers={markers} cursor={cursor} onSeek={onSeek} domain={domain} />
          {markers && markers.length > 0 && (
            <p className="text-xs text-faint">Las líneas verticales marcan eventos de la bitácora y capas con defecto.</p>
          )}
        </div>
      )}
    </Card>
  );
}
