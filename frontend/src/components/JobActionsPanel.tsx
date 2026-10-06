import { useAuth } from "../hooks/useAuth";
import { API_BASE_URL } from "../services/apiClient";
import type { PrintJob, TimelineEntry } from "../types/api";

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function timelineToCsv(entries: TimelineEntry[]): string {
  const header = "layer_number,z_height_mm,has_defect,defect_classes\n";
  const rows = entries.map((e) =>
    [e.layer_number, e.z_height ?? "", e.has_defect, `"${e.defect_classes.join(";")}"`].join(","),
  );
  return header + rows.join("\n");
}

/** Left column of the job dashboard. VIMOP's equivalent panel has a video-source picker,
 * start/stop and zone calibration - none apply here (the camera and printer already run on
 * their own, and ROI calibration has no UI anywhere yet, see the report). These two actions are
 * the ones with a real, robust implementation: a client-side CSV export needs no backend change,
 * and downloading the selected layer's already-saved photo needs no canvas trickery. A composite
 * "video + boxes" screenshot was left out - see the report for why. */
export function JobActionsPanel({
  job,
  entries,
  selectedEntry,
}: {
  job: PrintJob;
  entries: TimelineEntry[];
  selectedEntry: TimelineEntry | null;
}) {
  const { token } = useAuth();

  const handleExportCsv = () => {
    const csv = timelineToCsv(entries);
    triggerDownload(new Blob([csv], { type: "text/csv" }), `job_${job.id}_timeline.csv`);
  };

  const handleDownloadPhoto = async () => {
    if (!token || !selectedEntry?.thumbnail_url) return;
    const response = await fetch(`${API_BASE_URL}${selectedEntry.thumbnail_url}?token=${encodeURIComponent(token)}`);
    if (!response.ok) return;
    triggerDownload(await response.blob(), `job_${job.id}_layer_${selectedEntry.layer_number}.jpg`);
  };

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-400">Acciones</h2>
      <div className="flex flex-col gap-2">
        <button
          onClick={handleExportCsv}
          disabled={entries.length === 0}
          className="rounded-md border border-slate-700 px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-40"
        >
          Exportar timeline (CSV)
        </button>
        <button
          onClick={handleDownloadPhoto}
          disabled={!selectedEntry?.thumbnail_url}
          className="rounded-md border border-slate-700 px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-40"
        >
          Descargar foto de la capa seleccionada
        </button>
      </div>
    </div>
  );
}
