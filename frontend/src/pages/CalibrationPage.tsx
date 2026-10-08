import { Camera as CameraIcon, Check, Crosshair, Grid3x3, RotateCcw, Undo2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import { BedMapView, BedPositionNote, bedSize, MeshLegend } from "../components/bed/BedMapView";
import { usePrinterContext } from "../components/layout/PrinterLayout";
import { Badge, Button, Card, EmptyState, ErrorNote, Segmented, Skeleton, Table, Td, Th } from "../components/ui";
import { DEFECT_CLASS_LABELS } from "../config/defectClasses";
import { useAuth } from "../hooks/useAuth";
import { countOf, formatDateTime, formatNumber, relativeAge } from "../lib/format";
import { applyHomography, isConvexInOrder, solveHomography, type Point } from "../lib/homography";
import { useLiveTelemetry } from "../lib/telemetryStore";
import { useApi } from "../lib/useApi";
import { ApiError } from "../services/apiClient";
import { createCalibration, fetchSnapshot, getBedHeatmap, getPrinterGeometry, listCalibrations, type Snapshot } from "../services/bedMap";
import { listCamerasForPrinter } from "../services/cameras";
import type { BedGeometry, Camera, CameraCalibration, MarkError } from "../types/api";

const CORNER_NAMES = ["Frente izquierda", "Frente derecha", "Fondo derecha", "Fondo izquierda"];
const STALE_FRAME_SECONDS = 10;

// The C922's diagonal field of view; mirrors DEFAULT_DIAGONAL_FOV_DEGREES in app/services/bed_map.py.
const C922_DIAGONAL_FOV_DEGREES = 78;
// A mark farther than this fraction of the bed from where the camera model puts it is flagged
// (mirrors FAR_MARK_FRACTION in app/services/bed_map.py).
const FAR_MARK_FRACTION = 0.045;

function typicalFocalPx(width: number, height: number): number {
  return Math.hypot(width, height) / 2 / Math.tan((C922_DIAGONAL_FOV_DEGREES / 2) * (Math.PI / 180));
}

const WARNINGS: Record<string, string> = {
  bed_was_moving:
    "La cama se estaba moviendo al tomar la foto: la posición de referencia puede no corresponder a la imagen. Conviene calibrar con la impresora quieta.",
  camera_not_estimated:
    "No se pudo estimar la posición de la cámara: los defectos se ubicarán sin corregir el paralaje (más error en piezas altas).",
  focal_assumed:
    "La vista es casi perpendicular a la cama: la focal se tomó del campo de visión típico de la C922 (78°) en vez de calcularse.",
  focal_fixed: "La focal se fijó con el valor conocido de la cámara (no se estimó de las marcas).",
  focal_unusual:
    "La focal que salió de las marcas está muy lejos de la típica de la C922. Puede que una marca no esté en su esquina, que la cámara use otro campo de visión, o que la placa no mida lo que se supone. Fija la focal conocida y mira qué marca no encaja.",
  mark_far_from_corner:
    "Con esa focal, una marca queda muy lejos de su esquina: el modelo de cámara no puede explicar las cuatro marcas a la vez. La marca con más error es la que conviene revisar.",
  mark_far_at_typical_focal:
    "Con la focal conocida de la C922 una marca no encajaría (ver la tabla de abajo). La que más se aleja es la primera sospechosa de estar mal puesta; si todas están bien puestas, la cámara no trabaja con ese campo de visión.",
};

const CORNER_ERROR_LABELS = ["Frente izquierda", "Frente derecha", "Fondo derecha", "Fondo izquierda"];

function bedSizeOf(calibration: CameraCalibration): number {
  const xs = calibration.bed_points.map(([x]) => x);
  const ys = calibration.bed_points.map(([, y]) => y);
  return Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
}

function MarkErrorsTable({ title, marks, farMm }: { title: string; marks: MarkError[]; farMm: number }) {
  const worst = marks.reduce((best, mark, index) => (mark.error_mm > marks[best].error_mm ? index : best), 0);
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-xs font-medium text-fg">{title}</p>
      <table className="w-full max-w-md text-xs">
        <thead>
          <tr className="text-left text-faint">
            <th className="py-0.5 pr-2 font-medium">Marca</th>
            <th className="py-0.5 pr-2 text-right font-medium">Error (px)</th>
            <th className="py-0.5 text-right font-medium">Error en la cama (mm)</th>
          </tr>
        </thead>
        <tbody>
          {marks.map((mark, index) => {
            const far = mark.error_mm > farMm;
            return (
              <tr key={index} className={far ? "text-danger-fg" : "text-muted"}>
                <td className="py-0.5 pr-2">
                  {index + 1} · {CORNER_ERROR_LABELS[index]}
                  {far && index === worst ? " (la más lejos)" : ""}
                </td>
                <td className="py-0.5 pr-2 text-right tabular">{formatNumber(mark.error_px, 1)}</td>
                <td className="py-0.5 text-right tabular">{formatNumber(mark.error_mm, 1)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const FOCAL_SOURCE_LABELS: Record<string, string> = {
  estimated: "estimada de las marcas",
  assumed: "supuesta (campo de visión de la C922)",
  fixed: "fijada por ti",
};

function describeCameraPosition(calibration: CameraCalibration): string | null {
  const position = calibration.camera_position;
  if (!position) return null;
  const [x, y, z] = position;
  const side = y < 0 ? `${formatNumber(-y / 10, 0)} cm delante del borde frontal` : `sobre la cama, a ${formatNumber(y / 10, 0)} cm del frente`;
  return `Cámara estimada a ${formatNumber(z / 10, 0)} cm de altura, ${side}, en X = ${formatNumber(x / 10, 0)} cm. Si no se parece a la posición real, revisa las marcas.`;
}

function CalibrationResult({ calibration }: { calibration: CameraCalibration }) {
  const position = describeCameraPosition(calibration);
  return (
    <div className="flex flex-col gap-2 text-sm">
      <p className="flex flex-wrap items-center gap-2 text-muted">
        <Badge tone="ok" dot>
          Calibrada
        </Badge>
        {formatDateTime(calibration.created_at)} ·{" "}
        {calibration.bed_moves_in_image ? `cama móvil, Y de referencia ${formatNumber(calibration.reference_y, 1)} mm` : "cámara solidaria a la cama"}
        {calibration.focal_px
          ? ` · focal ${formatNumber(calibration.focal_px, 0)} px${calibration.focal_source ? ` (${FOCAL_SOURCE_LABELS[calibration.focal_source]})` : ""}`
          : ""}
        {calibration.typical_focal_px ? ` · la de la C922 a esta resolución: ${formatNumber(calibration.typical_focal_px, 0)} px` : ""}
      </p>
      {position && <p className="text-muted">{position}</p>}
      {calibration.warnings
        .filter((code) => code !== "focal_fixed")
        .map((code) => (
          <p key={code} className="rounded-lg border border-warn/40 bg-warn/10 px-3 py-2 text-warn-fg">
            {WARNINGS[code] ?? code}
          </p>
        ))}
      {calibration.marks && (
        <MarkErrorsTable
          title={`Error de cada marca con la focal en uso (${formatNumber(calibration.focal_px, 0)} px)`}
          marks={calibration.marks}
          farMm={FAR_MARK_FRACTION * bedSizeOf(calibration)}
        />
      )}
      {calibration.marks_at_typical_focal && (
        <MarkErrorsTable
          title={`Error de cada marca con la focal conocida de la C922 (${formatNumber(calibration.typical_focal_px, 0)} px)`}
          marks={calibration.marks_at_typical_focal}
          farMm={FAR_MARK_FRACTION * bedSizeOf(calibration)}
        />
      )}
    </div>
  );
}

function CalibrationWizard({
  camera,
  printerId,
  geometry,
  onSaved,
}: {
  camera: Camera;
  printerId: number;
  geometry: BedGeometry | null;
  onSaved: (calibration: CameraCalibration) => void;
}) {
  const { token } = useAuth();
  const { latest } = useLiveTelemetry(printerId);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [size, setSize] = useState<{ width: number; height: number } | null>(null);
  const [points, setPoints] = useState<Point[]>([]);
  const [dragging, setDragging] = useState<number | null>(null);
  const [bedMoves, setBedMoves] = useState<"yes" | "no">("yes");
  const [referenceY, setReferenceY] = useState("");
  const [focalMode, setFocalMode] = useState<"estimate" | "c922" | "custom">("estimate");
  const [customFocal, setCustomFocal] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const { width: bedWidth, depth: bedDepth } = bedSize(geometry);
  const bedPoints: Point[] = [
    [0, 0],
    [bedWidth, 0],
    [bedWidth, bedDepth],
    [0, bedDepth],
  ];

  useEffect(() => () => {
    if (snapshot) URL.revokeObjectURL(snapshot.url);
  }, [snapshot]);

  const takeSnapshot = async () => {
    if (!token) return;
    setError(null);
    try {
      const result = await fetchSnapshot(token, camera.id);
      setSnapshot(result);
      setPoints([]);
      setSize(null);
      if (latest?.y != null) setReferenceY(latest.y.toFixed(1));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo obtener la imagen de la cámara.");
    }
  };

  const toNormalized = (event: PointerEvent<SVGSVGElement>): Point | null => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return null;
    return [
      Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)),
      Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height)),
    ];
  };

  const preview = useMemo(() => {
    if (!size || points.length !== 4 || !isConvexInOrder(points)) return null;
    const pixels = points.map(([u, v]) => [u * size.width, v * size.height] as Point);
    const h = solveHomography(bedPoints, pixels);
    if (!h) return null;
    const lines: [Point, Point][] = [];
    for (let x = 0; x <= bedWidth + 0.1; x += 20) lines.push([applyHomography(h, x, 0), applyHomography(h, x, bedDepth)]);
    for (let y = 0; y <= bedDepth + 0.1; y += 20) lines.push([applyHomography(h, 0, y), applyHomography(h, bedWidth, y)]);
    return lines;
  }, [size, points, bedWidth, bedDepth]); // eslint-disable-line react-hooks/exhaustive-deps

  const crossed = points.length === 4 && !isConvexInOrder(points);
  const typicalFocal = size ? typicalFocalPx(size.width, size.height) : null;
  const knownFocal = focalMode === "c922" ? typicalFocal : focalMode === "custom" && customFocal !== "" ? Number(customFocal) : null;
  const focalMissing = focalMode !== "estimate" && !(knownFocal && knownFocal > 0);

  const save = async () => {
    if (!token || !size || points.length !== 4) return;
    setBusy(true);
    setError(null);
    try {
      const calibration = await createCalibration(token, camera.id, {
        image_points: points,
        bed_points: bedPoints,
        image_width: size.width,
        image_height: size.height,
        bed_moves_in_image: bedMoves === "yes",
        reference_y: bedMoves === "yes" && referenceY !== "" ? Number(referenceY) : null,
        focal_px: focalMode === "estimate" ? null : knownFocal,
      });
      onSaved(calibration);
      setSnapshot(null);
      setPoints([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo guardar la calibración.");
    } finally {
      setBusy(false);
    }
  };

  if (!snapshot) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-sm text-muted">
          Con la impresora quieta (sin imprimir), toma una foto y marca las cuatro esquinas de la cama. PrintWatch solo lee la
          posición del cabezal; no le envía ninguna orden a la impresora.
        </p>
        <Button variant="primary" icon={<CameraIcon size={15} />} onClick={takeSnapshot}>
          Tomar foto para calibrar
        </Button>
        {error && <ErrorNote>{error}</ErrorNote>}
      </div>
    );
  }

  const stale = snapshot.ageSeconds !== null && snapshot.ageSeconds > STALE_FRAME_SECONDS;

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
      <div className="flex flex-col gap-2">
        {snapshot.ageSeconds === null ? (
          <p className="text-xs text-warn-fg">
            No se sabe cuándo se tomó esta imagen (reinicia el proceso de captura para que lo registre). Asegúrate de que sea la vista actual.
          </p>
        ) : stale ? (
          <p className="text-xs text-warn-fg">
            Esta imagen es de {relativeAge(snapshot.ageSeconds)}: la captura no parece estar corriendo. Calibrar sobre una imagen vieja da un mapa equivocado.
          </p>
        ) : (
          <p className="text-xs text-muted">Imagen de {relativeAge(snapshot.ageSeconds)}.</p>
        )}
        <div className="relative w-full overflow-hidden rounded-lg bg-surface-2">
          <img
            src={snapshot.url}
            alt="Foto de la cámara para calibrar"
            className="block h-auto w-full select-none"
            draggable={false}
            onLoad={(event) => setSize({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })}
          />
          {size && (
            <svg
              ref={svgRef}
              className="absolute inset-0 h-full w-full touch-none"
              viewBox={`0 0 ${size.width} ${size.height}`}
              preserveAspectRatio="none"
              onPointerDown={(event) => {
                if (points.length >= 4 || dragging !== null) return;
                const point = toNormalized(event);
                if (point) setPoints((current) => [...current, point]);
              }}
              onPointerMove={(event) => {
                if (dragging === null) return;
                const point = toNormalized(event);
                if (point) setPoints((current) => current.map((item, index) => (index === dragging ? point : item)));
              }}
              onPointerUp={() => setDragging(null)}
            >
              {preview?.map(([a, b], index) => (
                <line key={index} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="#56B4E9" strokeOpacity={0.55} strokeWidth={size.width / 600} />
              ))}
              {points.length > 1 && (
                <polyline
                  points={[...points, ...(points.length === 4 ? [points[0]] : [])].map(([u, v]) => `${u * size.width},${v * size.height}`).join(" ")}
                  fill="none"
                  stroke={crossed ? "#D55E00" : "#ffffff"}
                  strokeWidth={size.width / 450}
                />
              )}
              {points.map(([u, v], index) => (
                <g
                  key={index}
                  className="cursor-grab"
                  onPointerDown={(event) => {
                    event.stopPropagation();
                    svgRef.current?.setPointerCapture(event.pointerId);
                    setDragging(index);
                  }}
                >
                  <circle cx={u * size.width} cy={v * size.height} r={size.width / 70} fill="#0b0f17" fillOpacity={0.7} stroke="#ffffff" strokeWidth={size.width / 500} />
                  <text x={u * size.width} y={v * size.height} textAnchor="middle" dominantBaseline="central" fontSize={size.width / 70} fontWeight={700} fill="#ffffff">
                    {index + 1}
                  </text>
                </g>
              ))}
            </svg>
          )}
        </div>
      </div>

      <div className="flex min-w-0 flex-col gap-4">
        <div>
          <p className="mb-2 text-sm font-medium text-fg">Marca las esquinas en este orden</p>
          <ol className="flex flex-col gap-1.5 text-sm">
            {CORNER_NAMES.map((name, index) => (
              <li
                key={name}
                className={`flex items-center gap-2 rounded-md px-2 py-1 ${index === points.length ? "bg-accent/15 text-accent-fg" : "text-muted"}`}
              >
                <span className="flex h-5 w-5 items-center justify-center rounded-full border border-line text-xs tabular">
                  {index < points.length ? <Check size={12} /> : index + 1}
                </span>
                {name}
                <span className="ml-auto text-xs tabular text-faint">
                  ({bedPoints[index][0]}, {bedPoints[index][1]})
                </span>
              </li>
            ))}
          </ol>
          <p className="mt-2 text-xs text-faint">Puedes arrastrar los puntos para ajustarlos. La cuadrícula azul muestra cómo quedaría la cama.</p>
          <div className="mt-2 flex gap-2">
            <Button size="sm" variant="ghost" icon={<Undo2 size={14} />} onClick={() => setPoints((current) => current.slice(0, -1))} disabled={!points.length}>
              Deshacer
            </Button>
            <Button size="sm" variant="ghost" icon={<RotateCcw size={14} />} onClick={takeSnapshot}>
              Otra foto
            </Button>
          </div>
          {crossed && <p className="mt-2 text-xs text-danger-fg">Las marcas se cruzan: revisa el orden de las esquinas.</p>}
        </div>

        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium text-fg">¿La cama se mueve dentro de la imagen al imprimir?</p>
          <Segmented
            label="Movimiento de la cama"
            value={bedMoves}
            onChange={setBedMoves}
            options={[
              { value: "yes", label: "Sí: cámara fija" },
              { value: "no", label: "No: cámara sobre la cama" },
            ]}
          />
          <p className="text-xs text-faint">
            La Creality Hi mueve la cama en Y: con una cámara en un trípode o en el marco, la cama se desplaza en la imagen.
          </p>
          {bedMoves === "yes" && (
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-muted">Y del cabezal cuando se tomó la foto (mm)</span>
              <input
                type="number"
                step="0.1"
                value={referenceY}
                onChange={(event) => setReferenceY(event.target.value)}
                placeholder="sin lectura de la impresora"
                className="h-9 rounded-md border border-line bg-surface-2 px-2 text-sm tabular text-fg"
              />
              <span className="text-xs text-faint">Se toma de la última lectura en vivo; la impresora debe estar quieta.</span>
            </label>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium text-fg">Focal de la cámara</p>
          <Segmented
            label="Focal"
            value={focalMode}
            onChange={setFocalMode}
            options={[
              { value: "estimate", label: "Estimarla" },
              { value: "c922", label: typicalFocal ? `C922 (${formatNumber(typicalFocal, 0)} px)` : "C922" },
              { value: "custom", label: "Otro valor" },
            ]}
          />
          {focalMode === "custom" && (
            <input
              type="number"
              min="1"
              step="1"
              value={customFocal}
              onChange={(event) => setCustomFocal(event.target.value)}
              placeholder="focal en píxeles"
              aria-label="Focal en píxeles"
              className="h-9 rounded-md border border-line bg-surface-2 px-2 text-sm tabular text-fg"
            />
          )}
          <p className="text-xs text-faint">
            {focalMode === "estimate"
              ? "Con una sola vista de la cama, la focal sale mal si las esquinas del fondo son difíciles de ubicar. Si sale muy distinta de la de la C922, fija la conocida."
              : "La focal no se calcula: se usa tal cual y al guardar verás cuánto se aleja cada marca de su esquina. Si una queda muy lejos, esa marca está mal puesta (o la cámara no tiene ese campo de visión)."}
          </p>
        </div>

        {error && <ErrorNote>{error}</ErrorNote>}
        <Button
          variant="primary"
          icon={<Crosshair size={15} />}
          onClick={save}
          disabled={busy || points.length !== 4 || crossed || (bedMoves === "yes" && referenceY === "") || focalMissing}
        >
          {busy ? "Guardando…" : "Guardar calibración"}
        </Button>
      </div>
    </div>
  );
}

function BedDefectsCard({ printerId, geometry }: { printerId: number; geometry: BedGeometry | null }) {
  const [classes, setClasses] = useState<string[]>([]);
  const [showMesh, setShowMesh] = useState<"mesh" | "none">("mesh");
  const heatmap = useApi((token) => getBedHeatmap(token, printerId, 20, classes), [printerId, classes.join(",")]);

  const toggle = (name: string) =>
    setClasses((current) => (current.includes(name) ? current.filter((item) => item !== name) : [...current, name]));

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <Grid3x3 size={15} className="text-faint" />
          Dónde aparecen los defectos
        </span>
      }
      subtitle="Todos los trabajos de esta impresora, en celdas de 2 × 2 cm"
      actions={
        <Segmented
          label="Malla"
          value={showMesh}
          onChange={setShowMesh}
          options={[
            { value: "mesh", label: "Con malla" },
            { value: "none", label: "Sin malla" },
          ]}
        />
      }
    >
      <div className="mb-3 flex flex-wrap gap-1.5">
        {Object.entries(DEFECT_CLASS_LABELS).map(([name, label]) => (
          <button
            key={name}
            onClick={() => toggle(name)}
            aria-pressed={classes.includes(name)}
            className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${
              classes.includes(name) ? "border-accent bg-accent/15 text-accent-fg" : "border-line text-muted hover:text-fg"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      {heatmap.loading && !heatmap.data ? (
        <Skeleton className="aspect-square w-full" />
      ) : heatmap.data ? (
        <>
          <BedMapView
            geometry={{
              axis_minimum: geometry?.axis_minimum ?? null,
              axis_maximum: [heatmap.data.width_mm, heatmap.data.depth_mm],
              bed_mesh: heatmap.data.bed_mesh ?? geometry?.bed_mesh ?? null,
              objects: [],
            }}
            heatmap={{ cellMm: heatmap.data.cell_mm, counts: heatmap.data.counts }}
            showMesh={showMesh === "mesh"}
          />
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-muted">
              {countOf(heatmap.data.located, "defecto ubicado", "defectos ubicados")} en {countOf(heatmap.data.jobs, "trabajo")} ·{" "}
              {countOf(heatmap.data.unreliable, "poco confiable", "poco confiables")} (no se cuentan) · {heatmap.data.skipped_boxes} sin ubicar
            </p>
            {showMesh === "mesh" && <MeshLegend mesh={heatmap.data.bed_mesh} />}
          </div>
          <BedPositionNote className="mt-3" />
        </>
      ) : (
        <ErrorNote>{heatmap.error}</ErrorNote>
      )}
    </Card>
  );
}

export function CalibrationPage() {
  const { printer } = usePrinterContext();
  const { user } = useAuth();
  const cameras = useApi((token) => listCamerasForPrinter(token, printer.id), [printer.id]);
  const geometry = useApi((token) => getPrinterGeometry(token, printer.id).catch(() => null), [printer.id]);
  const [cameraId, setCameraId] = useState<number | null>(null);
  const camera = cameras.data?.find((item) => item.id === cameraId) ?? cameras.data?.[0] ?? null;
  const calibrations = useApi((token) => (camera ? listCalibrations(token, camera.id) : null), [camera?.id]);
  const [wizardOpen, setWizardOpen] = useState(false);
  const latest = calibrations.data?.[0] ?? null;

  if (cameras.loading && !cameras.data) return <Skeleton className="h-96 w-full" />;

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
      <div className="flex min-w-0 flex-col gap-4">
        <Card
          title="Calibración de la cámara"
          subtitle="Para ubicar en la cama, en milímetros, cada defecto que el modelo encuentra en la foto"
          actions={
            cameras.data && cameras.data.length > 1 ? (
              <select
                value={camera?.id ?? ""}
                onChange={(event) => setCameraId(Number(event.target.value))}
                className="h-8 rounded-md border border-line bg-surface-2 px-2 text-xs text-fg"
                aria-label="Cámara"
              >
                {cameras.data.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            ) : undefined
          }
        >
          {!camera ? (
            <EmptyState title="Esta impresora no tiene cámaras" />
          ) : (
            <div className="flex min-w-0 flex-col gap-4">
              {latest ? (
                <CalibrationResult calibration={latest} />
              ) : (
                <p className="text-sm text-warn-fg">La cámara {camera.name} no está calibrada: los defectos no se pueden ubicar en la cama.</p>
              )}
              {user?.role === "admin" &&
                (wizardOpen ? (
                  <CalibrationWizard
                    camera={camera}
                    printerId={printer.id}
                    geometry={geometry.data}
                    onSaved={(calibration) => {
                      setWizardOpen(false);
                      calibrations.setData((current) => [calibration, ...(current ?? [])]);
                    }}
                  />
                ) : (
                  <Button className="self-start" icon={<Crosshair size={15} />} onClick={() => setWizardOpen(true)}>
                    {latest ? "Recalibrar" : "Calibrar"}
                  </Button>
                ))}
            </div>
          )}
        </Card>

        {calibrations.data && calibrations.data.length > 0 && (
          <Card title="Historial de calibraciones" subtitle="Cada detección se ubica con la calibración vigente cuando se capturó" padded={false}>
            <Table>
              <thead>
                <tr>
                  <Th>Fecha</Th>
                  <Th>Montaje</Th>
                  <Th>Y ref.</Th>
                  <Th>Focal</Th>
                  <Th>Cámara estimada (cm)</Th>
                </tr>
              </thead>
              <tbody>
                {calibrations.data.map((item) => (
                  <tr key={item.id}>
                    <Td className="whitespace-nowrap tabular">{formatDateTime(item.created_at)}</Td>
                    <Td>{item.bed_moves_in_image ? "Fija (cama móvil)" : "Sobre la cama"}</Td>
                    <Td className="tabular">{formatNumber(item.reference_y, 1)}</Td>
                    <Td className="tabular">{formatNumber(item.focal_px, 0)}</Td>
                    <Td className="whitespace-nowrap tabular">
                      {item.camera_position ? item.camera_position.map((value) => formatNumber(value / 10, 0)).join(", ") : "—"}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>
        )}
      </div>

      <BedDefectsCard printerId={printer.id} geometry={geometry.data} />
    </div>
  );
}
