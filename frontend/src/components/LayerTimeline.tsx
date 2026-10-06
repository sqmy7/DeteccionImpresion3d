import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { useWsEvent } from "../hooks/useWebSocket";
import { API_BASE_URL } from "../services/apiClient";
import { getJobTimeline } from "../services/printJobs";
import { classLabel, getLayerStatus, INFORMATIONAL_CLASSES, isInformationalClass } from "../config/defectClasses";
import type { TimelineEntry } from "../types/api";
import type { DetectionResultEvent } from "../types/ws";

export function LayerTimeline({
  jobId,
  selectedLayerNumber,
  onSelect,
}: {
  jobId: number;
  selectedLayerNumber?: number | null;
  onSelect?: (entry: TimelineEntry) => void;
}) {
  const { token } = useAuth();
  const [entries, setEntries] = useState<TimelineEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const refetch = useCallback(() => {
    if (!token) return;
    getJobTimeline(token, jobId)
      .then(setEntries)
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, [token, jobId]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  // Re-fetch (rather than patch state in place) whenever a detection.result for this job
  // arrives - the backend already aggregates has_defect across cameras and resolves the
  // thumbnail, so re-pulling the same computed shape avoids duplicating that logic here.
  const handleDetectionResult = useCallback(
    (envelope: { data: DetectionResultEvent }) => {
      if (envelope.data.job_id === jobId) refetch();
    },
    [jobId, refetch],
  );
  useWsEvent<DetectionResultEvent>("detection.result", handleDetectionResult);

  if (isLoading) {
    return <p className="text-sm text-slate-400">Cargando línea de tiempo...</p>;
  }

  if (entries.length === 0) {
    return <p className="text-sm text-slate-400">Todavía no hay capas registradas para este trabajo.</p>;
  }

  const hasInformational = entries.some((entry) => entry.defect_classes.some(isInformationalClass));

  return (
    <div className="flex flex-col gap-3">
      {hasInformational && (
        <p className="text-xs text-slate-500" data-testid="timeline-informational-legend">
          ⓘ Las clases marcadas como <span className="font-medium">informativas</span> se muestran por transparencia pero son menos
          confiables: no cuentan como defecto confirmado ni generan alertas.
        </p>
      )}
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:gap-3">
        {entries.map((entry) => (
          <LayerTimelineItem
            key={entry.layer_number}
            entry={entry}
            isSelected={selectedLayerNumber === entry.layer_number}
            onClick={onSelect ? () => onSelect(entry) : undefined}
          />
        ))}
      </div>
    </div>
  );
}

function LayerTimelineItem({
  entry,
  isSelected,
  onClick,
}: {
  entry: TimelineEntry;
  isSelected?: boolean;
  onClick?: () => void;
}) {
  const { token } = useAuth();
  const [imageFailed, setImageFailed] = useState(false);

  // ok = green, info = only low-confidence (informational) classes: dashed and neutral, not red; defect = red.
  const status = getLayerStatus(entry.has_defect, entry.defect_classes);
  const colorClasses = {
    ok: "border-emerald-500 bg-emerald-500/10",
    info: "border-dashed border-slate-600 bg-slate-900",
    defect: "border-red-500 bg-red-500/10",
  }[status];
  const showImage = entry.thumbnail_url && !imageFailed && token;

  return (
    <div
      className={`flex items-center gap-3 rounded-md border-2 p-2 sm:w-32 sm:flex-col sm:items-stretch sm:gap-1.5 ${colorClasses} ${
        onClick ? "cursor-pointer hover:brightness-95" : ""
      } ${isSelected ? "ring-2 ring-offset-1 ring-offset-slate-950 ring-sky-500" : ""}`}
      data-testid={`timeline-layer-${entry.layer_number}`}
      data-status={status}
      data-selected={isSelected || undefined}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      <div className="h-14 w-20 shrink-0 overflow-hidden rounded bg-slate-800 sm:h-16 sm:w-28">
        {showImage ? (
          <img
            src={`${API_BASE_URL}${entry.thumbnail_url}?token=${encodeURIComponent(token!)}`}
            alt={`Capa ${entry.layer_number}`}
            className="h-full w-full object-cover"
            onError={() => setImageFailed(true)}
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-[10px] text-slate-500">Sin imagen</div>
        )}
      </div>
      <div className="flex min-w-0 flex-col gap-1">
        <span className="text-xs font-medium text-slate-200">
          Capa {entry.layer_number}
          {status === "defect" && <span className="ml-1 text-red-400">⚠</span>}
          {status === "info" && <span className="ml-1 text-slate-400">ⓘ</span>}
        </span>
        {entry.defect_classes.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {entry.defect_classes.map((name) => (
              <DefectChip key={name} name={name} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function DefectChip({ name }: { name: string }) {
  if (isInformationalClass(name)) {
    return (
      <span
        className="rounded border border-dashed border-slate-600 bg-slate-900 px-1 py-0.5 text-[10px] leading-tight text-slate-400"
        title={INFORMATIONAL_CLASSES[name]}
        data-testid={`defect-chip-${name}`}
        data-informational="true"
      >
        {classLabel(name)} · informativo
      </span>
    );
  }
  return (
    <span
      className="rounded bg-red-500/15 px-1 py-0.5 text-[10px] leading-tight text-red-400"
      data-testid={`defect-chip-${name}`}
    >
      {classLabel(name)}
    </span>
  );
}
