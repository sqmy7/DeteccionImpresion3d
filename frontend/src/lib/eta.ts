// Remaining-time estimate of a running print (mirrors backend/app/services/eta.py).
//
// Measured on the real Creality Hi (job 43, 6 h, docs/laboratorio/analisis_trabajo_43.md), mean error
// against the real end: slicer total minus print time 1 min (5 %), file progress pace 23 min (74 %),
// layer pace 54 min (73 %: the last layers of that part were far slower than the rest). So the slicer's
// estimate is used when the file has one, and the file's progress pace only as a fallback.

export interface ProgressPoint {
  t: number; // ms
  progress: number; // 0-1
}

const MIN_PROGRESS_STEP = 0.01;
const MIN_SECONDS = 60;

/** Slicer's total estimate minus what has been printing (Klipper's print_duration). */
export function bySlicer(estimatedTotalS: number | null | undefined, runningS: number | null | undefined): number | null {
  if (!estimatedTotalS || runningS == null) return null;
  return Math.max(0, estimatedTotalS - runningS);
}

/** Pace of the file's progress since the first sample of the job. */
export function byProgress(first: ProgressPoint | null, nowMs: number, progress: number | null): number | null {
  if (!first || progress == null) return null;
  const gained = progress - first.progress;
  const seen = (nowMs - first.t) / 1000;
  if (gained < MIN_PROGRESS_STEP || seen < MIN_SECONDS) return null;
  return Math.max(0, (seen * (1 - progress)) / gained);
}

export interface Remaining {
  seconds: number | null;
  source: "slicer" | "progress" | null;
}

export function remaining(input: {
  estimatedTotalS?: number | null;
  runningS?: number | null;
  first: ProgressPoint | null;
  nowMs: number;
  progress: number | null;
}): Remaining {
  const slicer = bySlicer(input.estimatedTotalS, input.runningS);
  if (slicer != null) return { seconds: slicer, source: "slicer" };
  const pace = byProgress(input.first, input.nowMs, input.progress);
  return pace != null ? { seconds: pace, source: "progress" } : { seconds: null, source: null };
}
