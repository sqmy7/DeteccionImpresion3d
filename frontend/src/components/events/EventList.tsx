import {
  AlertTriangle,
  ArrowUpDown,
  Ban,
  CheckCircle2,
  Droplet,
  Fan,
  Gauge,
  Pause,
  Play,
  Plug,
  PlugZap,
  Send,
  Terminal,
  Thermometer,
  XCircle,
} from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { describeEvent, describeEvidence, EVENT_LABELS, eventTone, ORIGIN_INFO, phaseLabel } from "../../config/events";
import { formatDateTime } from "../../lib/format";
import type { PrinterEvent } from "../../types/api";
import { Badge, type Tone } from "../ui";

const ICON_TONES: Record<Tone, string> = {
  neutral: "bg-surface-3 text-muted",
  accent: "bg-accent/15 text-accent-fg",
  ok: "bg-ok/15 text-ok-fg",
  warn: "bg-warn/15 text-warn-fg",
  danger: "bg-danger/15 text-danger-fg",
  info: "bg-info/20 text-info-fg",
};

function eventIcon(event: PrinterEvent): ReactNode {
  const size = 15;
  switch (event.event_type) {
    case "target_changed":
      return <Thermometer size={size} />;
    case "speed_factor_changed":
      return <Gauge size={size} />;
    case "flow_factor_changed":
      return <Droplet size={size} />;
    case "fan_changed":
      return <Fan size={size} />;
    case "z_offset_changed":
      return <ArrowUpDown size={size} />;
    case "object_excluded":
      return <Ban size={size} />;
    case "console_command":
      return <Terminal size={size} />;
    case "printwatch_command":
      return <Send size={size} />;
    case "monitor_connected":
      return <Plug size={size} />;
    case "monitor_disconnected":
      return <PlugZap size={size} />;
    case "gcode_error":
    case "klippy_shutdown":
    case "klippy_disconnected":
      return <AlertTriangle size={size} />;
    case "state_changed":
      if (event.value_after === "paused") return <Pause size={size} />;
      if (event.value_after === "printing") return <Play size={size} />;
      if (event.value_after === "complete") return <CheckCircle2 size={size} />;
      if (event.value_after === "error" || event.value_after === "cancelled") return <XCircle size={size} />;
      return <Play size={size} />;
    default:
      return <CheckCircle2 size={size} />;
  }
}

export function EventRow({ event, showJob = true }: { event: PrinterEvent; showJob?: boolean }) {
  const origin = ORIGIN_INFO[event.origin] ?? ORIGIN_INFO.monitor;
  const tone = eventTone(event);
  const evidence = describeEvidence(event);
  const phase = phaseLabel(event.detail?.phase);
  const description = describeEvent(event);

  return (
    <li className="flex gap-3 px-4 py-3">
      <span className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${ICON_TONES[tone]}`}>
        {eventIcon(event)}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="text-sm font-medium text-fg">{EVENT_LABELS[event.event_type] ?? event.event_type}</span>
          <Badge tone={origin.tone} title={origin.description}>
            {origin.label}
          </Badge>
        </div>
        {description && <p className="mt-0.5 break-words text-sm text-muted">{description}</p>}
        <p className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-faint">
          <time dateTime={event.ts} className="tabular">
            {formatDateTime(event.ts)}
          </time>
          {phase && <span>{phase}</span>}
          {evidence && <span className="break-all">{evidence}</span>}
          {showJob && event.print_job_id && (
            <Link to={`/printers/${event.printer_id}/jobs/${event.print_job_id}`} className="text-accent-fg hover:underline">
              Trabajo #{event.print_job_id}
            </Link>
          )}
          <span className="font-mono" title={`Hash SHA-256 del evento #${event.id}`}>
            #{event.id} · {event.hash.slice(0, 10)}…
          </span>
        </p>
      </div>
    </li>
  );
}

export function EventList({ events, showJob = true }: { events: PrinterEvent[]; showJob?: boolean }) {
  return (
    <ul className="divide-y divide-line/70">
      {events.map((event) => (
        <EventRow key={event.id} event={event} showJob={showJob} />
      ))}
    </ul>
  );
}
