import { Activity, AlertTriangle, CheckCircle2, HelpCircle } from "lucide-react";
import type { ReactNode } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { usePrinterContext } from "../components/layout/PrinterLayout";
import { CHART_COLORS } from "../components/telemetry/TelemetryChart";
import { Badge, Card, EmptyState, ErrorNote, EstimateNote, Skeleton, type Tone } from "../components/ui";
import { countOf, formatDate, formatNumber } from "../lib/format";
import { useApi } from "../lib/useApi";
import { getPrinterHealth } from "../services/insights";
import type { HealthMethod, HealthMetric, HealthPoint, HealthStatus } from "../types/api";

const STATUS: Record<HealthStatus, { label: string; tone: Tone; icon: ReactNode }> = {
  normal: { label: "Normal", tone: "ok", icon: <CheckCircle2 size={14} /> },
  attention: { label: "Atención", tone: "warn", icon: <AlertTriangle size={14} /> },
  insufficient: { label: "Sin datos suficientes", tone: "neutral", icon: <HelpCircle size={14} /> },
};

const FLAG_LABELS: Record<string, string> = {
  beyond_3sigma: "fuera de ±3σ",
  two_of_three_beyond_2sigma: "2 de 3 más allá de 2σ",
  eight_on_worse_side: "8 seguidos del lado malo",
};

// Power is stored as a 0-1 fraction; it reads better as a percentage.
function scale(metric: HealthMetric, value: number): number {
  return metric.key === "hold_power" ? value * 100 : value;
}

function digits(metric: HealthMetric): number {
  return metric.key === "hold_power" ? 1 : 2;
}

function ChartTooltip({ active, payload, metric }: { active?: boolean; payload?: { payload: HealthPoint & { y: number } }[]; metric: HealthMetric }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="rounded-lg border border-line bg-surface-2/95 px-3 py-2 text-xs shadow-lg">
      <p className="text-fg">
        Trabajo #{point.job_id} · {formatDate(point.started_at)}
      </p>
      <p className="truncate text-muted">{point.file_name}</p>
      <p className="tabular text-fg">
        {formatNumber(point.y, digits(metric))} {metric.unit}
        {point.target != null && <span className="text-muted"> · objetivo {formatNumber(point.target, 0)} °C</span>}
      </p>
      {point.flags.length > 0 && <p className="text-warn-fg">{point.flags.map((flag) => FLAG_LABELS[flag] ?? flag).join(", ")}</p>}
    </div>
  );
}

function FlaggedDot(props: { cx?: number; cy?: number; payload?: HealthPoint }) {
  const { cx, cy, payload } = props;
  if (cx == null || cy == null) return null;
  const flagged = (payload?.flags.length ?? 0) > 0;
  return <circle cx={cx} cy={cy} r={flagged ? 4.5 : 3} fill={flagged ? CHART_COLORS.vermillion : CHART_COLORS.sky} stroke="#090c12" strokeWidth={1} />;
}

/** One metric over the jobs: the points, the baseline mean and its ±3σ control limits. */
function MetricPanel({ metric }: { metric: HealthMetric }) {
  const status = STATUS[metric.status];
  const data = metric.points.map((point) => ({ ...point, y: scale(metric, point.value), label: `#${point.job_id}` }));
  const last = data[data.length - 1];
  const baseline = metric.baseline;
  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-lg border border-line bg-surface-2/40 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium text-fg">{metric.label}</p>
          <p className="text-xs text-muted">
            {last ? (
              <>
                Último: <span className="tabular text-fg">{formatNumber(last.y, digits(metric))} {metric.unit}</span>
                {baseline && (
                  <>
                    {" "}
                    · línea base {formatNumber(scale(metric, baseline.mean), digits(metric))} ± {formatNumber(scale(metric, baseline.std), digits(metric))}{" "}
                    {metric.unit} ({countOf(baseline.n, "trabajo")})
                  </>
                )}
              </>
            ) : (
              "Sin mediciones todavía."
            )}
          </p>
        </div>
        <Badge tone={status.tone}>
          <span className="inline-flex items-center gap-1">
            {status.icon}
            {status.label}
          </span>
        </Badge>
      </div>

      {data.length > 0 && (
        <div className="h-36 w-full">
          <ResponsiveContainer>
            <LineChart data={data} margin={{ top: 6, right: 10, bottom: 0, left: 0 }}>
              <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" stroke={CHART_COLORS.axis} fontSize={10} tickLine={false} axisLine={false} minTickGap={16} />
              <YAxis stroke={CHART_COLORS.axis} fontSize={10} tickLine={false} axisLine={false} width={44} domain={["auto", "auto"]} />
              <Tooltip content={<ChartTooltip metric={metric} />} cursor={{ stroke: CHART_COLORS.axis, strokeWidth: 1 }} />
              {baseline && (
                <>
                  {/* extendDomain: the control limits stay in view even when every point is well inside them. */}
                  <ReferenceLine y={scale(metric, baseline.mean)} stroke={CHART_COLORS.axis} strokeDasharray="4 3" />
                  <ReferenceLine y={scale(metric, baseline.upper)} stroke={CHART_COLORS.orange} strokeDasharray="2 3" strokeOpacity={0.8} ifOverflow="extendDomain" />
                  <ReferenceLine y={scale(metric, baseline.lower)} stroke={CHART_COLORS.orange} strokeDasharray="2 3" strokeOpacity={0.8} ifOverflow="extendDomain" />
                </>
              )}
              <Line type="linear" dataKey="y" stroke={CHART_COLORS.sky} strokeWidth={1.5} dot={<FlaggedDot />} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {metric.findings.length > 0 ? (
        <ul className="flex flex-col gap-1 text-xs text-warn-fg">
          {metric.findings.map((finding) => (
            <li key={finding}>{finding}</li>
          ))}
        </ul>
      ) : metric.status === "insufficient" ? (
        <p className="text-xs text-faint">Hacen falta al menos 6 trabajos comparables (5 de línea base y 1 para comparar).</p>
      ) : null}
    </div>
  );
}

function MethodNote({ method }: { method: HealthMethod }) {
  return (
    <EstimateNote title="salud de la impresora: cómo se calcula" className="mt-3">
      <p>
        Para cada trabajo y cada calentador se toman las muestras de telemetría (1 por segundo) desde que la temperatura llega al
        objetivo con menos de {formatNumber(method.settle_delta_c, 0)} °C de diferencia (el mismo criterio con que Klipper da por
        asentado un calentador al esperar con M109) hasta que el objetivo cambia, mientras se imprimen capas. Hacen falta al menos{" "}
        {method.min_steady_samples} muestras así.
      </p>
      <ul className="flex list-disc flex-col gap-1 pl-4">
        {method.metrics.map((metric) => (
          <li key={metric.key}>
            <span className="text-fg">{metric.label}:</span> {metric.description}
          </li>
        ))}
      </ul>
      <p>
        Cada trabajo se compara con el pasado de esta misma impresora, no con valores de catálogo: la línea base son sus primeros{" "}
        {method.min_baseline_jobs} a {method.max_baseline_jobs} trabajos con el mismo objetivo (en pasos de{" "}
        {formatNumber(method.target_bucket_c, 0)} °C). Es una carta de control: se marca un trabajo fuera del promedio ± 3
        desviaciones estándar (Shewhart; por azar pasa en 3 de cada 1000), dos de tres seguidos más allá de 2 desviaciones, u ocho
        seguidos del lado malo del promedio (reglas de Western Electric para tendencias). Aparte, una desviación de más de{" "}
        {formatNumber(method.in_range_c, 0)} °C ya asentada se marca siempre: es la banda que Klipper considera en rango.
      </p>
      <p>
        Límites: la potencia para mantener la temperatura también depende de la temperatura del cuarto, del ventilador de capa, de la
        velocidad y del material, así que conviene comparar impresiones parecidas. Los umbrales todavía no se han contrastado con
        impresiones reales de la Creality Hi.
      </p>
    </EstimateNote>
  );
}

export function HealthPage() {
  const { printer } = usePrinterContext();
  const health = useApi((token) => getPrinterHealth(token, printer.id), [printer.id]);

  if (health.error) return <ErrorNote>{health.error}</ErrorNote>;
  if (!health.data) return <Skeleton className="h-96 w-full" />;
  const data = health.data;

  return (
    <div className="flex flex-col gap-4">
      <Card
        title={
          <span className="flex items-center gap-2">
            <Activity size={15} className="text-faint" />
            Tendencias de los calentadores
          </span>
        }
        subtitle={`${countOf(data.jobs_with_telemetry, "trabajo")} con telemetría de ${countOf(data.jobs_considered, "trabajo terminado", "trabajos terminados")}`}
      >
        <p className="text-sm text-muted">
          Cada punto es un trabajo terminado. La línea punteada gris es el promedio de la línea base y las naranjas, sus límites de
          control; un punto rojo rompió alguna regla.
        </p>
        <MethodNote method={data.method} />
      </Card>

      {data.jobs_with_telemetry === 0 ? (
        <Card>
          <EmptyState
            title="Todavía no hay trabajos con telemetría"
            description="La telemetría se guarda desde que se activó esa función; la salud se calcula con los trabajos terminados después."
          />
        </Card>
      ) : (
        data.heaters.map((heater) => (
          <Card
            key={heater.heater}
            title={heater.label}
            subtitle={heater.target_bucket != null ? `Comparando trabajos con objetivo de ~${formatNumber(heater.target_bucket, 0)} °C` : "Sin trabajos con la temperatura asentada"}
          >
            <div className="grid gap-3 md:grid-cols-2">
              {heater.metrics.map((metric) => (
                <MetricPanel key={metric.key} metric={metric} />
              ))}
            </div>
          </Card>
        ))
      )}
    </div>
  );
}
