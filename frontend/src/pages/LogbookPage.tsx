import { Check, Copy, ShieldAlert, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { EventList } from "../components/events/EventList";
import { usePrinterContext } from "../components/layout/PrinterLayout";
import { Badge, Button, Card, EmptyState, ErrorNote, Segmented, Skeleton } from "../components/ui";
import { INTERVENTION_TYPES, ORIGIN_INFO } from "../config/events";
import { useAuth } from "../hooks/useAuth";
import { useWsEvent } from "../hooks/useWebSocket";
import { formatDateTime } from "../lib/format";
import { useApi } from "../lib/useApi";
import { listPrintJobsForPrinter } from "../services/printJobs";
import { listPrinterEvents, verifyPrinterEvents } from "../services/telemetry";
import type { ChainVerification, EventOrigin, PrinterEvent } from "../types/api";
import type { PrinterEventEvent } from "../types/ws";

type Group = "all" | "interventions" | "states" | "connection";

const GROUP_TYPES: Record<Group, string[] | undefined> = {
  all: undefined,
  interventions: INTERVENTION_TYPES,
  states: [
    "state_changed",
    "printwatch_command",
    "klippy_state_changed",
    "klippy_disconnected",
    "klippy_shutdown",
    "klippy_ready",
    "filament_sensor_changed",
    "gcode_error",
  ],
  connection: ["monitor_connected", "monitor_disconnected"],
};

const ORIGINS = Object.keys(ORIGIN_INFO) as EventOrigin[];
const PAGE_SIZE = 100;

function matches(event: PrinterEvent, group: Group, origins: EventOrigin[], jobId: number | null): boolean {
  const types = GROUP_TYPES[group];
  return (!types || types.includes(event.event_type)) && (origins.length === 0 || origins.includes(event.origin)) && (jobId === null || event.print_job_id === jobId);
}

function ChainCard({ printerId }: { printerId: number }) {
  const { token } = useAuth();
  const [result, setResult] = useState<ChainVerification | null>(null);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const verify = async () => {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await verifyPrinterEvents(token, printerId));
      setCheckedAt(new Date());
    } catch {
      setError("No se pudo verificar la bitácora.");
    } finally {
      setBusy(false);
    }
  };

  const copyHash = async () => {
    if (!result?.last_hash) return;
    await navigator.clipboard.writeText(result.last_hash);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  return (
    <Card title="Integridad de la bitácora" subtitle="Cadena de hashes SHA-256">
      <p className="text-sm text-muted">
        Cada evento guarda un hash que incluye el del evento anterior. Si alguien edita o borra un evento en la base de
        datos, la cadena se rompe desde ese punto.
      </p>
      <Button variant="primary" size="sm" className="mt-3" onClick={verify} disabled={busy}>
        {busy ? "Verificando…" : "Verificar integridad"}
      </Button>
      {error && <div className="mt-3"><ErrorNote>{error}</ErrorNote></div>}
      {result && (
        <div className={`mt-3 rounded-lg border p-3 text-sm ${result.ok ? "border-ok/40 bg-ok/10" : "border-danger/50 bg-danger/10"}`}>
          <p className={`flex items-center gap-2 font-medium ${result.ok ? "text-ok-fg" : "text-danger-fg"}`}>
            {result.ok ? <ShieldCheck size={16} /> : <ShieldAlert size={16} />}
            {result.ok
              ? `Íntegra: ${result.events_checked} eventos verificados`
              : `Alterada en el evento #${result.first_broken_id}`}
          </p>
          {!result.ok && (
            <p className="mt-1 text-muted">
              {result.reason === "content_changed"
                ? "El contenido de ese evento cambió después de registrarse."
                : "Falta, sobra o se reordenó un evento antes de ese."}
            </p>
          )}
          {checkedAt && <p className="mt-1 text-xs text-faint">Verificada el {formatDateTime(checkedAt)}</p>}
          {result.last_hash && (
            <div className="mt-2">
              <p className="text-xs text-faint">Último hash (guárdalo fuera de la base para detectar también una reescritura completa):</p>
              <div className="mt-1 flex items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded bg-surface-2 px-2 py-1 font-mono text-xs text-fg">{result.last_hash}</code>
                <button onClick={copyHash} aria-label="Copiar hash" className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-fg">
                  {copied ? <Check size={15} /> : <Copy size={15} />}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function OriginLegend() {
  return (
    <Card title="Qué significa cada origen">
      <ul className="flex flex-col gap-2.5">
        {ORIGINS.map((origin) => (
          <li key={origin} className="text-sm">
            <Badge tone={ORIGIN_INFO[origin].tone}>{ORIGIN_INFO[origin].label}</Badge>
            <p className="mt-1 text-xs text-muted">{ORIGIN_INFO[origin].description}</p>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function LogbookPage() {
  const { printer } = usePrinterContext();
  const { token } = useAuth();
  const [group, setGroup] = useState<Group>("all");
  const [origins, setOrigins] = useState<EventOrigin[]>([]);
  const [jobId, setJobId] = useState<number | null>(null);
  const [events, setEvents] = useState<PrinterEvent[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  const jobs = useApi((t) => listPrintJobsForPrinter(t, printer.id), [printer.id]);
  const firstPage = useApi(
    (t) =>
      listPrinterEvents(t, printer.id, {
        eventTypes: GROUP_TYPES[group],
        origins,
        jobId: jobId ?? undefined,
        limit: PAGE_SIZE,
      }),
    [printer.id, group, origins.join(","), jobId],
  );

  useEffect(() => {
    if (!firstPage.data) return;
    setEvents(firstPage.data);
    setHasMore(firstPage.data.length === PAGE_SIZE);
  }, [firstPage.data]);

  const loadMore = async () => {
    if (!token || events.length === 0) return;
    setLoadingMore(true);
    try {
      const older = await listPrinterEvents(token, printer.id, {
        eventTypes: GROUP_TYPES[group],
        origins,
        jobId: jobId ?? undefined,
        beforeId: events[events.length - 1].id,
        limit: PAGE_SIZE,
      });
      setEvents((current) => [...current, ...older]);
      setHasMore(older.length === PAGE_SIZE);
    } finally {
      setLoadingMore(false);
    }
  };

  const onLiveEvent = useCallback(
    (envelope: { data: PrinterEventEvent }) => {
      const event = envelope.data;
      if (event.printer_id !== printer.id || !matches(event, group, origins, jobId)) return;
      setEvents((current) => (current.some((item) => item.id === event.id) ? current : [event, ...current]));
    },
    [printer.id, group, origins, jobId],
  );
  useWsEvent<PrinterEventEvent>("printer.event", onLiveEvent);

  const toggleOrigin = (origin: EventOrigin) =>
    setOrigins((current) => (current.includes(origin) ? current.filter((item) => item !== origin) : [...current, origin]));

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
      <Card
        padded={false}
        title="Bitácora de eventos"
        subtitle="Estados de la impresión e intervenciones, con quién los hizo según la evidencia disponible"
        actions={
          <select
            value={jobId ?? ""}
            onChange={(event) => setJobId(event.target.value ? Number(event.target.value) : null)}
            className="h-8 max-w-[14rem] rounded-md border border-line bg-surface-2 px-2 text-xs text-fg"
            aria-label="Filtrar por trabajo"
          >
            <option value="">Todos los trabajos</option>
            {[...(jobs.data ?? [])].reverse().map((job) => (
              <option key={job.id} value={job.id}>
                #{job.id} · {job.file_name}
              </option>
            ))}
          </select>
        }
      >
        <div className="flex flex-col gap-3 border-b border-line/70 px-4 py-3">
          <Segmented
            label="Tipo de evento"
            value={group}
            onChange={setGroup}
            options={[
              { value: "all", label: "Todo" },
              { value: "interventions", label: "Intervenciones" },
              { value: "states", label: "Estados" },
              { value: "connection", label: "Conexión" },
            ]}
          />
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Origen">
            {ORIGINS.map((origin) => {
              const active = origins.includes(origin);
              return (
                <button
                  key={origin}
                  onClick={() => toggleOrigin(origin)}
                  aria-pressed={active}
                  className={`rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors ${
                    active ? "border-accent bg-accent/15 text-accent-fg" : "border-line text-muted hover:text-fg"
                  }`}
                >
                  {ORIGIN_INFO[origin].label}
                </button>
              );
            })}
            {origins.length > 0 && (
              <button onClick={() => setOrigins([])} className="px-1.5 text-xs text-faint hover:text-fg">
                Quitar filtro
              </button>
            )}
          </div>
        </div>

        {firstPage.error && <div className="p-4"><ErrorNote>{firstPage.error}</ErrorNote></div>}
        {firstPage.loading && events.length === 0 ? (
          <div className="flex flex-col gap-3 p-4">
            {Array.from({ length: 6 }).map((_, index) => (
              <Skeleton key={index} className="h-12 w-full" />
            ))}
          </div>
        ) : events.length === 0 ? (
          <EmptyState
            title="Sin eventos"
            description="Los eventos aparecen cuando PrintWatch está conectado a la impresora: cambios de estado, órdenes e intervenciones."
          />
        ) : (
          <>
            <EventList events={events} showJob={jobId === null} />
            {hasMore && (
              <div className="border-t border-line/70 p-3 text-center">
                <Button size="sm" onClick={loadMore} disabled={loadingMore}>
                  {loadingMore ? "Cargando…" : "Cargar eventos anteriores"}
                </Button>
              </div>
            )}
          </>
        )}
      </Card>

      <div className="flex flex-col gap-4">
        <ChainCard printerId={printer.id} />
        <OriginLegend />
      </div>
    </div>
  );
}
