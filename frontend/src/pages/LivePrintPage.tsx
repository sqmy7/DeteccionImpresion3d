import { Camera, Clock, Layers, MapPin, ScrollText } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { BedMapView, MeshLegend } from "../components/bed/BedMapView";
import { EventList } from "../components/events/EventList";
import { JobAlertsPanel } from "../components/JobAlertsPanel";
import { LayerDetail } from "../components/layers/LayerDetail";
import { LayerStrip } from "../components/layers/LayerStrip";
import { usePrinterContext } from "../components/layout/PrinterLayout";
import { LiveCameraView } from "../components/LiveCameraView";
import { PrintControls } from "../components/PrintControls";
import { LiveKpis } from "../components/telemetry/LiveKpis";
import { TelemetryPanel, type TimedValues } from "../components/telemetry/TelemetryPanel";
import { Badge, Card, EmptyState, Skeleton } from "../components/ui";
import { JOB_STATUS } from "../config/status";
import { useWsEvent } from "../hooks/useWebSocket";
import { formatDateTime, formatDuration, formatPercent, secondsBetween } from "../lib/format";
import { defectMarkers, eventMarkers } from "../lib/markers";
import { readingAge, useLiveTelemetry } from "../lib/telemetryStore";
import { useApi } from "../lib/useApi";
import { getJobBedMap, getPrinterGeometry } from "../services/bedMap";
import { listCamerasForPrinter } from "../services/cameras";
import { getJobSummary, getJobTimeline, listPrintJobsForPrinter } from "../services/printJobs";
import { getJobTelemetry, listJobEvents, listJobLayers } from "../services/telemetry";
import type { JobSummary, PrintJob, PrinterEvent, TelemetryReading } from "../types/api";
import type { DetectionResultEvent, LayerCapturedEvent, PrinterEventEvent } from "../types/ws";

const TRAIL_SECONDS = 120;

function ProgressCard({
  job,
  summary,
  reading,
  printerId,
  status,
}: {
  job: PrintJob;
  summary: JobSummary | null;
  reading: TelemetryReading | null;
  printerId: number;
  status: Parameters<typeof PrintControls>[0]["status"];
}) {
  const progress = reading?.progress ?? null;
  const elapsed = secondsBetween(job.started_at, job.ended_at);
  // Rough: assumes the rest of the file prints at the average pace so far (heating included).
  const remaining = progress && progress > 0.02 && elapsed ? (elapsed * (1 - progress)) / progress : null;
  const layer = reading?.layer_number ?? summary?.current_layer ?? null;

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <span className="truncate" title={job.file_name}>
            {job.file_name}
          </span>
          <Badge tone={JOB_STATUS[job.status].tone}>{JOB_STATUS[job.status].label}</Badge>
        </span>
      }
      subtitle={`Trabajo #${job.id} · inicio ${formatDateTime(job.started_at)}`}
      actions={<PrintControls printerId={printerId} status={status} />}
    >
      <div className="flex flex-col gap-3">
        <div className="flex items-end justify-between gap-3">
          <p className="text-3xl font-semibold tabular text-fg">{formatPercent(progress)}</p>
          <p className="text-right text-sm text-muted">
            Capa <span className="tabular text-fg">{layer ?? "—"}</span>
            {job.estimated_layers ? <span className="tabular"> / {job.estimated_layers}</span> : null}
          </p>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-surface-3">
          <div className="h-full rounded-full bg-accent transition-[width] duration-700" style={{ width: `${Math.min(100, (progress ?? 0) * 100)}%` }} />
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs text-muted sm:grid-cols-3">
          <span className="flex items-center gap-1.5">
            <Clock size={13} className="text-faint" />
            {formatDuration(elapsed)}
          </span>
          <span title="Estimación: supone que lo que falta se imprime al ritmo promedio de lo hecho">
            Restan ~{formatDuration(remaining)}
          </span>
          {summary && (
            <span className={summary.layers_with_defect ? "text-danger-fg" : ""}>
              {summary.layers_with_defect} capas con defecto
            </span>
          )}
        </div>
      </div>
    </Card>
  );
}

export function LivePrintPage() {
  const { printer } = usePrinterContext();
  const [version, setVersion] = useState(0);
  const [selectedLayer, setSelectedLayer] = useState<number | null>(null);
  const [followLatest, setFollowLatest] = useState(true);
  const [liveEvents, setLiveEvents] = useState<PrinterEvent[]>([]);

  const jobs = useApi((token) => listPrintJobsForPrinter(token, printer.id), [printer.id, printer.last_known_status]);
  const job = useMemo(() => [...(jobs.data ?? [])].reverse().find((item) => item.status === "running") ?? null, [jobs.data]);
  const lastJob = jobs.data?.[jobs.data.length - 1] ?? null;
  const cameras = useApi((token) => listCamerasForPrinter(token, printer.id), [printer.id]);
  const camera = cameras.data?.find((item) => item.role === "primary" && item.is_active) ?? cameras.data?.[0] ?? null;

  const { latest, recent } = useLiveTelemetry(printer.id);
  const live = latest && (readingAge(latest) ?? Infinity) < 10 ? latest : null;

  const jobId = job?.id ?? null;
  const summary = useApi((token) => (jobId ? getJobSummary(token, jobId) : null), [jobId, version]);
  const timeline = useApi((token) => (jobId ? getJobTimeline(token, jobId) : null), [jobId, version]);
  const layers = useApi((token) => (jobId ? listJobLayers(token, jobId) : null), [jobId, version]);
  const bedMap = useApi((token) => (jobId ? getJobBedMap(token, jobId) : null), [jobId, version]);
  const history = useApi((token) => (jobId ? getJobTelemetry(token, jobId, 900) : null), [jobId]);
  const events = useApi((token) => (jobId ? listJobEvents(token, jobId) : null), [jobId]);
  const geometry = useApi((token) => getPrinterGeometry(token, printer.id), [printer.id, jobId]);

  useEffect(() => setLiveEvents([]), [jobId]);

  const refresh = useCallback(
    (envelope: { data: DetectionResultEvent | LayerCapturedEvent }) => {
      if (envelope.data.job_id === jobId) setVersion((value) => value + 1);
    },
    [jobId],
  );
  useWsEvent<DetectionResultEvent>("detection.result", refresh);
  useWsEvent<LayerCapturedEvent>("layer.captured", refresh);
  useWsEvent<PrinterEventEvent>("printer.event", (envelope) => {
    if (jobId && envelope.data.print_job_id === jobId) setLiveEvents((current) => [envelope.data, ...current]);
  });

  const entries = useMemo(() => timeline.data ?? [], [timeline.data]);
  useEffect(() => {
    if (followLatest && entries.length) setSelectedLayer(entries[entries.length - 1].layer_number);
  }, [entries, followLatest]);

  const allEvents = useMemo(() => {
    const known = new Set((events.data ?? []).map((event) => event.id));
    return [...liveEvents.filter((event) => !known.has(event.id)), ...(events.data ?? [])];
  }, [events.data, liveEvents]);

  const points = useMemo<TimedValues[]>(() => {
    const stored = history.data?.points ?? [];
    const lastStored = stored.length ? Date.parse(stored[stored.length - 1].ts) : 0;
    const fresh = recent.filter((reading) => reading.job_id === jobId && Date.parse(reading.ts) > lastStored);
    return [...stored, ...fresh];
  }, [history.data, recent, jobId]);

  const markers = useMemo(
    () => [...eventMarkers(allEvents), ...defectMarkers(layers.data ?? [], entries)],
    [allEvents, layers.data, entries],
  );

  const trail = useMemo(() => {
    const since = Date.now() - TRAIL_SECONDS * 1000;
    return recent
      .filter((reading) => Date.parse(reading.ts) >= since && reading.x != null && reading.y != null)
      .map((reading) => [reading.x as number, reading.y as number] as [number, number]);
  }, [recent]);

  const selectedEntry = entries.find((entry) => entry.layer_number === selectedLayer) ?? null;
  const selectedLayerRow = layers.data?.find((layer) => layer.layer_number === selectedLayer) ?? null;
  const mapGeometry = bedMap.data?.geometry ?? geometry.data ?? null;
  const notCalibrated = bedMap.data && bedMap.data.calibrated_cameras.length === 0;

  if (jobs.loading && !jobs.data) {
    return (
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <Skeleton className="aspect-video w-full" />
        <Skeleton className="h-80 w-full" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <Card
          title={
            <span className="flex items-center gap-2">
              <Camera size={15} className="text-faint" />
              {camera?.name ?? "Cámara"}
            </span>
          }
          subtitle="Video en vivo; los recuadros son los de la última capa analizada"
          padded={false}
        >
          <div className="p-3">
            {camera ? (
              <LiveCameraView cameraId={camera.id} />
            ) : (
              <EmptyState title="Sin cámara configurada" description="Agrega una cámara a esta impresora para ver el video y detectar defectos." />
            )}
          </div>
        </Card>

        <div className="flex flex-col gap-4">
          {job ? (
            <ProgressCard job={job} summary={summary.data} reading={live} printerId={printer.id} status={printer.last_known_status} />
          ) : (
            <Card title="Sin impresión en curso">
              <p className="text-sm text-muted">
                {lastJob ? (
                  <>
                    El último trabajo fue{" "}
                    <Link to={`/printers/${printer.id}/jobs/${lastJob.id}`} className="text-accent-fg hover:underline">
                      #{lastJob.id} {lastJob.file_name}
                    </Link>{" "}
                    ({JOB_STATUS[lastJob.status].label.toLowerCase()}, {formatDateTime(lastJob.ended_at ?? lastJob.started_at)}).
                  </>
                ) : (
                  "Esta impresora todavía no tiene trabajos."
                )}{" "}
                Un trabajo nuevo se abre solo cuando la impresora empieza a imprimir.
              </p>
            </Card>
          )}
          {live ? (
            <LiveKpis values={live} />
          ) : (
            <Card>
              <EmptyState
                title="Sin lecturas en vivo"
                description="PrintWatch no está recibiendo datos de la impresora. Revisa que esté encendida y en la misma red (y la VPN desconectada)."
              />
            </Card>
          )}
        </div>
      </div>

      {job && (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <TelemetryPanel
            points={points}
            markers={markers}
            subtitle={history.data?.bucket_seconds ? `Promedios cada ${Math.round(history.data.bucket_seconds)} s hasta hace un momento; luego segundo a segundo` : "Una muestra por segundo"}
          />
          <Card
            title={
              <span className="flex items-center gap-2">
                <MapPin size={15} className="text-faint" />
                Mapa de la cama
              </span>
            }
            subtitle="Vista superior; el frente de la cama abajo"
            actions={<MeshLegend mesh={mapGeometry?.bed_mesh} />}
          >
            <BedMapView geometry={mapGeometry} defects={bedMap.data?.defects ?? []} head={live} trail={trail} path={bedMap.data?.head_path} />
            {notCalibrated && (
              <p className="mt-2 text-xs text-warn-fg">
                La cámara no está calibrada: los defectos no se pueden ubicar en la cama.{" "}
                <Link to={`/printers/${printer.id}/camera`} className="underline">
                  Calibrar
                </Link>
              </p>
            )}
          </Card>
        </div>
      )}

      {job && (
        <Card
          title={
            <span className="flex items-center gap-2">
              <Layers size={15} className="text-faint" />
              Capas
            </span>
          }
          subtitle="Una foto y un análisis por capa"
          actions={
            <label className="flex items-center gap-2 text-xs text-muted">
              <input type="checkbox" checked={followLatest} onChange={(event) => setFollowLatest(event.target.checked)} className="accent-[rgb(var(--accent))]" />
              Seguir la última capa
            </label>
          }
        >
          {entries.length === 0 ? (
            <EmptyState title="Todavía no hay capas" description="Cada cambio de capa toma una foto y la analiza." />
          ) : (
            <div className="flex flex-col gap-4">
              <LayerStrip
                entries={entries}
                selected={selectedLayer}
                onSelect={(layerNumber) => {
                  setFollowLatest(false);
                  setSelectedLayer(layerNumber);
                }}
              />
              <LayerDetail entry={selectedEntry} layer={selectedLayerRow} located={bedMap.data?.defects} jobId={job.id} />
            </div>
          )}
        </Card>
      )}

      {job && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card
            title={
              <span className="flex items-center gap-2">
                <ScrollText size={15} className="text-faint" />
                Bitácora de este trabajo
              </span>
            }
            actions={
              <Link to={`/printers/${printer.id}/logbook`} className="text-xs text-accent-fg hover:underline">
                Ver toda la bitácora
              </Link>
            }
            padded={false}
          >
            {allEvents.length === 0 ? (
              <EmptyState title="Sin eventos todavía" />
            ) : (
              <div className="max-h-[28rem] overflow-y-auto">
                <EventList events={allEvents.slice(0, 40)} showJob={false} />
              </div>
            )}
          </Card>
          <JobAlertsPanel jobId={job.id} />
        </div>
      )}
    </div>
  );
}
