"""Per-class precision/recall vs. confidence threshold, measured on the held-out test split,
to pick CONFIDENCE_THRESHOLD (or per-class thresholds) from data instead of from a handful of photos.

It evaluates the DEPLOYED artifact the way the deployed worker runs it - same preprocessing
(plain stretch-resize to 640x640, BGR->RGB, /255), same postprocessing (argmax class per
prediction, class-agnostic NMS at IoU 0.45, confidence filter) as inference/model.py - and
NOT through Ultralytics' val()/predict(), which letterbox and run per-class NMS. Numbers from
those would describe a pipeline that is not the one running in production. The two
postprocessing copies must be kept in sync by hand (this script can't import inference/model.py:
that module needs the worker's env/config); the constants below say where they come from.

Optional --jpeg-reencode: the capture process re-encodes every frame as JPEG (cv2 default,
quality 95) before the worker reads it. INT8 scores are coarse and a borderline detection can
drop below a threshold from that alone (seen on real photos: 0.236 -> 0.172), so calibrating on
already-JPEG'd test images vs. re-encoded ones can differ. On by default; --no-jpeg-reencode to disable.

Label handling mirrors Ultralytics (see load_ground_truth): segmentation-only label files are converted to
enclosing boxes, files mixing segment and detection rows (or otherwise malformed) exclude that whole image with a
warning, and the run aborts if more than --max-excluded-fraction (5%) of the images end up excluded.

Metrics, per class and per threshold t (detections with confidence >= t):
  - instance level: a prediction is a TP if it matches an unmatched ground-truth box of the same
    class at IoU >= 0.5 (greedy by descending confidence); otherwise FP. FN = GT boxes left unmatched.
  - image level: "did the frame get flagged with class c" vs "does the frame contain class c". This is
    the level the system actually acts on (has_defect / the 3-consecutive-layers jam alert are
    per-frame), so it can differ from the instance numbers.
  - "empty images flagged": frames with no annotation at all that still got >=1 detection at t.

The exact-same detections for every t come from ONE inference + ONE NMS pass at the lowest
threshold, then filtering by confidence: greedy NMS visits boxes in descending score, so a
lower-scored box can never suppress a higher-scored one, hence NMS at t == NMS at the floor filtered
at t. (Verified against inference/model.py's DefectDetector when this script was written.)

Usage:
    python calibrate_thresholds.py --model best_int8.onnx \
        --images datasets/processed/images/test --labels datasets/processed/labels/test \
        --out-dir calibration [--reference-metrics best_int8.metrics.json]
"""

import argparse
import ast
import csv
import json
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

INPUT_SIZE = 640  # inference/model.py::_INPUT_SIZE
NMS_IOU = 0.45  # inference/model.py::_IOU_THRESHOLD
MATCH_IOU = 0.5  # standard "mAP50" matching criterion
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DEFAULT_THRESHOLDS = [round(0.05 * i, 2) for i in range(1, 15)]  # 0.05 .. 0.70
DEFAULT_PRECISION_FLOORS = [0.6, 0.7, 0.8, 0.9]
LOW_SUPPORT = 50  # fewer GT instances than this -> the curve is noisy, say so


# ----------------------------------------------------------------------------- inference


def load_session(model_path: Path) -> tuple[ort.InferenceSession, str, list[str]]:
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    raw = session.get_modelmeta().custom_metadata_map.get("names")
    if raw is None:
        raise RuntimeError("ONNX model has no 'names' metadata - re-export it with Ultralytics")
    names = ast.literal_eval(raw)
    if not isinstance(names, dict) or sorted(names) != list(range(len(names))):
        raise RuntimeError(f"ONNX 'names' metadata must map class ids 0..N-1 to names, got: {raw!r}")
    return session, session.get_inputs()[0].name, [str(names[i]) for i in range(len(names))]


def _preprocess(bgr: np.ndarray) -> np.ndarray:
    resized = cv2.resize(bgr, (INPUT_SIZE, INPUT_SIZE))
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    return np.expand_dims((rgb.astype(np.float32) / 255.0).transpose(2, 0, 1), axis=0)


def detect(session: ort.InferenceSession, input_name: str, bgr: np.ndarray, floor: float) -> np.ndarray:
    """-> (N, 6) float array [class_id, confidence, x1, y1, x2, y2], boxes normalized to 0..1."""
    raw = session.run(None, {input_name: _preprocess(bgr)})[0]
    predictions = raw[0].T  # (num_predictions, 4 + num_classes)
    boxes, scores = predictions[:, :4], predictions[:, 4:]
    class_ids = np.argmax(scores, axis=1)
    confidences = np.max(scores, axis=1)

    keep = confidences >= floor
    boxes, class_ids, confidences = boxes[keep], class_ids[keep], confidences[keep]
    if len(boxes) == 0:
        return np.zeros((0, 6), dtype=np.float32)

    nms_boxes = [[float(x - w / 2), float(y - h / 2), float(w), float(h)] for x, y, w, h in boxes]
    indices = cv2.dnn.NMSBoxes(nms_boxes, confidences.tolist(), floor, NMS_IOU)
    if len(indices) == 0:
        return np.zeros((0, 6), dtype=np.float32)
    indices = np.array(indices).flatten()

    xc, yc, w, h = (boxes[indices, k] for k in range(4))
    xyxy = np.stack([xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2], axis=1) / INPUT_SIZE
    return np.concatenate(
        [class_ids[indices, None].astype(np.float32), confidences[indices, None], np.clip(xyxy, 0.0, 1.0)], axis=1
    )


class UnusableLabel(ValueError):
    """The label file can't be used; the image is excluded from the evaluation (Ultralytics: 'ignoring corrupt image/label')."""


def load_ground_truth(label_path: Path) -> tuple[np.ndarray, bool]:
    """-> ((M, 5) float array [class_id, x1, y1, x2, y2] normalized, file_had_polygons).
    Missing/empty file = background frame. Follows what Ultralytics does when it reads labels, so the test population
    is the one the model was trained/validated on:
      - detection rows (5 columns): used as-is.
      - segmentation rows (class + x y pairs): a file made ONLY of them is accepted and each polygon becomes the box
        that encloses it (ultralytics.utils.ops.segments2boxes) - dropping them would leave real defects without
        ground truth and count the model's correct detections as false positives.
      - a file MIXING both kinds, or otherwise malformed (odd point count, coordinates outside 0..1, ...): raises
        UnusableLabel -> the whole image is excluded, exactly like Ultralytics' 'labels mix segment and detection rows'."""
    if not label_path.is_file():
        return np.zeros((0, 5), dtype=np.float32), False
    rows = [line.split() for line in label_path.read_text().splitlines() if line.strip()]
    has_polygons = any(len(r) > 6 for r in rows)
    if has_polygons and any(len(r) == 5 for r in rows):
        raise UnusableLabel("labels mix segment and detection rows")

    parsed = []
    try:
        for r in rows:
            if has_polygons:
                points = np.array(r[1:], dtype=np.float32).reshape(-1, 2)  # odd count -> ValueError
                x, y = points.T
                parsed.append([float(r[0]), x.min(), y.min(), x.max(), y.max()])
                coords = points
            else:
                if len(r) != 5:
                    raise UnusableLabel(f"expected 5 columns (YOLO detection format), got {len(r)}")
                xc, yc, w, h = map(float, r[1:])
                parsed.append([float(r[0]), xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2])
                coords = np.array([xc, yc, w, h])
            if coords.max() > 1.01 or coords.min() < -0.01:
                raise UnusableLabel(f"non-normalized or out of bounds coordinates in row {r[:5]}...")
    except UnusableLabel:
        raise
    except ValueError as exc:
        raise UnusableLabel(f"malformed row ({exc})") from exc

    gt = np.array(parsed, dtype=np.float32).reshape(-1, 5)
    gt[:, 0] = np.round(gt[:, 0])
    gt[:, 1:] = np.clip(gt[:, 1:], 0.0, 1.0)
    return np.unique(gt, axis=0), has_polygons  # exact duplicate rows removed, as Ultralytics does


MAX_WARNINGS_PRINTED = 20


def collect_samples(session, input_name, images_dir: Path, labels_dir: Path, floor: float, jpeg_reencode: bool,
                    limit: int | None, max_excluded_fraction: float) -> tuple[list[tuple[np.ndarray, np.ndarray]], dict]:
    """-> (samples, report). report = {"unreadable_images": [...], "excluded_labels": {image: reason},
    "polygon_label_files_converted": n}. Excluded images are reported, never silently dropped, and if too many are
    excluded the run aborts: that points at a systematic problem (wrong folder, wrong label format), not a few bad files."""
    paths = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if limit:
        paths = paths[:limit]
    if not paths:
        raise FileNotFoundError(f"No images found in {images_dir}")

    samples, unreadable, excluded, polygon_files = [], [], {}, 0
    t0 = time.time()
    for n, path in enumerate(paths, start=1):
        try:
            gt, had_polygons = load_ground_truth(labels_dir / f"{path.stem}.txt")  # label first: skip before inferring
        except UnusableLabel as exc:
            excluded[path.name] = str(exc)
            if len(excluded) <= MAX_WARNINGS_PRINTED:
                print(f"  WARNING {path.name}: ignoring corrupt image/label: {exc}", flush=True)
            continue
        polygon_files += had_polygons

        bgr = cv2.imread(str(path))
        if bgr is None:  # corrupt image - reported, not silently dropped
            unreadable.append(path.name)
            continue
        if jpeg_reencode:
            bgr = cv2.imdecode(cv2.imencode(".jpg", bgr)[1], cv2.IMREAD_COLOR)
        samples.append((detect(session, input_name, bgr, floor), gt))
        if n % 100 == 0 or n == len(paths):
            print(f"  inference {n}/{len(paths)} ({time.time() - t0:.0f}s)", flush=True)

    if len(excluded) > MAX_WARNINGS_PRINTED:
        print(f"  ... and {len(excluded) - MAX_WARNINGS_PRINTED} more excluded labels (all listed in the JSON)")
    dropped = len(unreadable) + len(excluded)
    if dropped / len(paths) > max_excluded_fraction:
        raise RuntimeError(
            f"{dropped}/{len(paths)} images excluded (> {max_excluded_fraction:.0%}) - that is not a few corrupt files, check "
            f"--images/--labels and the label format. First reasons: {list(excluded.items())[:3]}"
        )
    return samples, {"unreadable_images": unreadable, "excluded_labels": excluded, "polygon_label_files_converted": polygon_files}


# ----------------------------------------------------------------------------- evaluation


def _iou(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """a: (N,4), b: (M,4) xyxy -> (N,M)."""
    lt = np.maximum(a[:, None, :2], b[None, :, :2])
    rb = np.minimum(a[:, None, 2:], b[None, :, 2:])
    inter = np.prod(np.clip(rb - lt, 0, None), axis=2)
    area_a = np.prod(a[:, 2:] - a[:, :2], axis=1)
    area_b = np.prod(b[:, 2:] - b[:, :2], axis=1)
    union = area_a[:, None] + area_b[None, :] - inter
    return inter / np.maximum(union, 1e-12)


def _ratio(num: float, den: float) -> float | None:
    return num / den if den else None


def _f1(p: float | None, r: float | None) -> float | None:
    if p is None or r is None or p + r == 0:
        return None
    return 2 * p * r / (p + r)


def evaluate(samples: list[tuple[np.ndarray, np.ndarray]], thresholds: list[float], class_names: list[str]) -> dict:
    """samples: [(detections (N,6), ground truth (M,5))]. Returns {"rows": [...], "n_gt": {...}, ...}.
    One row per (threshold, class) plus class == "ALL" (instances summed over classes; image level =
    'frame flagged with any defect' vs 'frame has any annotation', i.e. the worker's has_defect)."""
    n_classes = len(class_names)
    n_gt = np.zeros(n_classes, dtype=int)
    n_img_gt = np.zeros(n_classes, dtype=int)
    empty_images = 0
    for _, gts in samples:
        for c in range(n_classes):
            k = int((gts[:, 0] == c).sum())
            n_gt[c] += k
            n_img_gt[c] += k > 0
        empty_images += len(gts) == 0
    any_gt_images = len(samples) - empty_images

    rows = []
    for t in thresholds:
        tp = np.zeros(n_classes, dtype=int)
        fp = np.zeros(n_classes, dtype=int)
        img_tp = np.zeros(n_classes, dtype=int)
        img_pred = np.zeros(n_classes, dtype=int)
        any_tp = any_pred = empty_flagged = 0

        for dets, gts in samples:
            dets = dets[dets[:, 1] >= t]
            flagged = len(dets) > 0
            any_pred += flagged
            any_tp += flagged and len(gts) > 0
            empty_flagged += flagged and len(gts) == 0

            for c in range(n_classes):
                pc = dets[dets[:, 0] == c]
                gc = gts[gts[:, 0] == c]
                img_pred[c] += len(pc) > 0
                img_tp[c] += len(pc) > 0 and len(gc) > 0
                if len(pc) == 0:
                    continue
                if len(gc) == 0:
                    fp[c] += len(pc)
                    continue
                pc = pc[np.argsort(-pc[:, 1])]
                ious = _iou(pc[:, 2:], gc[:, 1:])
                matched = np.zeros(len(gc), dtype=bool)
                for i in range(len(pc)):
                    candidates = np.where(matched, -1.0, ious[i])
                    j = int(np.argmax(candidates))
                    if candidates[j] >= MATCH_IOU:
                        matched[j] = True
                        tp[c] += 1
                    else:
                        fp[c] += 1

        def row(name, tp_, fp_, gt_, i_tp, i_pred, i_gt):
            p, r = _ratio(tp_, tp_ + fp_), _ratio(tp_, gt_)
            ip, ir = _ratio(i_tp, i_pred), _ratio(i_tp, i_gt)
            return {"threshold": t, "class": name, "tp": int(tp_), "fp": int(fp_), "fn": int(gt_ - tp_),
                    "precision": p, "recall": r, "f1": _f1(p, r),
                    "img_precision": ip, "img_recall": ir, "img_f1": _f1(ip, ir)}

        for c, name in enumerate(class_names):
            rows.append(row(name, tp[c], fp[c], n_gt[c], img_tp[c], img_pred[c], n_img_gt[c]))
        rows.append(row("ALL", tp.sum(), fp.sum(), n_gt.sum(), any_tp, any_pred, any_gt_images))
        rows[-1]["empty_images_flagged"] = int(empty_flagged)

    return {"rows": rows, "n_gt": {n: int(n_gt[i]) for i, n in enumerate(class_names)},
            "n_images_with_class": {n: int(n_img_gt[i]) for i, n in enumerate(class_names)},
            "n_images": len(samples), "n_empty_images": int(empty_images)}


def _lowest_stable(rows: list[dict], p_key: str, r_key: str, floor: float) -> dict | None:
    """Lowest threshold whose precision is >= floor AND stays >= floor at every higher threshold (where
    anything is still predicted). Plain "lowest threshold with P >= floor" would pick a lucky dip on a jagged
    curve (few instances -> precision jumps around); requiring it to hold from there upward is the safer
    reading when precision is the priority. Thresholds with no predictions (precision undefined) don't count."""
    defined = [r for r in rows if r[p_key] is not None]
    for k, r in enumerate(defined):
        if all(x[p_key] >= floor for x in defined[k:]):
            return {"threshold": r["threshold"], "precision": r[p_key], "recall": r[r_key]}
    return None


def recommend(result: dict, class_names: list[str], precision_floors: list[float]) -> dict:
    """Per class: the best-F1 threshold, and for each precision floor the lowest threshold that reaches it and
    keeps it (see _lowest_stable) with the recall left there - at instance level and at image level."""
    out = {}
    for name in [*class_names, "ALL"]:
        rows = [r for r in result["rows"] if r["class"] == name]
        entry = {"n_gt": result["n_gt"].get(name, sum(result["n_gt"].values()))}
        scored = [r for r in rows if r["f1"] is not None]
        if scored:
            best = max(scored, key=lambda r: (r["f1"], r["threshold"]))  # ties -> higher (safer) threshold
            entry["best_f1"] = {k: best[k] for k in ("threshold", "precision", "recall", "f1")}
        entry["lowest_threshold_for_precision"] = {
            str(f): _lowest_stable(rows, "precision", "recall", f) for f in precision_floors
        }
        entry["lowest_threshold_for_image_precision"] = {
            str(f): _lowest_stable(rows, "img_precision", "img_recall", f) for f in precision_floors
        }
        out[name] = entry
    return out


# ----------------------------------------------------------------------------- reporting


def _fmt(v: float | None) -> str:
    return "  -  " if v is None else f"{v:5.3f}"


def print_report(result: dict, recs: dict, class_names: list[str], precision_floors: list[float]) -> None:
    print(f"\nTest set: {result['n_images']} images evaluated ({result['n_empty_images']} without annotations)")
    for name in [*class_names, "ALL"]:
        rows = [r for r in result["rows"] if r["class"] == name]
        support = result["n_gt"].get(name, sum(result["n_gt"].values()))
        imgs = result["n_images_with_class"].get(name, result["n_images"] - result["n_empty_images"])
        warn = f"   <-- only {support} instances: noisy curve" if name != "ALL" and support < LOW_SUPPORT else ""
        print(f"\n=== {name}  ({support} GT instances in {imgs} images){warn}")
        extra = "  empty imgs flagged" if name == "ALL" else ""
        print(f"{'thr':>5} {'TP':>5} {'FP':>5} {'FN':>5} | {'P':>5} {'R':>5} {'F1':>5} | {'imgP':>5} {'imgR':>5}{extra}")
        for r in rows:
            tail = f"  {r.get('empty_images_flagged', ''):>5}/{result['n_empty_images']}" if name == "ALL" else ""
            print(f"{r['threshold']:>5.2f} {r['tp']:>5} {r['fp']:>5} {r['fn']:>5} | {_fmt(r['precision'])} "
                  f"{_fmt(r['recall'])} {_fmt(r['f1'])} | {_fmt(r['img_precision'])} {_fmt(r['img_recall'])}{tail}")

    for level, key, unit in (("instance level; IoU>=0.5", "lowest_threshold_for_precision", "recall"),
                             ("image level: frame flagged with the class", "lowest_threshold_for_image_precision", "image recall")):
        print(f"\n=== Lowest threshold that reaches AND keeps the precision floor ({level}) -> threshold / {unit} left")
        head = "".join(f"P>={f}".ljust(20) for f in precision_floors)
        print(f"{'class':<20}{'GT':>5}  {head}")
        for name in [*class_names, "ALL"]:
            e = recs[name]
            cells = []
            for f in precision_floors:
                x = e[key][str(f)]
                cells.append((f"{x['threshold']:.2f} / {x['recall']:.3f}" if x else "unreachable").ljust(20))
            print(f"{name:<20}{e['n_gt']:>5}  {''.join(cells)}")
    print("\nbest F1 (instance level, for reference): " + ", ".join(
        f"{n} {recs[n]['best_f1']['threshold']:.2f}" for n in class_names if "best_f1" in recs[n]))


def print_reference_check(recs: dict, reference_path: Path) -> None:
    ref = json.loads(reference_path.read_text()).get("per_class", {})
    print("\n=== Sanity check vs. the Ultralytics numbers you supplied (they use the confidence that maximizes F1,")
    print("    letterbox + per-class NMS; expect the same ballpark, not identical values)")
    print(f"{'class':<20}{'ref P':>7}{'ref R':>7}   {'mine @best-F1 thr':<20}{'P':>7}{'R':>7}")
    for name, e in recs.items():
        b, r = e.get("best_f1"), ref.get(name)  # 'ALL' has no reference entry -> skipped
        if b and r:
            print(f"{name:<20}{r['precision']:>7.3f}{r['recall']:>7.3f}   {b['threshold']:<20.2f}"
                  f"{b['precision']:>7.3f}{b['recall']:>7.3f}")


def write_outputs(out_dir: Path, result: dict, recs: dict, class_names: list[str], meta: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = ["threshold", "class", "tp", "fp", "fn", "precision", "recall", "f1",
              "img_precision", "img_recall", "img_f1", "empty_images_flagged"]
    with open(out_dir / "threshold_calibration.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, restval="")
        writer.writeheader()
        for r in result["rows"]:
            writer.writerow({k: ("" if r.get(k) is None else r.get(k, "")) for k in fields})
    (out_dir / "threshold_calibration.json").write_text(
        json.dumps({"meta": meta, "n_gt": result["n_gt"], "n_images": result["n_images"],
                    "n_empty_images": result["n_empty_images"], "recommendations": recs}, indent=2)
    )

    try:
        # Figure directly, not pyplot: pyplot/matplotlib.use() would change the backend of a whole
        # notebook kernel when this runs from Colab.
        from matplotlib.figure import Figure
    except ImportError:
        print("matplotlib not installed - skipping the plot")
        return
    fig = Figure(figsize=(15, 8))
    axes = fig.subplots(2, 3, sharex=True, sharey=True)
    for ax, name in zip(axes.flat, class_names):
        rows = [r for r in result["rows"] if r["class"] == name]
        t = [r["threshold"] for r in rows]
        for key, label, style in [("precision", "precision", "-"), ("recall", "recall", "-"), ("f1", "F1", "-"),
                                  ("img_precision", "image precision", ":"), ("img_recall", "image recall", ":")]:
            ax.plot(t, [np.nan if r[key] is None else r[key] for r in rows], style, marker="o", ms=3, label=label)
        ax.set_title(f"{name} ({result['n_gt'][name]} GT)")
        ax.set_ylim(0, 1.02)
        ax.grid(alpha=0.3)
    for ax in axes[1]:
        ax.set_xlabel("confidence threshold")
    fig.legend(*axes[0][0].get_legend_handles_labels(), loc="lower center", ncol=5)
    fig.suptitle(f"Precision / recall vs. confidence - {meta['model']} on the test split")
    fig.tight_layout(rect=(0, 0.05, 1, 0.97))
    fig.savefig(out_dir / "threshold_calibration.png", dpi=110)


# ----------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("calibration"))
    parser.add_argument("--thresholds", type=float, nargs="+", default=DEFAULT_THRESHOLDS)
    parser.add_argument("--precision-floors", type=float, nargs="+", default=DEFAULT_PRECISION_FLOORS)
    parser.add_argument("--reference-metrics", type=Path, help="metrics.json (per_class precision/recall) to compare against")
    parser.add_argument("--jpeg-reencode", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--limit", type=int, help="only the first N images (smoke test)")
    parser.add_argument("--max-excluded-fraction", type=float, default=0.05,
                        help="abort if more than this fraction of images is excluded as unreadable/corrupt-label")
    args = parser.parse_args(argv)

    thresholds = sorted(set(args.thresholds))
    session, input_name, class_names = load_session(args.model)
    print(f"Model {args.model.name}: classes {class_names}; thresholds {thresholds[0]}..{thresholds[-1]}; "
          f"jpeg re-encode: {args.jpeg_reencode}")

    samples, report = collect_samples(session, input_name, args.images, args.labels, thresholds[0],
                                      args.jpeg_reencode, args.limit, args.max_excluded_fraction)
    print(f"\nEvaluated {len(samples)} images. Excluded: {len(report['unreadable_images'])} unreadable image(s) "
          f"{report['unreadable_images']}, {len(report['excluded_labels'])} with unusable labels "
          f"(Ultralytics' 'ignoring corrupt image/label'). Polygon-only label files converted to boxes: "
          f"{report['polygon_label_files_converted']}.")
    bad = {int(c) for _, gts in samples for c in gts[:, 0]} - set(range(len(class_names)))
    if bad:
        raise ValueError(f"Labels use class ids {sorted(bad)} that the model does not have ({len(class_names)} classes)")

    result = evaluate(samples, thresholds, class_names)
    recs = recommend(result, class_names, args.precision_floors)
    print_report(result, recs, class_names, args.precision_floors)
    if args.reference_metrics:
        print_reference_check(recs, args.reference_metrics)

    meta = {"model": args.model.name, "thresholds": thresholds, "match_iou": MATCH_IOU, "nms_iou": NMS_IOU,
            "jpeg_reencode": args.jpeg_reencode, "skipped_images": report["unreadable_images"],
            "excluded_labels": report["excluded_labels"],
            "polygon_label_files_converted": report["polygon_label_files_converted"], "preprocess": "stretch-resize (as inference/model.py)"}
    write_outputs(args.out_dir, result, recs, class_names, meta)
    print(f"\nWrote threshold_calibration.csv/.json/.png to {args.out_dir}")
    return {"result": result, "recommendations": recs}


if __name__ == "__main__":
    main()
