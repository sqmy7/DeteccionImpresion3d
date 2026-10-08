import { useMemo } from "react";
import { classCode, classColor, classLabel } from "../../config/defectClasses";
import type { BedGeometry, BedMesh, LocatedDefect } from "../../types/api";

const MARGIN = 14; // mm of room around the bed for labels
const RIGHT_MARGIN = 22; // the X axis caption sits right of the last tick
const GRID_MM = 20;
const DEFAULT_SIZE = 260; // Creality Hi spec sheet, when Klipper hasn't reported its limits
const MAX_UNCERTAINTY_DRAWN = 45;

// Diverging scale for the bed mesh (blue = low, orange = high), from the Okabe-Ito palette.
const MESH_LOW = [0, 114, 178];
const MESH_HIGH = [230, 159, 0];

export interface HeatmapOverlay {
  cellMm: number;
  counts: number[][]; // [row from the front][column from the left]
}

export function bedSize(geometry: BedGeometry | null | undefined): { width: number; depth: number } {
  const maximum = geometry?.axis_maximum ?? [];
  return {
    width: maximum.length > 1 && maximum[0] ? maximum[0] : DEFAULT_SIZE,
    depth: maximum.length > 1 && maximum[1] ? maximum[1] : DEFAULT_SIZE,
  };
}

function meshColor(value: number, limit: number): string {
  const t = limit === 0 ? 0.5 : Math.max(0, Math.min(1, (value + limit) / (2 * limit)));
  const [r, g, b] = MESH_LOW.map((low, index) => Math.round(low + (MESH_HIGH[index] - low) * t));
  return `rgb(${r}, ${g}, ${b})`;
}

function MeshLayer({ mesh, sy }: { mesh: BedMesh; sy: (y: number) => number }) {
  const rows = mesh.probed_matrix;
  if (!rows.length || !rows[0].length) return null;
  const [minX, minY] = mesh.mesh_min;
  const [maxX, maxY] = mesh.mesh_max;
  const cellW = (maxX - minX) / Math.max(1, rows[0].length - 1);
  const cellH = (maxY - minY) / Math.max(1, rows.length - 1);
  const limit = Math.max(0.01, ...rows.flat().map((value) => Math.abs(value)));

  // One cell per probe point, clipped to the probed area, faint enough to read what's on top.
  return (
    <g opacity={0.2}>
      {rows.map((row, rowIndex) =>
        row.map((value, columnIndex) => {
          const x0 = Math.max(minX, minX + columnIndex * cellW - cellW / 2);
          const x1 = Math.min(maxX, minX + columnIndex * cellW + cellW / 2);
          const y0 = Math.max(minY, minY + rowIndex * cellH - cellH / 2);
          const y1 = Math.min(maxY, minY + rowIndex * cellH + cellH / 2);
          return (
            <rect key={`${rowIndex}-${columnIndex}`} x={x0} y={sy(y1)} width={x1 - x0} height={y1 - y0} fill={meshColor(value, limit)}>
              <title>{`Malla: ${value >= 0 ? "+" : ""}${value.toFixed(3)} mm`}</title>
            </rect>
          );
        }),
      )}
    </g>
  );
}

function HeatLayer({ heatmap, sy }: { heatmap: HeatmapOverlay; sy: (y: number) => number }) {
  const max = Math.max(1, ...heatmap.counts.flat());
  const size = heatmap.cellMm;
  return (
    <g>
      {heatmap.counts.map((row, rowIndex) =>
        row.map((count, columnIndex) =>
          count > 0 ? (
            <g key={`${rowIndex}-${columnIndex}`}>
              <rect
                x={columnIndex * size}
                y={sy((rowIndex + 1) * size)}
                width={size}
                height={size}
                fill="#D55E00"
                fillOpacity={0.15 + 0.7 * (count / max)}
              >
                <title>{`${count} defecto${count === 1 ? "" : "s"} en esta celda`}</title>
              </rect>
              <text
                x={columnIndex * size + size / 2}
                y={sy(rowIndex * size + size / 2)}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={size * 0.38}
                fill="white"
                fontWeight={600}
              >
                {count}
              </text>
            </g>
          ) : null,
        ),
      )}
    </g>
  );
}

/** The bed seen from above in millimetres: Y grows away from the viewer, as in Klipper, so the
 * front edge is at the bottom. Defects are drawn with their class code (not only color), and
 * the unreliable ones as a dashed circle the size of their estimated error. */
export function BedMapView({
  geometry,
  defects = [],
  head,
  trail,
  path,
  heatmap,
  showMesh = true,
  selectedDefectId,
  onSelectDefect,
  className = "",
}: {
  geometry: BedGeometry | null | undefined;
  defects?: LocatedDefect[];
  head?: { x: number | null; y: number | null } | null;
  trail?: [number, number][];
  path?: [number, number][];
  heatmap?: HeatmapOverlay;
  showMesh?: boolean;
  selectedDefectId?: number | null;
  onSelectDefect?: (defect: LocatedDefect) => void;
  className?: string;
}) {
  const { width, depth } = bedSize(geometry);
  const sy = (y: number) => depth - y;
  const objects = geometry?.objects ?? [];
  const ticks = useMemo(() => {
    const values: number[] = [];
    for (let value = 0; value <= Math.max(width, depth); value += 50) values.push(value);
    return values;
  }, [width, depth]);

  const polyline = (points: [number, number][]) => points.map(([x, y]) => `${x},${sy(y)}`).join(" ");

  return (
    <svg
      viewBox={`${-MARGIN} ${-MARGIN} ${width + MARGIN + RIGHT_MARGIN} ${depth + MARGIN * 2}`}
      className={`h-auto w-full select-none ${className}`}
      role="img"
      aria-label={`Mapa de la cama de ${width} por ${depth} milímetros`}
    >
      <rect x={0} y={0} width={width} height={depth} rx={3} className="fill-surface-2 stroke-line" strokeWidth={1} />

      {showMesh && geometry?.bed_mesh && <MeshLayer mesh={geometry.bed_mesh} sy={sy} />}
      {heatmap && <HeatLayer heatmap={heatmap} sy={sy} />}

      <g className="stroke-line" strokeWidth={0.4} opacity={0.7}>
        {Array.from({ length: Math.floor(width / GRID_MM) + 1 }, (_, index) => (
          <line key={`x${index}`} x1={index * GRID_MM} y1={0} x2={index * GRID_MM} y2={depth} />
        ))}
        {Array.from({ length: Math.floor(depth / GRID_MM) + 1 }, (_, index) => (
          <line key={`y${index}`} x1={0} y1={sy(index * GRID_MM)} x2={width} y2={sy(index * GRID_MM)} />
        ))}
      </g>

      <g fontSize={6} className="fill-faint">
        {ticks
          .filter((value) => value <= width)
          .map((value) => (
            <text key={`tx${value}`} x={value} y={depth + 9} textAnchor="middle">
              {value}
            </text>
          ))}
        {ticks
          .filter((value) => value <= depth)
          .map((value) => (
            <text key={`ty${value}`} x={-4} y={sy(value)} textAnchor="end" dominantBaseline="central">
              {value}
            </text>
          ))}
        <text x={width / 2} y={-5} textAnchor="middle">
          fondo
        </text>
        <text x={0} y={-5} textAnchor="start">
          Y mm
        </text>
        <text x={width + 4} y={depth + 9} textAnchor="start">
          X mm
        </text>
      </g>

      {path && path.length > 1 && (
        <polyline points={polyline(path)} fill="none" className="stroke-accent" strokeOpacity={0.25} strokeWidth={0.6} />
      )}

      {objects.map((object) =>
        object.polygon && object.polygon.length > 2 ? (
          <g key={object.name}>
            <polygon
              points={polyline(object.polygon)}
              className="fill-accent stroke-accent-fg"
              fillOpacity={0.08}
              strokeOpacity={0.7}
              strokeWidth={0.8}
            />
            {object.center && (
              <text x={object.center[0]} y={sy(object.center[1])} textAnchor="middle" dominantBaseline="central" fontSize={5} className="fill-muted">
                {object.name}
              </text>
            )}
          </g>
        ) : null,
      )}

      {trail && trail.length > 1 && (
        <polyline points={polyline(trail)} fill="none" className="stroke-accent" strokeWidth={1.1} strokeLinejoin="round" strokeOpacity={0.8} />
      )}

      {defects.map((defect) => {
        const color = classColor(defect.class_name ?? "");
        const selected = defect.detection_id === selectedDefectId;
        const radius = defect.reliable ? 4.5 : Math.min(defect.uncertainty_mm, MAX_UNCERTAINTY_DRAWN);
        const label = `${classLabel(defect.class_name ?? "")} · capa ${defect.layer_number} · ${
          defect.confidence != null ? `${Math.round(defect.confidence * 100)} %` : ""
        } · ±${defect.uncertainty_mm} mm${defect.reliable ? "" : " (poco confiable)"}`;
        return (
          <g
            key={`${defect.detection_id}-${defect.x}-${defect.y}`}
            onClick={onSelectDefect ? () => onSelectDefect(defect) : undefined}
            className={onSelectDefect ? "cursor-pointer" : undefined}
          >
            <title>{label}</title>
            {defect.reliable ? (
              <circle cx={defect.x} cy={sy(defect.y)} r={radius} fill={color} stroke={selected ? "white" : "#090c12"} strokeWidth={selected ? 1.6 : 0.8} />
            ) : (
              <>
                <circle cx={defect.x} cy={sy(defect.y)} r={radius} fill={color} fillOpacity={0.08} stroke={color} strokeWidth={0.8} strokeDasharray="2 2" />
                <circle cx={defect.x} cy={sy(defect.y)} r={1.6} fill={color} />
              </>
            )}
            <text
              x={defect.x}
              y={sy(defect.y) - (defect.reliable ? 6.5 : 3.5)}
              textAnchor="middle"
              fontSize={4.5}
              fontWeight={700}
              fill={color}
            >
              {classCode(defect.class_name ?? "")}
            </text>
          </g>
        );
      })}

      {head && head.x != null && head.y != null && (
        <g pointerEvents="none">
          <circle cx={head.x} cy={sy(head.y)} r={4} fill="none" stroke="white" strokeWidth={1} />
          <line x1={head.x - 7} y1={sy(head.y)} x2={head.x + 7} y2={sy(head.y)} stroke="white" strokeWidth={0.6} />
          <line x1={head.x} y1={sy(head.y) - 7} x2={head.x} y2={sy(head.y) + 7} stroke="white" strokeWidth={0.6} />
        </g>
      )}
    </svg>
  );
}

export function MeshLegend({ mesh }: { mesh: BedMesh | null | undefined }) {
  if (!mesh?.probed_matrix?.length) return null;
  const values = mesh.probed_matrix.flat();
  const low = Math.min(...values);
  const high = Math.max(...values);
  return (
    <div className="flex items-center gap-2 text-xs text-muted">
      <span>Malla {mesh.profile_name ?? ""}</span>
      <span className="tabular">{low.toFixed(2)}</span>
      <span className="h-2 w-20 rounded" style={{ background: `linear-gradient(90deg, rgb(${MESH_LOW}), rgb(${MESH_HIGH}))` }} />
      <span className="tabular">+{high.toFixed(2)} mm</span>
    </div>
  );
}
