import { ChevronRight, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { usePrinterContext } from "../components/layout/PrinterLayout";
import { Badge, Card, EmptyState, ErrorNote, Segmented, Skeleton, Table, Td, Th } from "../components/ui";
import { classLabel } from "../config/defectClasses";
import { useWsEvent } from "../hooks/useWebSocket";
import { formatDateTime, formatDuration, formatPercent } from "../lib/format";
import { incidentClassLabel, incidentKind, LABEL_INFO, REASON_LABELS, STATUS_INFO } from "../lib/incidentView";
import { useApi } from "../lib/useApi";
import { listIncidents, type IncidentFilter } from "../services/incidents";
import type { Incident } from "../types/api";

function lastLayer(incident: Incident): { layer: number | null; confidence: number | null } {
  const last = incident.streak[incident.streak.length - 1];
  return { layer: last?.layer ?? null, confidence: last?.confidence ?? null };
}

/** How the incidents were judged: the numbers behind the false positive rate (docs/META_FINAL.md a.3). */
function Verdicts({ incidents }: { incidents: Incident[] }) {
  const correct = incidents.filter((item) => item.label === "correct").length;
  const falsePositive = incidents.filter((item) => item.label === "false_positive").length;
  const unlabeled = incidents.length - correct - falsePositive;
  return (
    <p className="text-xs text-muted">
      {incidents.length} {incidents.length === 1 ? "incidente" : "incidentes"} · <span className="text-ok-fg">{correct} aciertos</span> ·{" "}
      <span className="text-info-fg">{falsePositive} falsos positivos</span> · {unlabeled} sin etiquetar
    </p>
  );
}

export function IncidentsListPage() {
  const { printer } = usePrinterContext();
  const navigate = useNavigate();
  const [filter, setFilter] = useState<IncidentFilter>("all");
  const incidents = useApi((token) => listIncidents(token, { printerId: printer.id, state: filter }), [printer.id, filter]);
  useWsEvent("incident.opened", () => incidents.reload());
  useWsEvent("incident.updated", () => incidents.reload());

  const rows = incidents.data ?? [];

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <ShieldAlert size={15} className="text-faint" />
          Incidentes
        </span>
      }
      subtitle="Lo que el modelo vio o la impresora hizo que pide una decisión"
      actions={
        <Segmented<IncidentFilter>
          label="Filtro"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: "Todos" },
            { value: "unclosed", label: "Sin cerrar" },
            { value: "closed", label: "Cerrados" },
          ]}
        />
      }
      padded={false}
    >
      {incidents.loading && !incidents.data ? (
        <div className="p-4">
          <Skeleton className="h-40 w-full" />
        </div>
      ) : incidents.error ? (
        <div className="p-4">
          <ErrorNote>{incidents.error}</ErrorNote>
        </div>
      ) : rows.length === 0 ? (
        <EmptyState
          icon={<ShieldAlert size={28} />}
          title="Sin incidentes"
          description="Se abren solos cuando el modelo ve una clase inminente, se activa la pausa automática o la impresora se pausa."
        />
      ) : (
        <>
          <div className="border-b border-line/70 px-4 py-2">
            <Verdicts incidents={rows} />
          </div>
          <ul className="divide-y divide-line/70 sm:hidden">
            {rows.map((incident) => {
              const { layer, confidence } = lastLayer(incident);
              return (
                <li key={incident.id}>
                  <Link to={`${incident.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-surface-2">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-fg">
                        <span className="mr-1.5 tabular text-faint">#{incident.id}</span>
                        {incidentClassLabel(incident.defect_class, classLabel)}
                        {layer !== null ? ` · capa ${layer}` : ""}
                      </p>
                      <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                        <Badge tone={STATUS_INFO[incident.status].tone}>{STATUS_INFO[incident.status].label}</Badge>
                        <span>{REASON_LABELS[incidentKind(incident)]}</span>
                        <span className="tabular">{formatDateTime(incident.opened_at)}</span>
                        {confidence !== null && <span className="tabular">{formatPercent(confidence)}</span>}
                      </p>
                    </div>
                    <ChevronRight size={16} className="shrink-0 text-faint" />
                  </Link>
                </li>
              );
            })}
          </ul>
          <Table className="hidden sm:block">
            <thead>
              <tr>
                <Th>#</Th>
                <Th>Hora</Th>
                <Th>Clase</Th>
                <Th>Capa</Th>
                <Th>Confianza</Th>
                <Th>Motivo</Th>
                <Th>Estado</Th>
                <Th>A la pausa</Th>
                <Th>Etiqueta</Th>
                <Th className="w-8" />
              </tr>
            </thead>
            <tbody>
              {rows.map((incident) => {
                const { layer, confidence } = lastLayer(incident);
                return (
                  <tr
                    key={incident.id}
                    onClick={() => navigate(`${incident.id}`)}
                    className="cursor-pointer transition-colors hover:bg-surface-2"
                  >
                    <Td className="tabular text-muted">{incident.id}</Td>
                    <Td className="whitespace-nowrap tabular text-muted">{formatDateTime(incident.opened_at)}</Td>
                    <Td>{incidentClassLabel(incident.defect_class, classLabel)}</Td>
                    <Td className="tabular">{layer ?? "—"}</Td>
                    <Td className="tabular">{confidence !== null ? formatPercent(confidence) : "—"}</Td>
                    <Td>{REASON_LABELS[incidentKind(incident)]}</Td>
                    <Td>
                      <Badge tone={STATUS_INFO[incident.status].tone}>{STATUS_INFO[incident.status].label}</Badge>
                    </Td>
                    <Td className="whitespace-nowrap tabular">{incident.seconds_to_pause !== null ? formatDuration(incident.seconds_to_pause) : "—"}</Td>
                    <Td>
                      <Badge tone={LABEL_INFO[incident.label].tone}>{LABEL_INFO[incident.label].label}</Badge>
                    </Td>
                    <Td>
                      <ChevronRight size={16} className="text-faint" />
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        </>
      )}
    </Card>
  );
}
