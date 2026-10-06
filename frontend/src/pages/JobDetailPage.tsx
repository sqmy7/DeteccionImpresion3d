import { useCallback, useEffect, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { AlertBanner } from "../components/AlertBanner";
import { JobActionsPanel } from "../components/JobActionsPanel";
import { JobAlertsPanel } from "../components/JobAlertsPanel";
import { JobStatsRow } from "../components/JobStatsRow";
import { JobTopBar } from "../components/JobTopBar";
import { LayerTimeline } from "../components/LayerTimeline";
import { LiveCameraView } from "../components/LiveCameraView";
import { SelectedLayerPanel } from "../components/SelectedLayerPanel";
import { useAuth } from "../hooks/useAuth";
import { useWsEvent } from "../hooks/useWebSocket";
import { listAlerts } from "../services/alerts";
import { listCamerasForPrinter } from "../services/cameras";
import { getPrinter } from "../services/printers";
import { getJobSummary, getJobTimeline, getPrintJob, listPrintJobsForPrinter } from "../services/printJobs";
import type { AlertListItem, Camera, JobSummary, Printer, PrintJob, TimelineEntry } from "../types/api";
import type { DetectionAlertEvent, DetectionResultEvent, PrinterStatusEvent } from "../types/ws";

export function JobDetailPage() {
  const { printerId, jobId } = useParams<{ printerId: string; jobId?: string }>();
  const { token } = useAuth();
  const navigate = useNavigate();

  const [printer, setPrinter] = useState<Printer | null>(null);
  const [job, setJob] = useState<PrintJob | null>(null);
  const [noJobs, setNoJobs] = useState(false);
  const [primaryCamera, setPrimaryCamera] = useState<Camera | null>(null);
  const [summary, setSummary] = useState<JobSummary | null>(null);
  const [entries, setEntries] = useState<TimelineEntry[]>([]);
  const [alerts, setAlerts] = useState<AlertListItem[]>([]);
  const [selectedEntry, setSelectedEntry] = useState<TimelineEntry | null>(null);

  const printerIdNum = Number(printerId);

  // No jobId in the URL: resolve the printer's most recent job and redirect to it.
  useEffect(() => {
    if (!token || jobId) return;
    let cancelled = false;

    listPrintJobsForPrinter(token, printerIdNum)
      .then((jobs) => {
        if (cancelled) return;
        if (jobs.length === 0) {
          setNoJobs(true);
          return;
        }
        const latest = jobs[jobs.length - 1];
        navigate(`/printers/${printerIdNum}/jobs/${latest.id}`, { replace: true });
      })
      .catch(() => {
        if (!cancelled) setNoJobs(true);
      });

    return () => {
      cancelled = true;
    };
  }, [token, jobId, printerIdNum, navigate]);

  useEffect(() => {
    if (!token) return;
    getPrinter(token, printerIdNum)
      .then(setPrinter)
      .catch(() => {});
  }, [token, printerIdNum]);

  // Same "pick the primary, fall back to whatever exists" rule as PrinterCard's dashboard thumbnail.
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    listCamerasForPrinter(token, printerIdNum)
      .then((cameras) => {
        if (cancelled) return;
        setPrimaryCamera(cameras.find((c) => c.role === "primary" && c.is_active) ?? cameras[0] ?? null);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [token, printerIdNum]);

  useEffect(() => {
    if (!token || !jobId) return;
    let cancelled = false;
    getPrintJob(token, Number(jobId))
      .then((result) => {
        if (!cancelled) setJob(result);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [token, jobId]);

  const refetchSummary = useCallback(() => {
    if (!token || !job) return;
    getJobSummary(token, job.id)
      .then(setSummary)
      .catch(() => {});
  }, [token, job]);

  // A second fetch of the same data LayerTimeline.tsx already loads for itself, kept separate on
  // purpose: this component owns CSV export, LayerTimeline owns rendering the strip, and neither
  // has to know about the other's internal state for that.
  const refetchEntries = useCallback(() => {
    if (!token || !job) return;
    getJobTimeline(token, job.id)
      .then(setEntries)
      .catch(() => {});
  }, [token, job]);

  const refetchAlerts = useCallback(() => {
    if (!token || !job) return;
    listAlerts(token, undefined, job.id)
      .then(setAlerts)
      .catch(() => {});
  }, [token, job]);

  useEffect(() => {
    refetchSummary();
    refetchEntries();
    refetchAlerts();
  }, [refetchSummary, refetchEntries, refetchAlerts]);

  const handleDetectionResult = useCallback(
    (envelope: { data: DetectionResultEvent }) => {
      if (job && envelope.data.job_id === job.id) {
        refetchSummary();
        refetchEntries();
      }
    },
    [job, refetchSummary, refetchEntries],
  );
  useWsEvent<DetectionResultEvent>("detection.result", handleDetectionResult);

  const handleDetectionAlert = useCallback(
    (envelope: { data: DetectionAlertEvent }) => {
      if (job && envelope.data.printer_id === job.printer_id) refetchAlerts();
    },
    [job, refetchAlerts],
  );
  useWsEvent<DetectionAlertEvent>("detection.alert", handleDetectionAlert);

  // Keeps the status badge and the manual pause/resume button (JobTopBar) in sync with what
  // Klipper actually reports, instead of the one-time snapshot getPrinter fetched on mount.
  const handlePrinterStatus = useCallback(
    (envelope: { data: PrinterStatusEvent }) => {
      if (envelope.data.printer_id === printerIdNum) {
        setPrinter((prev) => (prev ? { ...prev, last_known_status: envelope.data.status } : prev));
      }
    },
    [printerIdNum],
  );
  useWsEvent<PrinterStatusEvent>("printer.status", handlePrinterStatus);

  if (!printerId || Number.isNaN(printerIdNum)) {
    return <Navigate to="/" replace />;
  }

  if (noJobs) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-400">
        Esta impresora todavía no tiene trabajos de impresión registrados.
      </div>
    );
  }

  if (!job || !printer) {
    return <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-400">Cargando...</div>;
  }

  return (
    <div className="min-h-screen bg-slate-950">
      <JobTopBar printer={printer} job={job} summary={summary} />
      <JobStatsRow summary={summary} />

      <main className="grid grid-cols-1 gap-4 p-4 sm:p-6 lg:grid-cols-[220px_minmax(0,1fr)_320px]">
        <div className="order-3 lg:order-1">
          <JobActionsPanel job={job} entries={entries} selectedEntry={selectedEntry} />
        </div>

        <div className="order-1 flex flex-col gap-4 lg:order-2">
          <AlertBanner alerts={alerts} />

          {job.status === "running" && primaryCamera ? (
            <LiveCameraView cameraId={primaryCamera.id} />
          ) : (
            <div className="flex aspect-video w-full items-center justify-center rounded-lg border border-slate-800 bg-slate-900 text-sm text-slate-500">
              {job.status === "running" ? "Sin cámara configurada" : "Trabajo finalizado - sin vista en vivo"}
            </div>
          )}

          <div>
            <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-400">Línea de tiempo de capas</h2>
            <LayerTimeline jobId={job.id} selectedLayerNumber={selectedEntry?.layer_number} onSelect={setSelectedEntry} />
          </div>
        </div>

        <div className="order-2 flex flex-col gap-4 lg:order-3">
          <SelectedLayerPanel entry={selectedEntry} />
          <JobAlertsPanel jobId={job.id} />
        </div>
      </main>
    </div>
  );
}
