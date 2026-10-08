import { ChevronRight, History } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { usePrinterContext } from "../components/layout/PrinterLayout";
import { Badge, Card, EmptyState, ErrorNote, Skeleton, Table, Td, Th } from "../components/ui";
import { JOB_STATUS } from "../config/status";
import { formatDateTime, formatDuration, secondsBetween } from "../lib/format";
import { useApi } from "../lib/useApi";
import { listPrintJobsForPrinter } from "../services/printJobs";

export function JobsListPage() {
  const { printer } = usePrinterContext();
  const navigate = useNavigate();
  const jobs = useApi((token) => listPrintJobsForPrinter(token, printer.id), [printer.id]);
  const rows = [...(jobs.data ?? [])].reverse();

  return (
    <Card title="Trabajos de impresión" subtitle="Selecciona uno para ver su historial y repetirlo en el tiempo" padded={false}>
      {jobs.error && <div className="p-4"><ErrorNote>{jobs.error}</ErrorNote></div>}
      {jobs.loading && !jobs.data ? (
        <div className="flex flex-col gap-2 p-4">
          {Array.from({ length: 5 }).map((_, index) => (
            <Skeleton key={index} className="h-9 w-full" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <EmptyState icon={<History size={28} />} title="Sin trabajos" description="Se crean solos cuando la impresora empieza a imprimir." />
      ) : (
        <>
        <ul className="divide-y divide-line/70 sm:hidden">
          {rows.map((job) => (
            <li key={job.id}>
              <Link to={`/printers/${printer.id}/jobs/${job.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-surface-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-fg">
                    <span className="mr-1.5 tabular text-faint">#{job.id}</span>
                    {job.file_name}
                  </p>
                  <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                    <Badge tone={JOB_STATUS[job.status].tone}>{JOB_STATUS[job.status].label}</Badge>
                    <span className="tabular">{formatDateTime(job.started_at)}</span>
                    <span className="tabular">{formatDuration(secondsBetween(job.started_at, job.ended_at))}</span>
                  </p>
                </div>
                <ChevronRight size={16} className="shrink-0 text-faint" />
              </Link>
            </li>
          ))}
        </ul>
        <Table className="hidden sm:block">
          <thead>
            <tr>
              <Th>#</Th>
              <Th>Archivo</Th>
              <Th>Estado</Th>
              <Th>Inicio</Th>
              <Th>Duración</Th>
              <Th>Capas</Th>
              <Th className="w-8" />
            </tr>
          </thead>
          <tbody>
            {rows.map((job) => (
              <tr
                key={job.id}
                onClick={() => navigate(`/printers/${printer.id}/jobs/${job.id}`)}
                className="cursor-pointer transition-colors hover:bg-surface-2"
              >
                <Td className="tabular text-muted">{job.id}</Td>
                <Td className="max-w-[18rem] truncate" title={job.file_name}>
                  {job.file_name}
                </Td>
                <Td>
                  <Badge tone={JOB_STATUS[job.status].tone}>{JOB_STATUS[job.status].label}</Badge>
                </Td>
                <Td className="whitespace-nowrap tabular text-muted">{formatDateTime(job.started_at)}</Td>
                <Td className="whitespace-nowrap tabular">{formatDuration(secondsBetween(job.started_at, job.ended_at))}</Td>
                <Td className="tabular">{job.estimated_layers ?? "—"}</Td>
                <Td>
                  <ChevronRight size={16} className="text-faint" />
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
        </>
      )}
    </Card>
  );
}
