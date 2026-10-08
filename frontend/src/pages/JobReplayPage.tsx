import { Download, FileDown, FileText, MapPin, Pause, Play, ScrollText, SkipBack } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useParams, useSearchParams } from "react-router-dom";
import { BedMapView, BedPositionNote, MeshLegend } from "../components/bed/BedMapView";
import { EventList } from "../components/events/EventList";
import { JobAlertsPanel } from "../components/JobAlertsPanel";
import { LayerDetail } from "../components/layers/LayerDetail";
import { LayerStrip } from "../components/layers/LayerStrip";
import { usePrinterContext } from "../components/layout/PrinterLayout";
import { LiveKpis } from "../components/telemetry/LiveKpis";
import { TelemetryPanel } from "../components/telemetry/TelemetryPanel";
import { Badge, Button, Card, EmptyState, ErrorNote, Kpi, Segmented, Skeleton } from "../components/ui";
import { JOB_STATUS } from "../config/status";
import { formatDateTime, formatDuration, formatTime } from "../lib/format";
import { defectMarkers, eventMarkers } from "../lib/markers";
import { useApi } from "../lib/useApi";
import { getJobBedMap } from "../services/bedMap";
import { downloadJobReport, getJobCost, getJobFusion } from "../services/insights";
import { JobCostCard } from "../components/insights/CostCard";
import { useAuth } from "../hooks/useAuth";
import { getJobSummary, getJobTimeline, getPrintJob } from "../services/printJobs";
import { getJobTelemetry, listJobEvents, listJobLayers } from "../services/telemetry";
import type { TimelineEntry } from "../types/api";

type Speed = "10" | "60" | "300";
const TICK_MS = 100;

/** Index of the last item whose time is <= t (items sorted by time), or -1. */
function lastAtOrBefore(times: number[], t: number): number {
  let low = 0;
  let high = times.length - 1;
  let found = -1;
  while (low <= high) {
    const middle = (low + high) >> 1;
    if (times[middle] <= t) {
      found = middle;
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }
  return found;
}

function timelineCsv(entries: TimelineEntry[]): string {
  const rows = entries.map((entry) => [entry.layer_number, entry.z_height ?? "", entry.has_defect, `"${entry.defect_classes.join(";")}"`].join(","));
  return ["capa,z_mm,con_defecto,clases", ...rows].join("\n");
}

export function JobReplayPage() {
  const { printer } = usePrinterContext();
  const { jobId: jobIdParam } = useParams<{ jobId: string }>();
  const jobId = Number(jobIdParam);
  // ?capa=N opens the replay at that layer (links from the alerts).
  const [searchParams] = useSearchParams();
  const initialLayer = Number(searchParams.get("capa")) || null;

  const job = useApi((token) => getPrintJob(token, jobId), [jobId]);
  const summary = useApi((token) => getJobSummary(token, jobId), [jobId]);
  const timeline = useApi((token) => getJobTimeline(token, jobId), [jobId]);
  const layers = useApi((token) => listJobLayers(token, jobId), [jobId]);
  const telemetry = useApi((token) => getJobTelemetry(token, jobId, 1500), [jobId]);
  const events = useApi((token) => listJobEvents(token, jobId), [jobId]);
  const bedMap = useApi((token) => getJobBedMap(token, jobId), [jobId]);
  const fusion = useApi((token) => getJobFusion(token, jobId), [jobId]);
  const [costVersion, setCostVersion] = useState(0);
  const cost = useApi((token) => getJobCost(token, jobId), [jobId, costVersion]);
  const { token } = useAuth();
  const [reportBusy, setReportBusy] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);

  const start = job.data ? Date.parse(job.data.started_at) : 0;
  const end = job.data ? (job.data.ended_at ? Date.parse(job.data.ended_at) : Date.now()) : 0;
  const [t, setT] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<Speed>("60");

  useEffect(() => {
    if (!job.data || t !== null) return;
    if (initialLayer !== null && !layers.data && !layers.error) return; // wait to start at that layer
    const layer = initialLayer !== null ? layers.data?.find((item) => item.layer_number === initialLayer) : undefined;
    setT(layer ? Date.parse(layer.detected_at) : end);
  }, [job.data, end, t, initialLayer, layers.data, layers.error]);

  useEffect(() => {
    if (!playing) return;
    const interval = window.setInterval(() => {
      setT((current) => {
        const next = (current ?? start) + TICK_MS * Number(speed);
        if (next >= end) {
          setPlaying(false);
          return end;
        }
        return next;
      });
    }, TICK_MS);
    return () => window.clearInterval(interval);
  }, [playing, speed, start, end]);

  const sortedLayers = useMemo(() => [...(layers.data ?? [])].sort((a, b) => Date.parse(a.detected_at) - Date.parse(b.detected_at)), [layers.data]);
  const layerTimes = useMemo(() => sortedLayers.map((layer) => Date.parse(layer.detected_at)), [sortedLayers]);
  const points = useMemo(() => telemetry.data?.points ?? [], [telemetry.data]);
  const pointTimes = useMemo(() => points.map((point) => Date.parse(point.ts)), [points]);
  const entries = timeline.data ?? [];
  const allEvents = useMemo(() => [...(events.data ?? [])].sort((a, b) => Date.parse(b.ts) - Date.parse(a.ts)), [events.data]);

  const now = t ?? end;
  const layerIndex = lastAtOrBefore(layerTimes, now);
  const currentLayer = layerIndex >= 0 ? sortedLayers[layerIndex] : null;
  const pointIndex = lastAtOrBefore(pointTimes, now);
  const point = pointIndex >= 0 ? points[pointIndex] : null;
  const path = useMemo(
    () =>
      points
        .slice(0, pointIndex + 1)
        .filter((item) => item.x != null && item.y != null)
        .map((item) => [item.x as number, item.y as number] as [number, number]),
    [points, pointIndex],
  );
  const visibleDefects = (bedMap.data?.defects ?? []).filter((defect) => currentLayer && defect.layer_number <= currentLayer.layer_number);
  const pastEvents = allEvents.filter((event) => Date.parse(event.ts) <= now);
  const markers = useMemo(() => [...eventMarkers(allEvents), ...defectMarkers(layers.data ?? [], entries)], [allEvents, layers.data, entries]);

  if (!Number.isFinite(jobId)) return <Navigate to={`/printers/${printer.id}/jobs`} replace />;
  if (job.error) return <ErrorNote>{job.error}</ErrorNote>;
  if (!job.data) return <Skeleton className="h-96 w-full" />;
  if (job.data.printer_id !== printer.id) return <Navigate to={`/printers/${job.data.printer_id}/jobs/${job.data.id}`} replace />;

  const status = JOB_STATUS[job.data.status];
  const seekToLayer = (layerNumber: number) => {
    const layer = sortedLayers.find((item) => item.layer_number === layerNumber);
    if (layer) {
      setPlaying(false);
      setT(Date.parse(layer.detected_at));
    }
  };
  const estimatedTime = bedMap.data?.geometry?.file?.estimated_time;
  const downloadReport = async () => {
    if (!token) return;
    setReportBusy(true);
    setReportError(null);
    try {
      await downloadJobReport(token, jobId);
    } catch {
      setReportError("No se pudo generar el reporte. Intenta de nuevo.");
    } finally {
      setReportBusy(false);
    }
  };
  const exportCsv = () => {
    const url = URL.createObjectURL(new Blob([timelineCsv(entries)], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `trabajo_${jobId}_capas.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col gap-4">
      <Card
        title={
          <span className="flex flex-wrap items-center gap-2">
            <FileText size={15} className="text-faint" />
            <span className="truncate">{job.data.file_name}</span>
            <Badge tone={status.tone}>{status.label}</Badge>
          </span>
        }
        subtitle={`Trabajo #${job.data.id} · ${formatDateTime(job.data.started_at)} → ${job.data.ended_at ? formatDateTime(job.data.ended_at) : "en curso"}`}
        actions={
          <>
            <Button size="sm" icon={<FileDown size={14} />} onClick={downloadReport} disabled={reportBusy}>
              {reportBusy ? "Generando…" : "Reporte (PDF)"}
            </Button>
            <Button size="sm" icon={<Download size={14} />} onClick={exportCsv} disabled={entries.length === 0}>
              Capas (CSV)
            </Button>
          </>
        }
      >
        {reportError && <ErrorNote>{reportError}</ErrorNote>}
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Kpi
            label="Duración"
            value={formatDuration((end - start) / 1000)}
            hint={estimatedTime ? `laminador: ${formatDuration(estimatedTime)}` : undefined}
          />
          <Kpi label="Capas registradas" value={summary.data?.total_layers_recorded ?? "—"} hint={job.data.estimated_layers ? `de ${job.data.estimated_layers}` : undefined} />
          <Kpi label="Capas con defecto" value={summary.data?.layers_with_defect ?? "—"} tone={summary.data?.layers_with_defect ? "danger" : "ok"} />
          <Kpi label="Eventos en la bitácora" value={allEvents.length} />
        </div>
      </Card>

      <div className="sticky top-14 z-10 rounded-xl border border-line bg-surface/95 p-3 backdrop-blur lg:top-2">
        <div className="flex flex-wrap items-center gap-3">
          <Button size="sm" variant="primary" icon={playing ? <Pause size={14} /> : <Play size={14} />} onClick={() => {
            if (!playing && now >= end) setT(start);
            setPlaying((value) => !value);
          }}>
            {playing ? "Pausar" : "Reproducir"}
          </Button>
          <Button size="sm" variant="ghost" icon={<SkipBack size={14} />} onClick={() => { setPlaying(false); setT(start); }} aria-label="Ir al inicio" />
          <Segmented label="Velocidad" value={speed} onChange={setSpeed} options={[{ value: "10", label: "×10" }, { value: "60", label: "×60" }, { value: "300", label: "×300" }]} />
          <span className="ml-auto text-sm tabular text-fg">{formatTime(now)}</span>
          <span className="text-xs tabular text-muted">+{formatDuration((now - start) / 1000)}</span>
          {currentLayer && <Badge tone="accent">Capa {currentLayer.layer_number}</Badge>}
        </div>
        <input
          type="range"
          min={start}
          max={end}
          step={1000}
          value={now}
          onChange={(event) => {
            setPlaying(false);
            setT(Number(event.target.value));
          }}
          className="mt-3 w-full accent-[rgb(var(--accent))]"
          aria-label="Momento de la impresión"
        />
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <Card title={currentLayer ? `Capa ${currentLayer.layer_number} en ese momento` : "Antes de la primera capa"}>
          {entries.length === 0 ? (
            <EmptyState title="Sin capas registradas" />
          ) : (
            <div className="flex flex-col gap-4">
              <LayerStrip entries={entries} selected={currentLayer?.layer_number ?? null} upTo={currentLayer?.layer_number ?? 0} onSelect={seekToLayer} />
              <LayerDetail
                entry={entries.find((entry) => entry.layer_number === currentLayer?.layer_number) ?? null}
                layer={currentLayer}
                located={bedMap.data?.defects}
                fusion={fusion.data}
                jobId={jobId}
              />
            </div>
          )}
        </Card>

        <div className="flex flex-col gap-4">
          <Card
            title={
              <span className="flex items-center gap-2">
                <MapPin size={15} className="text-faint" />
                Cama en ese momento
              </span>
            }
            subtitle={bedMap.data?.calibrated_cameras.length ? "Recorrido del cabezal y defectos hasta ese instante" : "Recorrido del cabezal (cámara sin calibrar: sin defectos ubicados)"}
            actions={<MeshLegend mesh={bedMap.data?.geometry?.bed_mesh} />}
          >
            <BedMapView geometry={bedMap.data?.geometry} defects={visibleDefects} head={point} path={path} />
            {bedMap.data && bedMap.data.skipped_boxes > 0 && (
              <p className="mt-2 text-xs text-faint">
                {bedMap.data.skipped_boxes} recuadros no se pudieron ubicar (cámara sin calibrar o formato antiguo).
              </p>
            )}
            <BedPositionNote className="mt-3" />
          </Card>
          {point ? (
            <LiveKpis values={point} />
          ) : (
            <Card>
              <EmptyState
                title="Sin telemetría para este momento"
                description="La telemetría se guarda para los trabajos posteriores a la activación de esa función."
              />
            </Card>
          )}
        </div>
      </div>

      <TelemetryPanel
        points={points}
        markers={markers}
        cursor={now}
        onSeek={(value) => {
          setPlaying(false);
          setT(value);
        }}
        domain={[start, end]}
        subtitle="Haz clic en la gráfica para ir a ese momento"
      />

      <div className="grid items-start gap-4 lg:grid-cols-2">
        <Card
          title={
            <span className="flex items-center gap-2">
              <ScrollText size={15} className="text-faint" />
              Bitácora hasta ese momento
            </span>
          }
          actions={
            <Link to={`/printers/${printer.id}/logbook`} className="text-xs text-accent-fg hover:underline">
              Ver toda la bitácora
            </Link>
          }
          padded={false}
        >
          {pastEvents.length === 0 ? (
            <EmptyState title="Sin eventos hasta aquí" />
          ) : (
            <div className="max-h-[28rem] overflow-y-auto">
              <EventList events={pastEvents} showJob={false} />
            </div>
          )}
        </Card>
        <div className="flex flex-col gap-4">
          <JobAlertsPanel jobId={jobId} />
          {cost.data && <JobCostCard cost={cost.data} onChanged={() => setCostVersion((value) => value + 1)} />}
        </div>
      </div>
    </div>
  );
}
