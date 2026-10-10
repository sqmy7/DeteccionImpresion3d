import { formatDuration } from "./format";
import type { PrintJob } from "../types/api";

/** PrintWatch followed less than this share of what the printer says it printed: it joined late. */
const LATE_JOIN_RATIO = 0.9;

export interface JobTime {
  seconds: number | null;
  /** "printer": the printer's own print clock; "followed": only how long PrintWatch followed the job. */
  source: "printer" | "followed";
  /** Said next to the duration when PrintWatch joined late, e.g. "PrintWatch lo siguió 2 h 45 min". */
  note: string | null;
}

type JobTimes = Pick<PrintJob, "started_at" | "ended_at" | "status" | "printed_s">;

/** How long a job printed. started_at..ended_at is only the time PrintWatch followed it (2 h 45 min of
 * the 6 h print of job 43, which it joined at 45 %), so a finished job shows the printer's print clock
 * (`printed_s`) when it has one. A running job shows the time it has been followed, unless it joined
 * late: then the printer's clock. A job recorded before the clock was kept (`printed_s` null) shows the
 * time followed and claims nothing more. */
export function jobTime(job: JobTimes, options: { liveRunningS?: number | null; nowMs?: number } = {}): JobTime {
  const start = new Date(job.started_at).getTime();
  const end = job.ended_at ? new Date(job.ended_at).getTime() : (options.nowMs ?? Date.now());
  const followed = Math.max(0, (end - start) / 1000);
  const running = job.status === "running";
  const printed = running ? (options.liveRunningS ?? job.printed_s ?? null) : (job.printed_s ?? null);

  if (printed === null || !Number.isFinite(printed)) return { seconds: followed, source: "followed", note: null };

  const joinedLate = followed < LATE_JOIN_RATIO * printed;
  if (running && !joinedLate) return { seconds: followed, source: "followed", note: null };
  return {
    seconds: printed,
    source: "printer",
    note: joinedLate ? `PrintWatch lo siguió ${formatDuration(followed)}` : null,
  };
}

/** The layer to show for a job: the live one only while that job is the one printing; otherwise the last
 * layer the job itself recorded (an idle printer reports layer 0, which is not the job's layer). */
export function jobLayer(args: {
  running: boolean;
  liveLayer: number | null | undefined;
  summaryLayer: number | null | undefined;
}): number | null {
  if (args.running && args.liveLayer != null) return args.liveLayer;
  return args.summaryLayer ?? null;
}
