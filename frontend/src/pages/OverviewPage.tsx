import { AlertTriangle, Bell, Layers, Printer as PrinterIcon, Radio } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { EventList } from "../components/events/EventList";
import { PageHeader } from "../components/layout/PageHeader";
import { Badge, Card, EmptyState, ErrorNote, Kpi, Skeleton } from "../components/ui";
import { SnapshotFeed } from "../components/SnapshotFeed";
import { JOB_STATUS, PRINTER_STATUS } from "../config/status";
import { usePrinters } from "../context/PrintersContext";
import { useActiveAlertsCount } from "../hooks/useActiveAlertsCount";
import { useAuth } from "../hooks/useAuth";
import { useWsEvent } from "../hooks/useWebSocket";
import { formatDateTime, formatDuration, formatNumber, formatPercent } from "../lib/format";
import { jobLayer, jobTime } from "../lib/jobFacts";
import { readingAge, useLiveTelemetry } from "../lib/telemetryStore";
import { useApi } from "../lib/useApi";
import { listCamerasForPrinter } from "../services/cameras";
import { getJobSummary, listPrintJobsForPrinter } from "../services/printJobs";
import { listPrinterEvents } from "../services/telemetry";
import type { Printer, PrinterEvent } from "../types/api";
import type { PrinterEventEvent } from "../types/ws";

function ProgressBar({ value }: { value: number }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-3" role="progressbar" aria-valuenow={Math.round(value * 100)} aria-valuemin={0} aria-valuemax={100}>
      <div className="h-full rounded-full bg-accent transition-[width] duration-700" style={{ width: `${Math.min(100, value * 100)}%` }} />
    </div>
  );
}

function PrinterCard({ printer }: { printer: Printer }) {
  const cameras = useApi((token) => listCamerasForPrinter(token, printer.id), [printer.id]);
  const jobs = useApi((token) => listPrintJobsForPrinter(token, printer.id), [printer.id, printer.last_known_status]);
  const latestJob = jobs.data?.[jobs.data.length - 1] ?? null;
  const summary = useApi((token) => (latestJob ? getJobSummary(token, latestJob.id) : null), [latestJob?.id, printer.last_known_status]);
  const { latest } = useLiveTelemetry(printer.id);
  const live = latest && (readingAge(latest) ?? Infinity) < 10 ? latest : null;

  const camera = cameras.data?.find((item) => item.role === "primary" && item.is_active) ?? cameras.data?.[0] ?? null;
  const status = PRINTER_STATUS[printer.last_known_status];
  const running = latestJob?.status === "running";
  const progress = live?.progress ?? null;
  // The live layer belongs to whatever the printer is doing now; a finished job shows its own last layer.
  const layer = jobLayer({ running, liveLayer: live?.layer_number, summaryLayer: summary.data?.current_layer });
  const runningRaw = live?.extra?.["print_stats.print_duration"];
  const time = latestJob ? jobTime(latestJob, { liveRunningS: typeof runningRaw === "number" ? runningRaw : null }) : null;

  return (
    <Link
      to={`/printers/${printer.id}/live`}
      className="group flex flex-col overflow-hidden rounded-xl border border-line bg-surface transition-colors hover:border-accent/50"
    >
      <div className="relative aspect-video w-full bg-surface-2">
        {camera ? (
          <SnapshotFeed cameraId={camera.id} />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-faint">{cameras.loading ? "" : "Sin cámara configurada"}</div>
        )}
        <div className="absolute left-2 top-2">
          <Badge tone={status.tone} dot pulse={printer.last_known_status === "printing"} className="bg-canvas/80 backdrop-blur">
            {status.label}
          </Badge>
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="min-w-0">
          <h3 className="truncate font-semibold text-fg group-hover:text-accent-fg">{printer.name}</h3>
          <p className="truncate text-xs text-muted">{printer.model ?? "Modelo no especificado"}</p>
        </div>

        {latestJob ? (
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2 text-xs">
              <span className="min-w-0 truncate text-muted" title={latestJob.file_name}>
                {latestJob.file_name}
              </span>
              <Badge tone={JOB_STATUS[latestJob.status].tone}>{JOB_STATUS[latestJob.status].label}</Badge>
            </div>
            {running && progress !== null && <ProgressBar value={progress} />}
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-faint">
              <span>
                Capa {layer ?? "—"}
                {latestJob.estimated_layers ? ` / ${latestJob.estimated_layers}` : ""}
              </span>
              {running && progress !== null && <span>{formatPercent(progress)}</span>}
              <span title={time?.source === "printer" ? "Tiempo de impresión según el reloj de la impresora" : "Tiempo que PrintWatch siguió el trabajo"}>
                {formatDuration(time?.seconds)}
              </span>
              {time?.note && <span>{time.note}</span>}
              {summary.data && summary.data.layers_with_defect > 0 && (
                <span className="text-danger-fg">{summary.data.layers_with_defect} capas con defecto</span>
              )}
            </div>
          </div>
        ) : (
          <p className="text-xs text-faint">{jobs.loading ? "" : "Sin trabajos registrados."}</p>
        )}

        {live && (
          <div className="mt-auto grid grid-cols-2 gap-2 border-t border-line/70 pt-3 text-xs">
            <span className="text-muted">
              Boquilla <span className="tabular text-fg">{formatNumber(live.extruder_temp, 0)}</span>/
              {formatNumber(live.extruder_target, 0)} °C
            </span>
            <span className="text-muted">
              Cama <span className="tabular text-fg">{formatNumber(live.bed_temp, 0)}</span>/{formatNumber(live.bed_target, 0)} °C
            </span>
          </div>
        )}
      </div>
    </Link>
  );
}

function RecentActivity({ printers }: { printers: Printer[] }) {
  const { token } = useAuth();
  const [events, setEvents] = useState<PrinterEvent[] | null>(null);

  useEffect(() => {
    if (!token || printers.length === 0) return;
    let cancelled = false;
    Promise.all(printers.map((printer) => listPrinterEvents(token, printer.id, { limit: 12 }).catch(() => [])))
      .then((lists) => {
        if (cancelled) return;
        setEvents(lists.flat().sort((a, b) => b.ts.localeCompare(a.ts)).slice(0, 12));
      });
    return () => {
      cancelled = true;
    };
  }, [token, printers.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const onEvent = useCallback((envelope: { data: PrinterEventEvent }) => {
    setEvents((current) => (current ? [envelope.data, ...current.filter((item) => item.id !== envelope.data.id)].slice(0, 12) : current));
  }, []);
  useWsEvent<PrinterEventEvent>("printer.event", onEvent);

  return (
    <Card title="Actividad reciente" subtitle="Últimos eventos de todas las impresoras" padded={false}>
      {events === null ? (
        <div className="flex flex-col gap-3 p-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-10 w-full" />
          ))}
        </div>
      ) : events.length === 0 ? (
        <EmptyState title="Sin actividad todavía" description="Aquí aparecen los cambios de estado y las intervenciones." />
      ) : (
        <EventList events={events} />
      )}
    </Card>
  );
}

export function OverviewPage() {
  const { printers, loading, error } = usePrinters();
  const alerts = useActiveAlertsCount();
  const printing = printers.filter((printer) => printer.last_known_status === "printing").length;
  const attention = printers.filter((printer) => printer.last_known_status === "paused" || printer.last_known_status === "error").length;

  return (
    <>
      <PageHeader title="Panel general" subtitle={`Actualizado ${formatDateTime(new Date())} (hora de Colombia)`} />

      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label="Impresoras" value={printers.length} icon={<PrinterIcon size={14} />} />
        <Kpi label="Imprimiendo" value={printing} tone={printing ? "ok" : "neutral"} icon={<Radio size={14} />} />
        <Kpi
          label="Requieren atención"
          value={attention}
          tone={attention ? "warn" : "neutral"}
          hint="En pausa o con error"
          icon={<AlertTriangle size={14} />}
        />
        <Kpi label="Alertas sin revisar" value={alerts} tone={alerts ? "danger" : "neutral"} icon={<Bell size={14} />} />
      </div>

      {error && <ErrorNote>{error}</ErrorNote>}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div>
          {loading ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <Skeleton className="h-72" />
              <Skeleton className="h-72" />
            </div>
          ) : printers.length === 0 ? (
            <Card>
              <EmptyState icon={<Layers size={28} />} title="No hay impresoras registradas" description="Se agregan desde la API (POST /api/v1/printers)." />
            </Card>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 2xl:grid-cols-3">
              {printers.map((printer) => (
                <PrinterCard key={printer.id} printer={printer} />
              ))}
            </div>
          )}
        </div>
        <RecentActivity printers={printers} />
      </div>
    </>
  );
}
