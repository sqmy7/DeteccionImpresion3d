import { ShieldAlert, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { classLabel } from "../config/defectClasses";
import { usePrinters } from "../context/PrintersContext";
import { useAuth } from "../hooks/useAuth";
import { useWsEvent } from "../hooks/useWebSocket";
import { incidentClassLabel, needsAttention, noticeText } from "../lib/incidentView";
import { listIncidents } from "../services/incidents";
import type { Incident } from "../types/api";

const BASE_TITLE = typeof document !== "undefined" ? document.title : "PrintWatch";

/** A banner that follows the user across the web while an incident is unclosed, whatever screen they are on, and
 * puts a mark in the browser tab's title for when the tab is not in front. An incident that is already open when
 * the web is opened shows too (it is read from the server, not only from the live feed). «Ocultar» hides it
 * until it changes (a pause confirmed, a decision), so it does not nag but does not get lost either. */
export function IncidentNotice() {
  const { token } = useAuth();
  const { printers } = usePrinters();
  const [items, setItems] = useState<Incident[]>([]);
  const [hidden, setHidden] = useState<Record<number, string>>({});
  const load = useRef<() => void>(() => {});

  load.current = () => {
    if (!token) return;
    listIncidents(token, { state: "unclosed", limit: 20 })
      .then(setItems)
      .catch(() => {});
  };
  const refresh = useCallback(() => load.current(), []);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 60_000); // a safety net if the live feed drops
    return () => window.clearInterval(timer);
  }, [token, refresh]);
  useWsEvent("incident.opened", refresh);
  useWsEvent("incident.updated", refresh);

  const open = items.filter(needsAttention);
  const visible = open.filter((incident) => hidden[incident.id] !== `${incident.status}:${incident.updated_at}`);

  useEffect(() => {
    document.title = open.length > 0 ? `(!) ${open.length} incidente${open.length === 1 ? "" : "s"} · ${BASE_TITLE}` : BASE_TITLE;
    return () => {
      document.title = BASE_TITLE;
    };
  }, [open.length]);

  if (visible.length === 0) return null;

  return (
    <div className="sticky top-14 z-20 mb-4 flex flex-col gap-2 lg:top-2" role="alert" aria-live="assertive">
      {visible.map((incident) => {
        const printerName = printers.find((printer) => printer.id === incident.printer_id)?.name ?? `Impresora #${incident.printer_id}`;
        const urgent = incident.status === "unconfirmed" || incident.status === "paused";
        return (
          <div
            key={incident.id}
            className={`flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border-2 bg-surface-2/95 px-4 py-3 shadow-xl backdrop-blur ${
              urgent ? "border-danger/70" : "border-warn/70"
            }`}
          >
            <ShieldAlert size={20} className={urgent ? "shrink-0 text-danger-fg" : "shrink-0 text-warn-fg"} />
            <p className="min-w-0 flex-1 text-sm font-medium text-fg">
              Incidente #{incident.id}:{" "}
              {noticeText(incident, printerName, incidentClassLabel(incident.defect_class, classLabel))}
              {incident.status === "unconfirmed" && <span className="ml-1 text-danger-fg">· pausa NO confirmada</span>}
              {incident.status === "paused" && <span className="ml-1 text-warn-fg">· la impresora está en pausa</span>}
            </p>
            <Link
              to={`/printers/${incident.printer_id}/incidents/${incident.id}`}
              className="rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-canvas hover:bg-accent/90"
            >
              Ver incidente
            </Link>
            <button
              onClick={() => setHidden((current) => ({ ...current, [incident.id]: `${incident.status}:${incident.updated_at}` }))}
              aria-label="Ocultar el aviso hasta que cambie"
              title="Ocultar hasta que cambie"
              className="rounded-md p-1.5 text-muted hover:bg-surface-3 hover:text-fg"
            >
              <X size={15} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
