import { ArrowUpDown, Droplet, Fan, Gauge, Move3d, Ruler, Thermometer } from "lucide-react";
import { formatNumber, formatPercent } from "../../lib/format";
import type { TelemetryValues } from "../../types/api";
import { Kpi, type Tone } from "../ui";

function heaterTone(temperature: number | null, target: number | null): Tone {
  if (temperature == null || !target) return "neutral";
  return Math.abs(temperature - target) > 5 ? "warn" : "ok";
}

function extraLabel(key: string): string {
  return key
    .replace(/^temperature_sensor /, "")
    .replace(/^temperature_fan /, "")
    .replace(/^heater_fan /, "ventilador ")
    .replace(/^controller_fan /, "ventilador ")
    .replace(/^filament_switch_sensor |^filament_motion_sensor /, "filamento ")
    .replace(/\.temperature$/, "")
    .replace(/\.speed$/, "")
    .replace(/\.filament_detected$/, "")
    .replace(/\.enabled$/, " (activo)");
}

function extraValue(key: string, value: number | boolean): string {
  if (typeof value === "boolean") return value ? "sí" : "no";
  if (key.endsWith(".temperature")) return `${value.toFixed(1)} °C`;
  if (key.endsWith(".speed")) return formatPercent(value);
  return String(value);
}

/** The printer's current readings as figures, with their targets next to them. */
export function LiveKpis({ values }: { values: TelemetryValues }) {
  const extra = Object.entries(values.extra ?? {}).filter(([key]) => !key.endsWith(".enabled"));
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3">
        <Kpi
          label="Boquilla"
          icon={<Thermometer size={14} />}
          value={formatNumber(values.extruder_temp, 1)}
          unit="°C"
          tone={heaterTone(values.extruder_temp, values.extruder_target)}
          hint={`Objetivo ${formatNumber(values.extruder_target, 0)} °C · potencia ${formatPercent(values.extruder_power)}`}
        />
        <Kpi
          label="Cama"
          icon={<Thermometer size={14} />}
          value={formatNumber(values.bed_temp, 1)}
          unit="°C"
          tone={heaterTone(values.bed_temp, values.bed_target)}
          hint={`Objetivo ${formatNumber(values.bed_target, 0)} °C · potencia ${formatPercent(values.bed_power)}`}
        />
        <Kpi
          label="Velocidad"
          icon={<Gauge size={14} />}
          value={formatNumber(values.velocity, 0)}
          unit="mm/s"
          hint={`Factor ${formatPercent(values.speed_factor)}`}
          tone={values.speed_factor != null && Math.abs(values.speed_factor - 1) > 0.001 ? "info" : "neutral"}
        />
        <Kpi
          label="Flujo"
          icon={<Droplet size={14} />}
          value={formatPercent(values.extrude_factor)}
          hint={`Filamento ${formatNumber(values.filament_used != null ? values.filament_used / 1000 : null, 2, "m")}`}
          tone={values.extrude_factor != null && Math.abs(values.extrude_factor - 1) > 0.001 ? "info" : "neutral"}
        />
        <Kpi label="Ventilador de capa" icon={<Fan size={14} />} value={formatPercent(values.fan_speed)} />
        <Kpi
          label="Desfase de Z"
          icon={<ArrowUpDown size={14} />}
          value={formatNumber(values.z_offset, 3)}
          unit="mm"
          hint="Babystepping"
          tone={values.z_offset ? "info" : "neutral"}
        />
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-line bg-surface px-3 py-2 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <Move3d size={14} className="text-faint" />X {formatNumber(values.x, 1)} · Y {formatNumber(values.y, 1)} · Z {formatNumber(values.z, 2)} mm
        </span>
        {extra.map(([key, value]) => (
          <span key={key} className="flex items-center gap-1.5">
            <Ruler size={13} className="text-faint" />
            {extraLabel(key)}: <span className="tabular text-fg">{extraValue(key, value)}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
