import { History, Radio, ScrollText, Thermometer } from "lucide-react";
import { Navigate, Outlet, useOutletContext, useParams } from "react-router-dom";
import { PRINTER_STATUS } from "../../config/status";
import { usePrinters } from "../../context/PrintersContext";
import { formatNumber } from "../../lib/format";
import { readingAge, useLiveTelemetry } from "../../lib/telemetryStore";
import type { Printer, TelemetryReading } from "../../types/api";
import { Badge, EmptyState, RouteTabs, Skeleton } from "../ui";
import { PageHeader } from "./PageHeader";

export interface PrinterOutletContext {
  printer: Printer;
}

export function usePrinterContext(): PrinterOutletContext {
  return useOutletContext<PrinterOutletContext>();
}

function LiveTemperatures({ reading }: { reading: TelemetryReading }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted" title="Temperatura actual / objetivo">
      <Thermometer size={14} className="text-faint" />
      Boquilla {formatNumber(reading.extruder_temp, 0)}/{formatNumber(reading.extruder_target, 0)} °C · Cama{" "}
      {formatNumber(reading.bed_temp, 0)}/{formatNumber(reading.bed_target, 0)} °C
    </span>
  );
}

/** Header and tabs shared by every page of one printer. */
export function PrinterLayout() {
  const { printerId } = useParams<{ printerId: string }>();
  const id = Number(printerId);
  const { printers, loading } = usePrinters();
  const { latest } = useLiveTelemetry(Number.isFinite(id) ? id : null);

  if (!Number.isFinite(id)) return <Navigate to="/" replace />;
  const printer = printers.find((candidate) => candidate.id === id);
  if (!printer) {
    return loading ? (
      <Skeleton className="h-24 w-full" />
    ) : (
      <EmptyState title="Impresora no encontrada" description="Puede que se haya eliminado." />
    );
  }

  const status = PRINTER_STATUS[printer.last_known_status];
  const age = readingAge(latest);

  return (
    <>
      <PageHeader
        title={printer.name}
        subtitle={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <span>{printer.model ?? "Modelo no especificado"}</span>
            <Badge tone={status.tone} dot pulse={printer.last_known_status === "printing"}>
              {status.label}
            </Badge>
            {latest && age !== null && age < 10 && <LiveTemperatures reading={latest} />}
          </span>
        }
      >
        <RouteTabs
          items={[
            { to: "live", label: "En vivo", icon: <Radio size={15} /> },
            { to: "jobs", label: "Trabajos", icon: <History size={15} /> },
            { to: "logbook", label: "Bitácora", icon: <ScrollText size={15} /> },
          ]}
        />
      </PageHeader>
      <Outlet context={{ printer } satisfies PrinterOutletContext} />
    </>
  );
}
