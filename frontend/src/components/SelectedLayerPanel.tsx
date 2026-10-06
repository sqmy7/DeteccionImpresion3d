import { useEffect, useState } from "react";
import { classColor, classLabel } from "../config/defectClasses";
import { useAuth } from "../hooks/useAuth";
import { getLayerCapture, listDetectionsForCapture } from "../services/layers";
import { API_BASE_URL } from "../services/apiClient";
import type { Detection, LayerCapture, TimelineEntry } from "../types/api";

export function SelectedLayerPanel({ entry }: { entry: TimelineEntry | null }) {
  const { token } = useAuth();
  const [capture, setCapture] = useState<LayerCapture | null>(null);
  const [detections, setDetections] = useState<Detection[]>([]);

  useEffect(() => {
    setCapture(null);
    setDetections([]);
    if (!token || !entry?.capture_id) return;
    let cancelled = false;
    const captureId = entry.capture_id;

    getLayerCapture(token, captureId)
      .then((result) => !cancelled && setCapture(result))
      .catch(() => {});
    listDetectionsForCapture(token, captureId)
      .then((result) => !cancelled && setDetections(result))
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [token, entry?.capture_id]);

  if (!entry) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
        <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-slate-400">Capa seleccionada</h2>
        <p className="text-sm text-slate-500">Hacé clic en una capa de la línea de tiempo para ver el detalle.</p>
      </div>
    );
  }

  const boxes = detections.flatMap((d) => d.raw_output?.detections ?? []);

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-400">Capa seleccionada</h2>

      <div className="mb-3 aspect-video w-full overflow-hidden rounded-md bg-slate-950">
        {entry.thumbnail_url && token ? (
          <img
            src={`${API_BASE_URL}${entry.thumbnail_url}?token=${encodeURIComponent(token)}`}
            alt={`Capa ${entry.layer_number}`}
            className="h-full w-full object-contain"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-slate-500">Sin imagen</div>
        )}
      </div>

      <dl className="mb-3 grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
        <dt className="text-slate-500">Capa</dt>
        <dd className="text-slate-200">{entry.layer_number}</dd>
        <dt className="text-slate-500">Altura Z</dt>
        <dd className="text-slate-200">{entry.z_height ? `${entry.z_height} mm` : "—"}</dd>
        <dt className="text-slate-500">Capturada</dt>
        <dd className="text-slate-200">{capture ? new Date(capture.captured_at).toLocaleTimeString() : "—"}</dd>
        <dt className="text-slate-500">Color dominante</dt>
        <dd className="flex items-center gap-1.5 text-slate-200">
          {capture?.dominant_color_rgb ? (
            <>
              <span
                className="h-3 w-3 rounded-full border border-slate-700"
                style={{ backgroundColor: capture.dominant_color_rgb }}
              />
              {capture.dominant_color_rgb}
            </>
          ) : (
            "—"
          )}
        </dd>
      </dl>

      <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">Detecciones</p>
      {boxes.length === 0 ? (
        <p className="text-sm text-emerald-400">Sin defectos detectados en esta capa.</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {boxes.map((box, i) => (
            <li key={i} className="flex items-center gap-2 text-sm">
              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: classColor(box.class) }} />
              <span className="text-slate-200">{classLabel(box.class)}</span>
              <span className="text-slate-500">{box.confidence.toFixed(2)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
