import { Download } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { classColor, classLabel, isInformationalClass } from "../../config/defectClasses";
import { useAuth } from "../../hooks/useAuth";
import { detectionBoxes } from "../../lib/boxes";
import { formatDateTime, formatNumber, formatPercent } from "../../lib/format";
import { API_BASE_URL, freshToken } from "../../services/apiClient";
import { getLayerCapture, listDetectionsForCapture } from "../../services/layers";
import type { Detection, JobFusion, Layer, LayerCapture, LocatedDefect, TimelineEntry } from "../../types/api";
import { AnnotatedImage } from "../camera/AnnotatedImage";
import { FusionMethodNote, FusionReasons, fusionKey } from "../insights/Fusion";
import { Badge, Button, EmptyState } from "../ui";

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="text-muted">{label}</dt>
      <dd className="truncate text-right tabular text-fg">{children}</dd>
    </>
  );
}

/** One layer: its photo with the boxes the model drew, what the printer was doing when the layer
 * started, where each defect is on the bed and its combined score (model + telemetry). */
export function LayerDetail({
  entry,
  layer,
  located = [],
  fusion = null,
  jobId,
}: {
  entry: TimelineEntry | null;
  layer: Layer | null;
  located?: LocatedDefect[];
  fusion?: JobFusion | null;
  jobId: number;
}) {
  const { token } = useAuth();
  const [capture, setCapture] = useState<LayerCapture | null>(null);
  const [detections, setDetections] = useState<Detection[]>([]);

  useEffect(() => {
    setCapture(null);
    setDetections([]);
    if (!token || !entry?.capture_id) return;
    let cancelled = false;
    const captureId = entry.capture_id;
    getLayerCapture(token, captureId).then((result) => !cancelled && setCapture(result)).catch(() => {});
    listDetectionsForCapture(token, captureId).then((result) => !cancelled && setDetections(result)).catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [token, entry?.capture_id]);

  const boxes = useMemo(() => detections.flatMap(detectionBoxes), [detections]);
  const placed = located.filter((defect) => detections.some((detection) => detection.id === defect.detection_id));
  const scores = useMemo(
    () => new Map((fusion?.items ?? []).map((item) => [fusionKey(item.detection_id, item.box_index), item])),
    [fusion],
  );

  if (!entry) {
    return <EmptyState title="Ninguna capa seleccionada" description="Elige una capa en la tira de arriba." />;
  }

  const src = entry.thumbnail_url && token ? `${API_BASE_URL}${entry.thumbnail_url}?token=${encodeURIComponent(freshToken(token))}` : null;
  const snapshot = layer?.telemetry ?? null;

  const download = async () => {
    if (!src) return;
    const response = await fetch(src);
    if (!response.ok) return;
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = `trabajo_${jobId}_capa_${entry.layer_number}.jpg`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="grid gap-4 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="flex flex-col gap-2">
        <AnnotatedImage src={src} alt={`Capa ${entry.layer_number}`} boxes={boxes} />
        {src && (
          <Button size="sm" variant="ghost" icon={<Download size={14} />} onClick={download} className="self-start">
            Descargar foto
          </Button>
        )}
      </div>

      <div className="flex min-w-0 flex-col gap-4">
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-sm">
          <Fact label="Capa">{entry.layer_number}</Fact>
          <Fact label="Altura Z">{entry.z_height ? `${entry.z_height} mm` : "—"}</Fact>
          <Fact label="Foto">{capture ? formatDateTime(capture.captured_at) : "—"}</Fact>
          {snapshot && (
            <>
              <Fact label="Boquilla">
                {formatNumber(snapshot.extruder_temp, 1)} / {formatNumber(snapshot.extruder_target, 0)} °C
              </Fact>
              <Fact label="Cama">
                {formatNumber(snapshot.bed_temp, 1)} / {formatNumber(snapshot.bed_target, 0)} °C
              </Fact>
              <Fact label="Velocidad">
                {formatNumber(snapshot.velocity, 0, "mm/s")} · {formatPercent(snapshot.speed_factor)}
              </Fact>
              <Fact label="Flujo / ventilador">
                {formatPercent(snapshot.extrude_factor)} / {formatPercent(snapshot.fan_speed)}
              </Fact>
              {snapshot.z_offset != null && snapshot.z_offset !== 0 && <Fact label="Desfase Z">{formatNumber(snapshot.z_offset, 3, "mm")}</Fact>}
              {snapshot.current_object && <Fact label="Objeto en curso">{snapshot.current_object}</Fact>}
            </>
          )}
          {capture?.dominant_color_rgb && (
            <Fact label="Color dominante">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-3 w-3 rounded-full border border-line" style={{ backgroundColor: capture.dominant_color_rgb }} />
                {capture.dominant_color_rgb}
              </span>
            </Fact>
          )}
        </dl>

        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-faint">Detecciones</p>
          {boxes.length === 0 ? (
            <p className="text-sm text-ok-fg">{entry.capture_id ? "Sin defectos en esta capa." : "La capa no tiene foto."}</p>
          ) : (
            <ul className="flex flex-col gap-2.5">
              {boxes.map((box, index) => {
                const score = scores.get(fusionKey(box.detectionId, box.index));
                return (
                  <li key={index} className="flex flex-col gap-0.5">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm">
                      <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: classColor(box.className) }} />
                      <span className="text-fg">{classLabel(box.className)}</span>
                      {isInformationalClass(box.className) && <Badge>informativa</Badge>}
                      <span className="ml-auto tabular text-muted">
                        modelo {Math.round(box.confidence * 100)} %
                        {score && (
                          <>
                            {" · "}
                            <span title="Puntaje combinado con la telemetría (estimación)">
                              combinado <span className={score.score > (box.confidence ?? 0) + 0.005 ? "text-warn-fg" : "text-fg"}>{Math.round(score.score * 100)} %</span>
                            </span>
                          </>
                        )}
                      </span>
                    </div>
                    {score && <FusionReasons item={score} />}
                  </li>
                );
              })}
            </ul>
          )}
          {fusion && boxes.length > 0 && <FusionMethodNote method={fusion.method} />}
          {placed.length > 0 && (
            <p className="mt-2 text-xs text-muted">
              En la cama:{" "}
              {placed
                .map((defect) => `(${defect.x.toFixed(0)}, ${defect.y.toFixed(0)}) mm ±${defect.uncertainty_mm}${defect.object ? ` · ${defect.object}` : ""}`)
                .join(" · ")}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
