import { ArrowLeft, Clock, FileDown, Gauge, Layers, Play, ShieldCheck, ShieldX, Timer } from "lucide-react";
import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AnnotatedImage } from "../components/camera/AnnotatedImage";
import { CancelPrintButton } from "../components/CancelPrintButton";
import { EventList } from "../components/events/EventList";
import { usePrinterContext } from "../components/layout/PrinterLayout";
import { LiveKpis } from "../components/telemetry/LiveKpis";
import { Badge, Button, Card, EmptyState, ErrorNote, Kpi, Segmented, Skeleton } from "../components/ui";
import { classLabel } from "../config/defectClasses";
import { PRINTER_STATUS } from "../config/status";
import { useAuth } from "../hooks/useAuth";
import { useWsEvent } from "../hooks/useWebSocket";
import { bySlicer } from "../lib/eta";
import { formatDateTime, formatDuration, formatNumber, formatPercent } from "../lib/format";
import {
  canCancel,
  canResume,
  incidentClassLabel,
  isAbortable,
  LABEL_INFO,
  milestones,
  needsAttention,
  REASON_LABELS,
  statusExplanation,
  STATUS_INFO,
} from "../lib/incidentView";
import { useApi } from "../lib/useApi";
import { ApiError } from "../services/apiClient";
import { dismissIncident, getIncident, incidentImageUrl, labelIncident } from "../services/incidents";
import { downloadJobReport } from "../services/insights";
import { abortAutoPause } from "../services/printJobs";
import { resumePrinter } from "../services/printers";
import type { IncidentDetail, IncidentLabel, TelemetryValues } from "../types/api";

type SnapshotView = "opened" | "paused";

/** What one printer reading says about time: printed (the printer's own clock) and left (slicer's estimate). */
function timing(values: (TelemetryValues & { ts: string }) | null, estimatedTotalS: number | null): { printed: number | null; remaining: number | null } {
  const raw = values?.extra?.["print_stats.print_duration"];
  const printed = typeof raw === "number" ? raw : null;
  return { printed, remaining: bySlicer(estimatedTotalS, printed) };
}

function ActionError({ message }: { message: string | null }) {
  return message ? (
    <p role="alert" className="text-sm text-danger-fg">
      {message}
    </p>
  ) : null;
}

export function IncidentPage() {
  const { incidentId } = useParams<{ incidentId: string }>();
  const id = Number(incidentId);
  const { printer } = usePrinterContext();
  const { token, user } = useAuth();
  const isAdmin = user?.role === "admin";
  const incident = useApi((accessToken) => (Number.isFinite(id) ? getIncident(accessToken, id) : null), [id]);
  const [layer, setLayer] = useState<number | null>(null);
  const [view, setView] = useState<SnapshotView>("opened");
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const reloadTimer = useRef<number | undefined>(undefined);

  // The incident changes while it is open (pause confirmed, decision, new events): follow it, at most once a second.
  const refresh = () => {
    window.clearTimeout(reloadTimer.current);
    reloadTimer.current = window.setTimeout(() => incident.reload(), 700);
  };
  useWsEvent<{ incident_id: number }>("incident.updated", (envelope) => {
    if (envelope.data.incident_id === id) refresh();
  });
  // The WebSocket handler is registered once, so it reads the job from a ref instead of a stale closure.
  const jobId = useRef<number | null>(null);
  jobId.current = incident.data?.print_job_id ?? null;
  useWsEvent<{ print_job_id: number | null }>("printer.event", (envelope) => {
    if (jobId.current !== null && envelope.data.print_job_id === jobId.current) refresh();
  });

  if (!Number.isFinite(id)) return <EmptyState title="Incidente no encontrado" />;
  if (incident.loading && !incident.data) return <Skeleton className="h-96 w-full" />;
  if (!incident.data) return <ErrorNote>{incident.error ?? "No se pudo cargar el incidente."}</ErrorNote>;

  const data: IncidentDetail = incident.data;
  const status = STATUS_INFO[data.status];
  const detections = data.detections;
  const selected = detections.find((item) => item.layer_number === layer) ?? detections[detections.length - 1] ?? null;
  const snapshot = data.telemetry_snapshot;
  const estimatedTotal = snapshot?.estimated_total_s ?? null;
  const shown = view === "paused" && data.telemetry_at_pause ? data.telemetry_at_pause : snapshot?.sample ?? null;
  const times = view === "paused" && data.telemetry_at_pause ? timing(data.telemetry_at_pause, estimatedTotal) : { printed: snapshot?.printed_s ?? null, remaining: snapshot?.remaining_s ?? null };
  const steps = milestones(data);
  const printerStatus = printer.last_known_status;
  const labelInfo = LABEL_INFO[data.label];

  const run = async (name: string, action: () => Promise<unknown>) => {
    if (!token || busy) return;
    setBusy(name);
    setActionError(null);
    try {
      await action();
      incident.reload();
    } catch (error) {
      setActionError(error instanceof ApiError ? error.message : "No se pudo completar la acción.");
    } finally {
      setBusy(null);
    }
  };

  const resume = () => {
    if (!window.confirm("¿Reanudar la impresión ahora? Verifica primero que la pieza y el cabezal estén bien.")) return;
    void run("resume", () => resumePrinter(token!, printer.id));
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Link to={`/printers/${printer.id}/incidents`} className="flex w-fit items-center gap-1.5 text-xs text-muted hover:text-fg">
          <ArrowLeft size={14} /> Incidentes
        </Link>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <h1 className="text-lg font-semibold text-fg">
            Incidente #{data.id} · {incidentClassLabel(data.defect_class, classLabel)}
          </h1>
          <Badge tone={status.tone} dot pulse={needsAttention(data)}>
            {status.label}
          </Badge>
          <Badge tone="accent">{REASON_LABELS[data.reason]}</Badge>
          {data.mode && <Badge tone="neutral">Modo {data.mode === "warn" ? "aviso" : "automático"}</Badge>}
          <Badge tone={labelInfo.tone}>{labelInfo.label}</Badge>
        </div>
        <p className="text-sm text-muted">
          {data.job_file_name ?? "Trabajo"} ·{" "}
          <Link to={`/printers/${data.printer_id}/jobs/${data.print_job_id}`} className="text-accent-fg hover:underline">
            Trabajo #{data.print_job_id}
          </Link>{" "}
          · abierto {formatDateTime(data.opened_at)}
        </p>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        {/* Evidence: the layer photo with the boxes. */}
        <Card
          className="xl:row-span-2"
          title="Evidencia"
          subtitle={selected ? `Capa ${selected.layer_number}${selected.z_height != null ? ` · z ${formatNumber(selected.z_height, 2)} mm` : ""}` : "Sin detección asociada"}
          actions={
            detections.length > 1 && (
              <Segmented
                label="Capa de la racha"
                value={String(selected?.layer_number ?? "")}
                onChange={(value) => setLayer(Number(value))}
                options={detections.map((item) => ({ value: String(item.layer_number), label: `Capa ${item.layer_number}` }))}
              />
            )
          }
        >
          {selected && token ? (
            <div className="flex flex-col gap-3">
              <AnnotatedImage
                src={incidentImageUrl(token, selected.image_url)}
                alt={`Foto de la capa ${selected.layer_number}`}
                boxes={selected.boxes.map((box) => ({ className: box.class_name, confidence: box.confidence, x1: box.x1, y1: box.y1, x2: box.x2, y2: box.y2 }))}
              />
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
                <div>
                  <dt className="text-xs text-faint">Clase</dt>
                  <dd className="font-medium text-fg">{incidentClassLabel(data.defect_class, classLabel)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-faint">Confianza</dt>
                  <dd className="font-medium tabular text-fg">{selected.confidence != null ? formatPercent(selected.confidence) : "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-faint">Capa</dt>
                  <dd className="font-medium tabular text-fg">{selected.layer_number}{data.job.estimated_layers ? ` / ${data.job.estimated_layers}` : ""}</dd>
                </div>
                <div>
                  <dt className="text-xs text-faint">Hora de la foto</dt>
                  <dd className="font-medium tabular text-fg">{formatDateTime(selected.captured_at)}</dd>
                </div>
              </dl>
              {selected.boxes.length === 0 && <p className="text-xs text-muted">El modelo no dibujó cajas en esta foto.</p>}
            </div>
          ) : (
            <EmptyState
              title="Sin foto del defecto"
              description={
                data.reason === "pause"
                  ? "La impresora se pausó sin que el modelo hubiera detectado nada: no hay una foto asociada a este incidente."
                  : "No hay una detección guardada para este incidente."
              }
            />
          )}
        </Card>

        {/* Decision. */}
        <Card title="Decisión" subtitle={statusExplanation(data)}>
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
              Impresora ahora:
              <Badge tone={PRINTER_STATUS[printerStatus].tone} dot pulse={printerStatus === "printing"}>
                {PRINTER_STATUS[printerStatus].label}
              </Badge>
              {data.seconds_to_pause !== null && (
                <span className="flex items-center gap-1" title="De la primera foto con el defecto a que Klipper confirmó la pausa">
                  <Timer size={13} className="text-faint" /> a la pausa en {formatDuration(data.seconds_to_pause)}
                </span>
              )}
            </div>

            {isAdmin ? (
              <div className="flex flex-wrap items-start gap-2">
                {isAbortable(data) && (
                  <Button size="md" variant="danger" disabled={busy !== null} onClick={() => void run("abort", () => abortAutoPause(token!, data.print_job_id))}>
                    Abortar la pausa
                  </Button>
                )}
                {canResume(printerStatus, isAdmin) && (
                  <Button size="md" variant="ok" icon={<Play size={15} />} disabled={busy !== null} onClick={resume}>
                    {busy === "resume" ? "Enviando…" : "Reanudar impresión"}
                  </Button>
                )}
                {canCancel(printerStatus, isAdmin) && <CancelPrintButton printerId={printer.id} size="md" onCancelled={incident.reload} />}
                {needsAttention(data) && (
                  <Button size="md" variant="secondary" disabled={busy !== null} onClick={() => void run("dismiss", () => dismissIncident(token!, data.id))}>
                    Ignorar incidente
                  </Button>
                )}
              </div>
            ) : (
              <p className="text-xs text-muted">Solo un administrador puede reanudar, cancelar o cerrar un incidente.</p>
            )}
            <ActionError message={actionError} />

            <div className="flex flex-col gap-1.5 border-t border-line/70 pt-3">
              <p className="text-xs font-medium text-fg">¿Qué fue en realidad?</p>
              {isAdmin ? (
                <Segmented<IncidentLabel>
                  label="Etiqueta del incidente"
                  value={data.label}
                  onChange={(value) => void run("label", () => labelIncident(token!, data.id, value))}
                  options={[
                    { value: "correct", label: "Acierto: el defecto era real" },
                    { value: "false_positive", label: "Falso positivo" },
                    { value: "unlabeled", label: "Sin etiquetar" },
                  ]}
                />
              ) : (
                <span className="text-sm text-muted">{labelInfo.label}</span>
              )}
              <p className="text-xs text-faint">
                {data.label !== "unlabeled" && data.labeled_by ? `Etiquetado por ${data.labeled_by} · ${formatDateTime(data.labeled_at)}. ` : ""}
                Las etiquetas sirven para medir cuántas pausas habrían sido falsas.
              </p>
            </div>

            <div className="flex flex-wrap gap-2 border-t border-line/70 pt-3">
              <Button
                size="sm"
                variant="secondary"
                icon={<FileDown size={14} />}
                disabled={busy !== null}
                onClick={() => void run("report", () => downloadJobReport(token!, data.print_job_id))}
              >
                Reporte PDF del trabajo
              </Button>
            </div>
          </div>
        </Card>

        {/* The printer at that moment. */}
        <Card
          title="Estado de la impresora"
          subtitle={shown ? `Lectura de las ${formatDateTime(shown.ts)}` : "Sin telemetría guardada para este trabajo"}
          actions={
            data.telemetry_at_pause && (
              <Segmented<SnapshotView>
                label="Momento"
                value={view}
                onChange={setView}
                options={[
                  { value: "opened", label: "Al abrirse" },
                  { value: "paused", label: "Al pausarse" },
                ]}
              />
            )
          }
        >
          {shown ? (
            <div className="flex flex-col gap-3">
              <div className="grid grid-cols-2 gap-3">
                <Kpi label="Progreso" icon={<Gauge size={14} />} value={formatPercent(shown.progress)} hint={`Capa ${shown.layer_number ?? "—"}${data.job.estimated_layers ? ` / ${data.job.estimated_layers}` : ""}`} />
                <Kpi label="Tiempo impreso" icon={<Clock size={14} />} value={formatDuration(times.printed)} hint="Reloj de la impresora" />
                <Kpi
                  label="Tiempo restante"
                  icon={<Layers size={14} />}
                  value={times.remaining !== null ? `~${formatDuration(times.remaining)}` : "—"}
                  hint={estimatedTotal ? "Total del laminador menos lo impreso" : "El archivo no trae estimación"}
                />
              </div>
              <LiveKpis values={shown} />
            </div>
          ) : (
            <EmptyState title="Sin telemetría" description="No había muestras guardadas de este trabajo cuando se abrió el incidente." />
          )}
        </Card>

        {/* Timeline. */}
        <Card
          className="xl:col-span-2"
          title="Línea de tiempo"
          subtitle="Lo que pasó, en orden, con su origen"
          actions={
            data.chain.ok ? (
              <Badge tone="ok" title={`Hash del último evento: ${data.chain.last_hash ?? "—"}`}>
                <ShieldCheck size={12} className="mr-1 inline" />
                Cadena de eventos íntegra ({data.chain.events_checked})
              </Badge>
            ) : (
              <Badge tone="danger" title="Se borró o se cambió un evento después de registrarlo">
                <ShieldX size={12} className="mr-1 inline" />
                Cadena ROTA en el evento #{data.chain.first_broken_id}
              </Badge>
            )
          }
          padded={false}
        >
          <ol className="grid gap-x-6 gap-y-1 border-b border-line/70 px-4 py-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
            {steps.map((step) => (
              <li key={step.key} className="flex items-baseline justify-between gap-3">
                <span className="text-muted">{step.label}</span>
                <span className="tabular text-fg">
                  {formatDateTime(step.at)}
                  {step.offsetS !== null && step.offsetS !== 0 && <span className="ml-1.5 text-xs text-faint">+{formatDuration(step.offsetS)}</span>}
                </span>
              </li>
            ))}
          </ol>
          {data.events.length > 0 ? (
            <EventList events={data.events} showJob={false} />
          ) : (
            <p className="px-4 py-6 text-sm text-muted">No hay eventos de la bitácora en esta ventana.</p>
          )}
        </Card>
      </div>
    </div>
  );
}
