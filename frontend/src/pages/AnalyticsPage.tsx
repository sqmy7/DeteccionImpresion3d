import { BarChart3, CheckCircle2, Clock, Disc3, Hand, Layers } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BedMapView, BedPositionNote, MeshLegend } from "../components/bed/BedMapView";
import { PageHeader } from "../components/layout/PageHeader";
import { CHART_COLORS } from "../components/telemetry/TelemetryChart";
import { Badge, Card, EmptyState, ErrorNote, Kpi, Segmented, Skeleton, Table, Td, Th } from "../components/ui";
import { classColor, classLabel } from "../config/defectClasses";
import { ORIGIN_INFO } from "../config/events";
import { JOB_STATUS } from "../config/status";
import { usePrinters } from "../context/PrintersContext";
import { formatDate, formatDuration, formatNumber, formatPercent } from "../lib/format";
import { useApi } from "../lib/useApi";
import { getAnalyticsSummary } from "../services/analytics";
import { getBedHeatmap } from "../services/bedMap";
import type { EventOrigin, JobAnalytics, JobStatus } from "../types/api";

type Period = "7" | "30" | "all";

const STATUS_COLORS: Record<JobStatus, string> = {
  running: CHART_COLORS.sky,
  completed: CHART_COLORS.green,
  failed: CHART_COLORS.vermillion,
  cancelled: CHART_COLORS.axis,
};
const ORIGIN_COLORS: Record<string, string> = {
  console: CHART_COLORS.blue,
  external: CHART_COLORS.orange,
  printwatch: CHART_COLORS.sky,
  gcode_file: CHART_COLORS.axis,
  printer: CHART_COLORS.axis,
  monitor: CHART_COLORS.axis,
};

function SimpleTooltip({ active, payload, unit = "" }: { active?: boolean; payload?: { payload: { label: string; value: number } }[]; unit?: string }) {
  if (!active || !payload?.length) return null;
  const { label, value } = payload[0].payload;
  return (
    <div className="rounded-lg border border-line bg-surface-2/95 px-3 py-2 text-xs shadow-lg">
      <span className="text-muted">{label}: </span>
      <span className="tabular text-fg">
        {formatNumber(value, unit === "%" || unit === "°C" ? 1 : 0)} {unit}
      </span>
    </div>
  );
}

function HorizontalBars({ data, unit }: { data: { label: string; value: number; color: string }[]; unit?: string }) {
  if (!data.length) return <EmptyState title="Sin datos en este periodo" />;
  return (
    <div style={{ height: Math.max(120, data.length * 34 + 20) }}>
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 8 }}>
          <XAxis type="number" hide allowDecimals={false} />
          <YAxis type="category" dataKey="label" width={150} tick={{ fill: "#98a5ba", fontSize: 12 }} tickLine={false} axisLine={false} />
          <Tooltip content={<SimpleTooltip unit={unit} />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
          <Bar dataKey="value" radius={[0, 4, 4, 0]} isAnimationActive={false} label={{ position: "right", fill: "#e4e8f0", fontSize: 12 }}>
            {data.map((item) => (
              <Cell key={item.label} fill={item.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function PerJobChart({
  jobs,
  value,
  unit,
  onOpen,
}: {
  jobs: JobAnalytics[];
  value: (job: JobAnalytics) => number | null;
  unit: string;
  onOpen: (job: JobAnalytics) => void;
}) {
  const data = jobs
    .map((job) => ({ job, label: `#${job.id} ${job.file_name}`, value: value(job) }))
    .filter((item): item is { job: JobAnalytics; label: string; value: number } => item.value !== null);
  if (!data.length) return <EmptyState title="Sin datos en este periodo" />;
  return (
    <div className="h-56">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={false} axisLine={false} />
          <YAxis stroke={CHART_COLORS.axis} fontSize={11} tickLine={false} axisLine={false} width={36} />
          <Tooltip content={<SimpleTooltip unit={unit} />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
          <Bar dataKey="value" radius={[4, 4, 0, 0]} isAnimationActive={false} onClick={(entry) => onOpen((entry as unknown as { job: JobAnalytics }).job)} className="cursor-pointer">
            {data.map((item) => (
              <Cell key={item.job.id} fill={STATUS_COLORS[item.job.status]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function StatusLegend() {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
      {(Object.keys(STATUS_COLORS) as JobStatus[]).map((status) => (
        <span key={status} className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: STATUS_COLORS[status] }} />
          {JOB_STATUS[status].label}
        </span>
      ))}
    </div>
  );
}

export function AnalyticsPage() {
  const { printers } = usePrinters();
  const navigate = useNavigate();
  const [printerId, setPrinterId] = useState<number | null>(null);
  const [period, setPeriod] = useState<Period>("30");
  const days = period === "all" ? null : Number(period);
  const summary = useApi((token) => getAnalyticsSummary(token, printerId, days), [printerId, days]);
  const heatmap = useApi((token) => (printerId !== null ? getBedHeatmap(token, printerId, 20) : null), [printerId]);
  const data = summary.data;
  const open = (job: JobAnalytics) => navigate(`/printers/${job.printer_id}/jobs/${job.id}`);
  const printerName = (id: number) => printers.find((printer) => printer.id === id)?.name ?? `#${id}`;

  return (
    <>
      <PageHeader
        title="Analítica"
        subtitle="Resultados, defectos e intervenciones a lo largo de los trabajos"
        actions={
          <>
            <select
              value={printerId ?? ""}
              onChange={(event) => setPrinterId(event.target.value ? Number(event.target.value) : null)}
              className="h-8 rounded-md border border-line bg-surface-2 px-2 text-xs text-fg"
              aria-label="Impresora"
            >
              <option value="">Todas las impresoras</option>
              {printers.map((printer) => (
                <option key={printer.id} value={printer.id}>
                  {printer.name}
                </option>
              ))}
            </select>
            <Segmented
              label="Periodo"
              value={period}
              onChange={setPeriod}
              options={[
                { value: "7", label: "7 días" },
                { value: "30", label: "30 días" },
                { value: "all", label: "Todo" },
              ]}
            />
          </>
        }
      />

      {summary.error && <ErrorNote>{summary.error}</ErrorNote>}
      {!data ? (
        <div className="grid gap-3 sm:grid-cols-3">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      ) : data.totals.jobs === 0 ? (
        <Card>
          <EmptyState icon={<BarChart3 size={28} />} title="Sin trabajos en este periodo" description="Prueba con otro periodo o con todas las impresoras." />
        </Card>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Kpi label="Trabajos" value={data.totals.jobs} icon={<Layers size={14} />} />
            <Kpi
              label="Tasa de éxito"
              value={formatPercent(data.totals.success_rate)}
              icon={<CheckCircle2 size={14} />}
              tone={data.totals.success_rate != null && data.totals.success_rate < 0.8 ? "warn" : "ok"}
              hint="Completados sobre terminados"
            />
            <Kpi label="Horas de impresión" value={formatNumber(data.totals.print_hours, 1)} unit="h" icon={<Clock size={14} />} />
            <Kpi
              label="Capas con defecto"
              value={formatPercent(data.totals.defect_rate, 1)}
              hint={`${data.totals.layers_with_defect ?? 0} de ${data.totals.layers ?? 0}`}
              tone={data.totals.layers_with_defect ? "danger" : "ok"}
            />
            <Kpi label="Intervenciones" value={data.totals.interventions ?? 0} icon={<Hand size={14} />} hint="Consola y externas" />
            <Kpi label="Filamento" value={formatNumber(data.totals.filament_m, 1)} unit="m" icon={<Disc3 size={14} />} hint="Trabajos con telemetría" />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="Capas con defecto, por clase" subtitle="Sin las clases informativas">
              <HorizontalBars
                data={Object.entries(data.defects_by_class)
                  .sort((a, b) => b[1] - a[1])
                  .map(([name, value]) => ({ label: classLabel(name), value, color: classColor(name) }))}
              />
            </Card>
            <Card title="Resultado de los trabajos">
              <HorizontalBars
                data={(Object.keys(JOB_STATUS) as JobStatus[])
                  .filter((status) => data.status_counts[status])
                  .map((status) => ({ label: JOB_STATUS[status].label, value: data.status_counts[status], color: STATUS_COLORS[status] }))}
              />
            </Card>
            <Card title="Intervenciones por origen" subtitle="Cambios hechos durante la impresión">
              <HorizontalBars
                data={Object.entries(data.interventions_by_origin)
                  .sort((a, b) => b[1] - a[1])
                  .map(([origin, value]) => ({
                    label: ORIGIN_INFO[origin as EventOrigin]?.label ?? origin,
                    value,
                    color: ORIGIN_COLORS[origin] ?? CHART_COLORS.axis,
                  }))}
              />
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Capas con defecto por trabajo (%)" subtitle="En orden cronológico; clic en una barra para abrir el trabajo" actions={<StatusLegend />}>
              <PerJobChart jobs={data.jobs} value={(job) => (job.defect_rate == null ? null : job.defect_rate * 100)} unit="%" onOpen={open} />
            </Card>
            <Card title="Estabilidad de la boquilla (°C)" subtitle="Diferencia media con el objetivo mientras imprime capas" actions={<StatusLegend />}>
              <PerJobChart jobs={data.jobs} value={(job) => job.nozzle_error_mean_c} unit="°C" onOpen={open} />
            </Card>
          </div>

          <div className={`grid gap-4 ${printerId !== null ? "xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]" : ""}`}>
            <Card title="Trabajos" padded={false}>
              <Table>
                <thead>
                  <tr>
                    <Th>#</Th>
                    {printerId === null && <Th>Impresora</Th>}
                    <Th>Archivo</Th>
                    <Th>Estado</Th>
                    <Th>Inicio</Th>
                    <Th>Duración</Th>
                    <Th>Defecto</Th>
                    <Th>Interv.</Th>
                    <Th>Boquilla ±</Th>
                    <Th>Filamento</Th>
                  </tr>
                </thead>
                <tbody>
                  {[...data.jobs].reverse().map((job) => (
                    <tr key={job.id} onClick={() => open(job)} className="cursor-pointer hover:bg-surface-2">
                      <Td className="tabular text-muted">{job.id}</Td>
                      {printerId === null && <Td className="whitespace-nowrap">{printerName(job.printer_id)}</Td>}
                      <Td className="max-w-[14rem] truncate" title={job.file_name}>
                        {job.file_name}
                      </Td>
                      <Td>
                        <Badge tone={JOB_STATUS[job.status].tone}>{JOB_STATUS[job.status].label}</Badge>
                      </Td>
                      <Td className="whitespace-nowrap tabular text-muted">{formatDate(job.started_at)}</Td>
                      <Td className="whitespace-nowrap tabular">{formatDuration(job.duration_s)}</Td>
                      <Td className="tabular">
                        {job.layers_with_defect}/{job.layers}
                      </Td>
                      <Td className="tabular">{Object.values(job.interventions).reduce((sum, count) => sum + count, 0)}</Td>
                      <Td className="tabular">{job.nozzle_error_mean_c == null ? "—" : `${formatNumber(job.nozzle_error_mean_c, 1)} °C`}</Td>
                      <Td className="tabular">{job.filament_m == null ? "—" : `${formatNumber(job.filament_m, 1)} m`}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </Card>
            {printerId !== null && (
              <Card title="Dónde aparecen los defectos" subtitle="Todos los trabajos de la impresora" actions={<MeshLegend mesh={heatmap.data?.bed_mesh} />}>
                {heatmap.data ? (
                  <>
                    <BedMapView
                      geometry={{ axis_minimum: null, axis_maximum: [heatmap.data.width_mm, heatmap.data.depth_mm], bed_mesh: heatmap.data.bed_mesh, objects: [] }}
                      heatmap={{ cellMm: heatmap.data.cell_mm, counts: heatmap.data.counts }}
                    />
                    <p className="mt-2 text-xs text-muted">
                      {heatmap.data.located} ubicados · {heatmap.data.unreliable} poco confiables · {heatmap.data.skipped_boxes} sin ubicar (cámara sin calibrar o formato antiguo)
                    </p>
                    <BedPositionNote className="mt-3" />
                  </>
                ) : (
                  <Skeleton className="aspect-square w-full" />
                )}
              </Card>
            )}
          </div>
        </div>
      )}
    </>
  );
}
