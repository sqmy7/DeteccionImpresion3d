import { classColor, classLabel } from "../config/defectClasses";
import type { JobSummary } from "../types/api";

export function JobStatsRow({ summary }: { summary: JobSummary | null }) {
  if (!summary) {
    return <div className="px-4 py-3 text-sm text-slate-500 sm:px-6">Cargando estadísticas...</div>;
  }

  const classCounts = Object.entries(summary.defect_class_counts).sort((a, b) => b[1] - a[1]);

  return (
    <div className="flex flex-wrap gap-3 border-b border-slate-800 bg-slate-950 px-4 py-4 sm:px-6">
      <StatTile label="Capas capturadas" value={summary.layers_captured} valueClassName="text-slate-100" />
      <StatTile label="Sin defecto" value={summary.layers_ok} valueClassName="text-emerald-400" />
      <StatTile label="Con defecto" value={summary.layers_with_defect} valueClassName="text-red-400" />
      <StatTile label="Alertas activas" value={summary.active_alerts_count} valueClassName="text-amber-400" />

      {summary.total_layers_recorded > summary.layers_captured && (
        <StatTile
          label="Sin foto"
          value={summary.total_layers_recorded - summary.layers_captured}
          valueClassName="text-slate-400"
          title="Capas registradas por la impresora sin una captura exitosa - falla de cámara, no de detección"
        />
      )}

      {classCounts.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-l border-slate-800 pl-3">
          {classCounts.map(([name, count]) => (
            <span
              key={name}
              className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-slate-100"
              style={{ backgroundColor: `${classColor(name)}26`, border: `1px solid ${classColor(name)}66` }}
            >
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: classColor(name) }} />
              {classLabel(name)} · {count}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function StatTile({
  label,
  value,
  valueClassName,
  title,
}: {
  label: string;
  value: number;
  valueClassName: string;
  title?: string;
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 px-4 py-2" title={title}>
      <p className={`text-2xl font-bold tabular-nums ${valueClassName}`}>{value}</p>
      <p className="text-xs text-slate-400">{label}</p>
    </div>
  );
}
