"""Remaining-time estimates of a running print, and how to compare them.

Three ways to estimate it, from what PrintWatch stores once per second (progress, layer) and from the
file itself:

  progress  - the pace of the file's progress (virtual_sdcard.progress, the fraction of the G-code file
              read) since the first sample of the job.
  layers    - the pace of layers since the first sample, over the layers that remain.
  slicer    - the slicer's total estimate (Creality Print writes it in the file name) minus the time
              the print has been running.

Pure functions, so they are tested without a printer and the same code is used to replay a finished job
and measure each method's error against the real end (scripts/analyze_job.py)."""

from dataclasses import dataclass

MIN_PROGRESS_STEP = 0.01  # progress gained before a pace is trusted
MIN_LAYERS_STEP = 3  # layers done before a pace is trusted
MIN_SECONDS = 60.0  # observed time before a pace is trusted


@dataclass(frozen=True)
class Reading:
    """One moment of the job: seconds since a fixed origin, file progress (0-1) and layer number."""

    t: float
    progress: float | None
    layer: int | None


def by_progress(first: Reading, now: Reading) -> float | None:
    if first.progress is None or now.progress is None:
        return None
    gained, seen = now.progress - first.progress, now.t - first.t
    if gained < MIN_PROGRESS_STEP or seen < MIN_SECONDS:
        return None
    return max(0.0, seen * (1 - now.progress) / gained)


def by_layers(first: Reading, now: Reading, total_layers: int | None, window: Reading | None = None) -> float | None:
    """Layers left at the pace of the layers done since `first` (or since `window`, a more recent
    reading, to follow a pace that changes along the part)."""
    start = window or first
    if not total_layers or start.layer is None or now.layer is None:
        return None
    done, seen = now.layer - start.layer, now.t - start.t
    if done < MIN_LAYERS_STEP or seen < MIN_SECONDS:
        return None
    return max(0.0, (total_layers - now.layer) * seen / done)


def by_slicer(estimated_total_s: float | None, running_s: float | None) -> float | None:
    if not estimated_total_s or running_s is None:
        return None
    return max(0.0, estimated_total_s - running_s)


def errors(predictions: list[tuple[float, float | None]]) -> dict | None:
    """Prediction error against the real remaining time: [(real remaining s, predicted s or None)].
    Mean absolute error and mean signed error (positive = too long) in seconds, and the share of the
    moments where the method gave an answer."""
    answered = [(real, predicted) for real, predicted in predictions if predicted is not None]
    if not answered:
        return None
    diffs = [predicted - real for real, predicted in answered]
    return {
        "moments": len(answered),
        "answered": len(answered) / len(predictions),
        "mean_abs_error_s": sum(abs(d) for d in diffs) / len(diffs),
        "mean_signed_error_s": sum(diffs) / len(diffs),
        "mean_abs_relative": sum(abs(predicted - real) / real for real, predicted in answered if real > 0) / max(1, sum(1 for real, _ in answered if real > 0)),
    }
