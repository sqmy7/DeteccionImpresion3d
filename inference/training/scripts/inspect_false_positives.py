"""Diagnose WHY one class produces false alarms (or misses): for the test split, at a given confidence threshold,
classify every false positive and every missed ground-truth box of that class by cause, and save annotated images to
look at. Built to decide the remedy for a weak class (e.g. blob_over_extrusion) before spending time on retraining.

Uses exactly the same model handling, preprocessing, postprocessing, label rules and TP/FP matching as
calibrate_thresholds.py (it imports it), so the counts here add up to that script's table for the same threshold.

False positive (a predicted box of the class with no unmatched same-class ground truth at IoU >= 0.5) causes:
  duplicate      overlaps a real box of the class that a higher-scored prediction already matched
  mislocalized   overlaps a real box of the class (IoU 0.1-0.5) but too loosely to count
  confused_with:X  overlaps a ground-truth box of ANOTHER class X (IoU >= 0.3): the model sees a defect, wrong class
  unannotated    no ground truth there at all: background - OR a real defect nobody labeled. Only looking at the
                 saved images tells these two apart; a large share of unannotated boxes that look like real blobs
                 means label gaps in the dataset, not a model problem.
Missed ground-truth box (false negative) causes, by what the model predicted at that place (IoU >= 0.3):
  below_threshold  right class, but confidence < threshold (the threshold cost this recall)
  predicted_as:X   another class won there
  mislocalized     right class and confidence >= threshold, box too loose (IoU < 0.5)
  not_detected     nothing at all above the 0.05 floor

Also reports box sizes (side in the 640x640 model input) of found vs missed ground truth: small objects are a
common reason for a weak class and the remedy differs (higher resolution vs. more data).

Usage:
    python inspect_false_positives.py --model best_fp32.onnx --class-name blob_over_extrusion --threshold 0.25 \
        --images datasets/processed/images/test --labels datasets/processed/labels/test --out-dir diagnosis
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calibrate_thresholds as ct  # noqa: E402

FLOOR = 0.05  # lowest confidence looked at when explaining misses
CONFUSION_IOU = 0.3
LOOSE_IOU = 0.1
MAX_SIDE_SAVED = 900
THUMB_WIDTH = 480
COLORS = {  # BGR
    "gt": (60, 200, 60), "gt_other": (200, 120, 40), "missed": (200, 60, 200), "fp": (40, 40, 230), "tp": (0, 215, 255),
}


# ----------------------------------------------------------------------------- analysis (pure, testable)


def analyse_image(dets: np.ndarray, gts: np.ndarray, class_id: int, threshold: float, class_names: list[str]) -> dict:
    """dets (N,6) [cls, conf, x1..y2] at >= FLOOR; gts (M,5) [cls, x1..y2], both normalized.
    Same greedy matching as calibrate_thresholds.evaluate (predictions of the class with conf >= threshold, by
    descending confidence, each ground truth matched once at IoU >= 0.5)."""
    preds = dets[(dets[:, 0] == class_id) & (dets[:, 1] >= threshold)]
    preds = preds[np.argsort(-preds[:, 1])]
    gt_c = gts[gts[:, 0] == class_id]
    matched = np.zeros(len(gt_c), dtype=bool)
    ious = ct._iou(preds[:, 2:], gt_c[:, 1:]) if len(preds) and len(gt_c) else None

    tps, fps = [], []
    for i, p in enumerate(preds):
        if ious is not None:
            candidates = np.where(matched, -1.0, ious[i])
            j = int(np.argmax(candidates))
            if candidates[j] >= ct.MATCH_IOU:
                matched[j] = True
                tps.append({"box": p[2:], "conf": float(p[1])})
                continue
        fps.append({"box": p[2:], "conf": float(p[1]), **_fp_cause(p, gts, class_id, class_names)})

    fns = [{"box": g[1:], **_fn_cause(g, dets, class_id, threshold, class_names)} for g, m in zip(gt_c, matched) if not m]
    return {"tps": tps, "fps": fps, "fns": fns, "n_gt": len(gt_c), "gt_other": gts[gts[:, 0] != class_id]}


def _fp_cause(pred: np.ndarray, gts: np.ndarray, class_id: int, class_names: list[str]) -> dict:
    if len(gts) == 0:
        return {"cause": "unannotated", "detail": "image has no annotations"}
    ious = ct._iou(pred[None, 2:], gts[:, 1:])[0]
    same = gts[:, 0] == class_id
    if same.any():
        best_same = float(ious[same].max())
        if best_same >= ct.MATCH_IOU:
            return {"cause": "duplicate", "detail": f"IoU {best_same:.2f} with an already-matched real box"}
        if best_same >= LOOSE_IOU:
            return {"cause": "mislocalized", "detail": f"IoU {best_same:.2f} with a real box"}
    other = (~same) & (ious >= CONFUSION_IOU)
    if other.any():
        k = int(np.argmax(np.where(other, ious, -1)))
        name = class_names[int(gts[k, 0])]
        return {"cause": f"confused_with:{name}", "detail": f"IoU {ious[k]:.2f} with a real {name} box"}
    return {"cause": "unannotated", "detail": "no ground truth at that location"}


def _fn_cause(gt: np.ndarray, dets: np.ndarray, class_id: int, threshold: float, class_names: list[str]) -> dict:
    if len(dets) == 0:
        return {"cause": "not_detected", "detail": "no detection above the floor"}
    ious = ct._iou(gt[None, 1:], dets[:, 2:])[0]
    # same class counts as 'there' from IoU 0.1 (same criterion as the FP side's 'mislocalized'), other classes from 0.3
    near = (ious >= CONFUSION_IOU) | ((dets[:, 0] == class_id) & (ious >= LOOSE_IOU))
    if not near.any():
        return {"cause": "not_detected", "detail": "no detection above the floor near it"}
    k = int(np.argmax(np.where(near, dets[:, 1], -1)))  # highest-confidence detection overlapping it
    cls, conf = int(dets[k, 0]), float(dets[k, 1])
    if cls != class_id:
        return {"cause": f"predicted_as:{class_names[cls]}", "detail": f"conf {conf:.2f}, IoU {ious[k]:.2f}"}
    if conf < threshold:
        return {"cause": "below_threshold", "detail": f"right class at conf {conf:.2f} (< {threshold})"}
    return {"cause": "mislocalized", "detail": f"right class conf {conf:.2f} but IoU {ious[k]:.2f}"}


def _side_px(box: np.ndarray) -> float:
    """sqrt(area) of a normalized box in the 640x640 model input (the stretch-resize makes the scale per-axis)."""
    return float(np.sqrt(max(box[2] - box[0], 0) * max(box[3] - box[1], 0)) * ct.INPUT_SIZE)


def summarize(per_image: dict[str, dict], threshold: float) -> dict:
    fp_causes, fn_causes = {}, {}
    n_tp = n_fp = n_fn = 0
    tp_sizes, fn_sizes = [], []
    fp_images = fn_images = 0
    for name, a in per_image.items():
        n_tp += len(a["tps"]); n_fp += len(a["fps"]); n_fn += len(a["fns"])
        fp_images += bool(a["fps"]); fn_images += bool(a["fns"])
        for f in a["fps"]:
            fp_causes[f["cause"]] = fp_causes.get(f["cause"], 0) + 1
        for f in a["fns"]:
            fn_causes[f["cause"]] = fn_causes.get(f["cause"], 0) + 1
            fn_sizes.append(_side_px(f["box"]))
        tp_sizes += [_side_px(t["box"]) for t in a["tps"]]
    med = lambda v: None if not v else round(float(np.median(v)), 1)  # noqa: E731
    return {"threshold": threshold, "tp": n_tp, "fp": n_fp, "fn": n_fn, "images_with_fp": fp_images,
            "images_with_missed": fn_images,
            "precision": ct._ratio(n_tp, n_tp + n_fp), "recall": ct._ratio(n_tp, n_tp + n_fn),
            "fp_causes": dict(sorted(fp_causes.items(), key=lambda kv: -kv[1])),
            "fn_causes": dict(sorted(fn_causes.items(), key=lambda kv: -kv[1])),
            "median_side_px_found": med(tp_sizes), "median_side_px_missed": med(fn_sizes)}


# ----------------------------------------------------------------------------- drawing


def _rect(img, box, color, label=None, thick=2):
    h, w = img.shape[:2]
    x1, y1, x2, y2 = (int(round(v)) for v in (box[0] * w, box[1] * h, box[2] * w, box[3] * h))
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thick)
    if label:
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        x1 = max(min(x1, w - tw - 8), 0)  # keep the label inside the image
        top = max(y1 - th - 6, 0)
        cv2.rectangle(img, (x1, top), (x1 + tw + 6, top + th + 6), color, -1)
        cv2.putText(img, label, (x1 + 3, top + th + 1), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)


def annotate(bgr: np.ndarray, a: dict, class_name: str, title: str) -> np.ndarray:
    """Green = real boxes of the class, blue = real boxes of other classes, yellow = correct predictions,
    red = false positives (with cause), magenta = real boxes the model missed (with cause)."""
    img = bgr.copy()
    scale = MAX_SIDE_SAVED / max(img.shape[:2])
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    for g in a["gt_other"]:
        _rect(img, g[1:], COLORS["gt_other"], f"GT {a['names'][int(g[0])]}", 1)
    missed = {tuple(np.round(f["box"], 5)) for f in a["fns"]}
    for g in a["gt_c"]:
        if tuple(np.round(g[1:], 5)) not in missed:
            _rect(img, g[1:], COLORS["gt"], f"GT {class_name}", 2)
    for f in a["fns"]:
        _rect(img, f["box"], COLORS["missed"], f"MISSED: {f['cause']}", 2)
    for t in a["tps"]:
        _rect(img, t["box"], COLORS["tp"], f"ok {t['conf']:.2f}", 2)
    for f in a["fps"]:
        _rect(img, f["box"], COLORS["fp"], f"FP {f['conf']:.2f} {f['cause']}", 2)
    bar = np.full((28, img.shape[1], 3), 30, np.uint8)
    cv2.putText(bar, title, (6, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (235, 235, 235), 1, cv2.LINE_AA)
    return np.vstack([bar, img])


def montage(images: list[np.ndarray], columns: int = 3) -> np.ndarray:
    thumbs = []
    for im in images:
        s = THUMB_WIDTH / im.shape[1]
        thumbs.append(cv2.resize(im, (THUMB_WIDTH, int(im.shape[0] * s)), interpolation=cv2.INTER_AREA))
    rows = []
    for i in range(0, len(thumbs), columns):
        row = thumbs[i:i + columns]
        height = max(t.shape[0] for t in row)
        row = [cv2.copyMakeBorder(t, 0, height - t.shape[0], 0, 4, cv2.BORDER_CONSTANT, value=(20, 20, 20)) for t in row]
        row += [np.full((height, THUMB_WIDTH + 4, 3), 20, np.uint8)] * (columns - len(row))
        rows.append(np.hstack(row))
    return np.vstack(rows)


# ----------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--class-name", default="blob_over_extrusion")
    parser.add_argument("--threshold", type=float, default=0.25)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("diagnosis"))
    parser.add_argument("--max-images", type=int, default=30, help="annotated images to save per group (FP / missed)")
    parser.add_argument("--jpeg-reencode", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--limit", type=int, help="only the first N images (smoke test)")
    parser.add_argument("--max-excluded-fraction", type=float, default=0.05)
    args = parser.parse_args(argv)

    session, input_name, class_names = ct.load_session(args.model)
    if args.class_name not in class_names:
        raise ValueError(f"{args.class_name!r} is not one of the model's classes {class_names}")
    class_id = class_names.index(args.class_name)

    paths = sorted(p for p in args.images.iterdir() if p.suffix.lower() in ct.IMAGE_SUFFIXES)
    if args.limit:
        paths = paths[:args.limit]
    if not paths:
        raise FileNotFoundError(f"No images found in {args.images}")

    per_image, excluded, unreadable = {}, {}, []
    for n, path in enumerate(paths, start=1):
        try:
            gts, _ = ct.load_ground_truth(args.labels / f"{path.stem}.txt")
        except ct.UnusableLabel as exc:
            excluded[path.name] = str(exc)
            continue
        bgr = cv2.imread(str(path))
        if bgr is None:
            unreadable.append(path.name)
            continue
        model_input = cv2.imdecode(cv2.imencode(".jpg", bgr)[1], cv2.IMREAD_COLOR) if args.jpeg_reencode else bgr
        dets = ct.detect(session, input_name, model_input, FLOOR)
        a = analyse_image(dets, gts, class_id, args.threshold, class_names)
        a.update(path=path, names=class_names, gt_c=gts[gts[:, 0] == class_id], dets=dets,
                 flagged=bool(((dets[:, 0] == class_id) & (dets[:, 1] >= args.threshold)).any()))
        per_image[path.name] = a
        if n % 100 == 0 or n == len(paths):
            print(f"  inference {n}/{len(paths)}", flush=True)
    dropped = len(excluded) + len(unreadable)
    if dropped / len(paths) > args.max_excluded_fraction:
        raise RuntimeError(f"{dropped}/{len(paths)} images excluded - check --images/--labels and the label format")

    summary = summarize(per_image, args.threshold)
    n_with_class = sum(1 for a in per_image.values() if a["n_gt"])
    flagged_wrong = [n for n, a in per_image.items() if a["flagged"] and not a["n_gt"]]
    summary.update(class_name=args.class_name, images_evaluated=len(per_image), images_with_class=n_with_class,
                   images_flagged_without_class=len(flagged_wrong), excluded_labels=excluded, unreadable_images=unreadable,
                   model=args.model.name, jpeg_reencode=args.jpeg_reencode)

    out = args.out_dir / args.class_name
    for group in ("false_positives", "missed"):
        (out / group).mkdir(parents=True, exist_ok=True)
        for old in (out / group).glob("*.jpg"):
            old.unlink()
    groups = {
        "false_positives": sorted((n for n, a in per_image.items() if a["fps"]), key=lambda n: -max(f["conf"] for f in per_image[n]["fps"])),
        "missed": sorted(n for n, a in per_image.items() if a["fns"]),
    }
    for group, names in groups.items():
        saved = []
        for k, name in enumerate(names[:args.max_images]):
            a = per_image[name]
            causes = ", ".join(sorted({f["cause"] for f in (a["fps"] if group == "false_positives" else a["fns"])}))
            image = annotate(cv2.imread(str(a["path"])), a, args.class_name, f"{name} | {causes}")
            cv2.imwrite(str(out / group / f"{k:02d}_{Path(name).stem[:60]}.jpg"), image, [cv2.IMWRITE_JPEG_QUALITY, 88])
            saved.append(image)
        if saved:
            cv2.imwrite(str(out / f"montage_{group}.jpg"), montage(saved), [cv2.IMWRITE_JPEG_QUALITY, 85])
        summary[f"{group}_images"] = names
        summary[f"{group}_saved"] = len(saved)

    (out / "diagnosis.json").write_text(json.dumps(summary, indent=2, default=float))
    _print(summary)
    print(f"\nWrote annotated images, montages and diagnosis.json to {out}")
    return summary


def _print(s: dict) -> None:
    pct = lambda v: "-" if v is None else f"{v:.3f}"  # noqa: E731
    print(f"\n=== {s['class_name']} @ threshold {s['threshold']} ({s['model']}, {s['images_evaluated']} images, "
          f"{s['images_with_class']} contain the class)")
    print(f"instances: TP {s['tp']}  FP {s['fp']}  FN {s['fn']}  ->  precision {pct(s['precision'])}  recall {pct(s['recall'])}")
    print(f"images flagged with the class that do not contain it: {s['images_flagged_without_class']}"
          f"   (images with >=1 FP box: {s['images_with_fp']}, with >=1 missed box: {s['images_with_missed']})")
    print("\nFalse-positive causes:")
    for cause, n in s["fp_causes"].items():
        print(f"  {n:>4}  {cause}")
    print("\nMissed ground-truth boxes, by what the model did there:")
    for cause, n in s["fn_causes"].items():
        print(f"  {n:>4}  {cause}")
    print(f"\nbox size (side in the 640-px model input): found median {s['median_side_px_found']} px, "
          f"missed median {s['median_side_px_missed']} px")
    if s["excluded_labels"] or s["unreadable_images"]:
        print(f"excluded: {len(s['excluded_labels'])} unusable labels, {len(s['unreadable_images'])} unreadable images")


if __name__ == "__main__":
    main()
