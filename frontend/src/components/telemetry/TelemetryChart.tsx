import { useEffect, useRef, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatShortTime, formatTime } from "../../lib/format";

const TICK_STEPS_S = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400];
const PX_PER_TICK = 85; // room for an HH:MM:SS label and its gap
// Colombia keeps UTC-5 all year, so this puts the ticks on round local times.
const BOGOTA_OFFSET_MS = -5 * 3600 * 1000;

/** Ticks on round times (every 15 s, 5 min, 1 h...), at most maxTicks of them. Recharts' own
 * ticks on a time axis land on odd seconds and sometimes overlap. */
function timeTicks(start: number, end: number, maxTicks: number): { ticks: number[]; step: number } {
  const span = end - start;
  if (!(span > 0)) return { ticks: [], step: 0 };
  const stepS = TICK_STEPS_S.find((step) => span / (step * 1000) <= maxTicks) ?? Math.ceil(span / maxTicks / 86_400_000) * 86_400;
  const step = stepS * 1000;
  const ticks: number[] = [];
  for (let t = Math.ceil((start + BOGOTA_OFFSET_MS) / step) * step - BOGOTA_OFFSET_MS; t <= end; t += step) ticks.push(t);
  return { ticks, step };
}

function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

// Recharts takes colors as attributes, so the theme's values are repeated here as literals.
export const CHART_COLORS = {
  grid: "#283346",
  axis: "#69788f",
  cursor: "#ffffff",
  vermillion: "#D55E00",
  sky: "#56B4E9",
  green: "#009E73",
  yellow: "#F0E442",
  purple: "#CC79A7",
  orange: "#E69F00",
  blue: "#0072B2",
};

export interface SeriesSpec {
  key: string;
  name: string;
  color: string;
  dashed?: boolean;
}

export interface ChartMarker {
  t: number;
  label: string;
  color: string;
}

export type ChartRow = { t: number } & Record<string, number | null>;

function ChartTooltip({
  active,
  payload,
  label,
  unit,
}: {
  active?: boolean;
  payload?: { name: string; value: number | null; color: string }[];
  label?: number;
  unit: string;
}) {
  if (!active || !payload?.length || label == null) return null;
  return (
    <div className="rounded-lg border border-line bg-surface-2/95 px-3 py-2 text-xs shadow-lg backdrop-blur">
      <p className="mb-1 tabular text-muted">{formatTime(label)}</p>
      {payload.map((item) => (
        <p key={item.name} className="flex items-center gap-2 tabular">
          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: item.color }} />
          <span className="text-muted">{item.name}</span>
          <span className="ml-auto pl-3 text-fg">
            {item.value == null ? "—" : `${item.value.toFixed(1)} ${unit}`}
          </span>
        </p>
      ))}
    </div>
  );
}

/** A time series with vertical markers (events, defects) and, for the replay, a cursor. Clicking
 * the chart reports the time under the pointer. */
export function TelemetryChart({
  rows,
  series,
  unit,
  markers = [],
  cursor,
  onSeek,
  domain,
  height = 220,
}: {
  rows: ChartRow[];
  series: SeriesSpec[];
  unit: string;
  markers?: ChartMarker[];
  cursor?: number | null;
  onSeek?: (t: number) => void;
  domain?: [number, number];
  height?: number;
}) {
  const [ref, width] = useWidth();
  const [start, end]: [number, number] = domain ?? (rows.length > 1 ? [rows[0].t, rows[rows.length - 1].t] : [0, 0]);
  const { ticks, step } = timeTicks(start, end, Math.max(2, Math.floor((width - 52) / PX_PER_TICK)));
  // Seconds only when the ticks are less than a minute apart (a fresh print).
  const tickFormat = step < 60_000 ? formatTime : formatShortTime;
  return (
    <div ref={ref} style={{ height }} className="w-full">
      <ResponsiveContainer>
        <LineChart
          data={rows}
          margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
          onClick={(state) => {
            if (onSeek && state?.activeLabel != null) onSeek(Number(state.activeLabel));
          }}
        >
          <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={domain ?? ["dataMin", "dataMax"]}
            ticks={ticks}
            interval={0}
            tickFormatter={(value: number) => tickFormat(value)}
            stroke={CHART_COLORS.axis}
            fontSize={11}
            tickLine={false}
            axisLine={false}
          />
          <YAxis stroke={CHART_COLORS.axis} fontSize={11} tickLine={false} axisLine={false} width={40} />
          <Tooltip content={<ChartTooltip unit={unit} />} cursor={{ stroke: CHART_COLORS.axis, strokeWidth: 1 }} />
          {markers.map((marker, index) => (
            <ReferenceLine key={index} x={marker.t} stroke={marker.color} strokeOpacity={0.7} strokeDasharray="3 3" ifOverflow="hidden" />
          ))}
          {series.map((spec) => (
            <Line
              key={spec.key}
              type="monotone"
              dataKey={spec.key}
              name={spec.name}
              stroke={spec.color}
              strokeWidth={spec.dashed ? 1.2 : 1.8}
              strokeDasharray={spec.dashed ? "5 4" : undefined}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          ))}
          {cursor != null && <ReferenceLine x={cursor} stroke={CHART_COLORS.cursor} strokeWidth={1.2} ifOverflow="hidden" />}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function SeriesLegend({ series }: { series: SeriesSpec[] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
      {series.map((spec) => (
        <span key={spec.key} className="flex items-center gap-1.5">
          <svg width="18" height="6" aria-hidden="true">
            <line x1="0" y1="3" x2="18" y2="3" stroke={spec.color} strokeWidth="2" strokeDasharray={spec.dashed ? "4 3" : undefined} />
          </svg>
          {spec.name}
        </span>
      ))}
    </div>
  );
}
