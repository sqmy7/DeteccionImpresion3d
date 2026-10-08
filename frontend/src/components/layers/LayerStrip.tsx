import { classLabel, getLayerStatus } from "../../config/defectClasses";
import type { TimelineEntry } from "../../types/api";

const STATUS_STYLES = {
  ok: "bg-ok/70 hover:bg-ok",
  info: "bg-faint/60 hover:bg-faint",
  defect: "bg-danger hover:bg-danger-fg",
  missing: "bg-surface-3 hover:bg-line",
};

/** Every layer as a thin block colored by what the model saw; scales to hundreds of layers.
 * The legend repeats the meaning in words, so color is not the only cue. */
export function LayerStrip({
  entries,
  selected,
  onSelect,
  upTo,
}: {
  entries: TimelineEntry[];
  selected: number | null;
  onSelect: (layerNumber: number) => void;
  upTo?: number | null; // replay: layers after this one are dimmed
}) {
  const counts = { ok: 0, info: 0, defect: 0, missing: 0 };
  for (const entry of entries) {
    counts[entry.capture_id ? getLayerStatus(entry.has_defect, entry.defect_classes) : "missing"] += 1;
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm bg-ok/70" /> Sin defecto · {counts.ok}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm bg-danger" /> Con defecto · {counts.defect}
        </span>
        {counts.info > 0 && (
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-faint/60" /> Solo clases informativas · {counts.info}
          </span>
        )}
        {counts.missing > 0 && (
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-surface-3" /> Sin foto · {counts.missing}
          </span>
        )}
      </div>
      <div className="flex h-9 items-stretch gap-px overflow-x-auto rounded-md bg-surface-2 p-1" role="listbox" aria-label="Capas">
        {entries.map((entry) => {
          const status = entry.capture_id ? getLayerStatus(entry.has_defect, entry.defect_classes) : "missing";
          const isSelected = entry.layer_number === selected;
          const dimmed = upTo != null && entry.layer_number > upTo;
          const classes = entry.defect_classes.map(classLabel).join(", ");
          return (
            <button
              key={entry.layer_number}
              role="option"
              aria-selected={isSelected}
              title={`Capa ${entry.layer_number}${entry.z_height ? ` · Z ${entry.z_height} mm` : ""}${classes ? ` · ${classes}` : ""}`}
              onClick={() => onSelect(entry.layer_number)}
              className={`min-w-[3px] max-w-[14px] flex-1 rounded-[2px] transition-colors ${STATUS_STYLES[status]} ${
                isSelected ? "outline outline-2 outline-offset-1 outline-white" : ""
              } ${dimmed ? "opacity-25" : ""}`}
            />
          );
        })}
      </div>
    </div>
  );
}
