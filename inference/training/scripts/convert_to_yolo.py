"""Converts a source object-detection dataset into our unified 6-class taxonomy,
staging the result under datasets/interim/<dataset_name>/ for merge_datasets.py to
split later.

Only handles sources already in YOLO .txt label format - a Roboflow export with
format="yolov8" already is this, so "conversion" here is really just remapping each
source dataset's own class names onto our 6 classes (and dropping annotations for
classes that don't correspond to any of ours). If a future source uses a genuinely
different annotation format (e.g. COCO JSON, Pascal VOC XML), write a new adapter
function rather than forcing it through this one.

Usage:
    python convert_to_yolo.py \
        --source datasets/raw/roboflow_stringing_v3 \
        --dataset-name stringing_v3 \
        --mapping roboflow_generic \
        --output datasets/interim
"""

import argparse
import json
import shutil
from pathlib import Path

import yaml

# Order matters - must match datasets/dataset.yaml and configs/train_config.yaml.
CLASS_NAMES = [
    "spaghetti",
    "warping",
    "stringing",
    "layer_shift",
    "under_extrusion",
    "blob_over_extrusion",
]
CLASS_TO_INDEX = {name: i for i, name in enumerate(CLASS_NAMES)}

# Per-adapter class-name mapping: source dataset's class name (lowercased) -> our class
# name, or explicit None to drop that class's annotations on purpose. A source class name
# that isn't in here AT ALL also gets dropped (same as None), but with a printed warning -
# use explicit None (not just omitting the key) whenever a class is deliberately excluded,
# so a future reader doesn't mistake it for an oversight.
#
# Matching is case-insensitive: convert() looks up `source_name.strip().lower()`, so keys
# here are always lowercase regardless of how the source dataset capitalizes them (e.g. a
# source class "Layer_shifting" or "Warping" still matches the lowercase keys below).
#
# Verified against 3 real Roboflow Universe datasets (workspace samuel-rodriguez-2vtvz) -
# together they cover all 6 of our classes with real volume:
#   - "3D PRINT DEFECT DETECTION" / 3d-print-defect-detection-6fcmi-drylp (v1, 3612 images,
#     6 classes - the Roboflow UI showed Spanish labels at one point, but the dataset's
#     REAL class names (confirmed from its own data.yaml) are English: blobs (1119),
#     crack (713), Layer_shifting (629), spaghetti (2042), stringing (1924), Warping (805).
#   - "3d print fail detection" / 3d-print-fail-detection-jckut (v1, 1002 images, 4 classes):
#     3D-print-fail-detection (0 annotations - Roboflow's own auto-added project-name
#     class, harmless to drop), crack, spaghetti, stringing.
#   - "Under Extrusion" / under-extrusion-pf0uy-nlyil (v1, 999 images, 1 class): "Under
#     Extrusion" (1414 annotations) - note the space, not an underscore, in the source name.
# See the class-coverage table in README.md for which dataset(s) back each of our 6 classes.
# Everything else below is an unverified best guess for other datasets that might get
# added later - check each new dataset's own data.yaml and extend accordingly.
MAPPINGS: dict[str, dict[str, str | None]] = {
    "roboflow_generic": {
        # --- verified: RVM "3D PRINT DEFECT DETECTION" + "3d print fail detection" + "Under Extrusion" ---
        "blobs": "blob_over_extrusion",
        "layer_shifting": "layer_shift",
        "spaghetti": "spaghetti",
        "stringing": "stringing",
        "warping": "warping",
        "under extrusion": "under_extrusion",  # source name has a space, not an underscore
        "crack": None,  # cracking isn't one of our 6 defect classes - dropped on purpose, in both sources
        "3d-print-fail-detection": None,  # Roboflow's own auto-added project-name class, 0 annotations
        # --- unverified guesses for other/future datasets ---
        "spaghetti_detection": "spaghetti",
        "failure": "spaghetti",
        "print_failure": "spaghetti",
        "print-failure": "spaghetti",
        "warp": "warping",
        "corner_lift": "warping",
        "lifting": "warping",
        "stringer": "stringing",
        "string": "stringing",
        "hair": "stringing",
        "hairs": "stringing",
        "layer_shift": "layer_shift",
        "layer-shift": "layer_shift",
        "layershift": "layer_shift",
        "shifted_layer": "layer_shift",
        "shift": "layer_shift",
        "under_extrusion": "under_extrusion",
        "underextrusion": "under_extrusion",
        "under-extrusion": "under_extrusion",
        "gaps": "under_extrusion",
        "gap": "under_extrusion",
        "blob": "blob_over_extrusion",
        "over_extrusion": "blob_over_extrusion",
        "overextrusion": "blob_over_extrusion",
        "over-extrusion": "blob_over_extrusion",
        "zit": "blob_over_extrusion",
        "zits": "blob_over_extrusion",
    },
}


def _load_source_class_names(source_dir: Path) -> list[str]:
    data_yaml_path = source_dir / "data.yaml"
    if not data_yaml_path.is_file():
        raise FileNotFoundError(
            f"No data.yaml found in {source_dir} - expected a Roboflow YOLO export. "
            "If this source uses a different format, write a new adapter instead of forcing it through this one."
        )
    with data_yaml_path.open() as f:
        data = yaml.safe_load(f)

    names = data["names"]
    if isinstance(names, dict):
        return [names[i] for i in sorted(names)]
    return list(names)


def _find_split_dirs(source_dir: Path) -> list[Path]:
    # Roboflow exports train/valid/test (sometimes "val" instead of "valid") as
    # top-level dirs, each with its own images/ + labels/. We pool all of them here -
    # merge_datasets.py re-splits by sequence itself, so Roboflow's own per-image split
    # isn't trustworthy for our leakage-avoidance goal.
    candidates = ["train", "valid", "val", "test"]
    return [source_dir / name for name in candidates if (source_dir / name / "images").is_dir()]


def convert(source_dir: Path, dataset_name: str, mapping_name: str, output_dir: Path) -> None:
    mapping = MAPPINGS.get(mapping_name)
    if mapping is None:
        raise ValueError(f"Unknown mapping '{mapping_name}'. Known mappings: {list(MAPPINGS)}")

    source_class_names = _load_source_class_names(source_dir)

    index_map: dict[int, int | None] = {}
    for source_idx, source_name in enumerate(source_class_names):
        our_name = mapping.get(source_name.strip().lower())
        if our_name is None:
            print(f"  [warn] source class '{source_name}' (idx {source_idx}) has no mapping entry - its annotations will be dropped")
            index_map[source_idx] = None
        else:
            index_map[source_idx] = CLASS_TO_INDEX[our_name]

    out_images = output_dir / dataset_name / "images"
    out_labels = output_dir / dataset_name / "labels"
    out_images.mkdir(parents=True, exist_ok=True)
    out_labels.mkdir(parents=True, exist_ok=True)

    split_dirs = _find_split_dirs(source_dir)
    if not split_dirs:
        raise FileNotFoundError(f"No train/valid/val/test split with an images/ folder found under {source_dir}")

    total_images = 0
    total_boxes_kept = 0
    total_boxes_dropped = 0

    for split_dir in split_dirs:
        images_dir = split_dir / "images"
        labels_dir = split_dir / "labels"
        for image_path in sorted(images_dir.iterdir()):
            if image_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                continue

            label_path = labels_dir / (image_path.stem + ".txt")
            kept_lines = []
            if label_path.is_file():
                for line in label_path.read_text().splitlines():
                    parts = line.split()
                    if not parts:
                        continue
                    source_class_idx = int(parts[0])
                    our_idx = index_map.get(source_class_idx)
                    if our_idx is None:
                        total_boxes_dropped += 1
                        continue
                    kept_lines.append(" ".join([str(our_idx), *parts[1:]]))
                    total_boxes_kept += 1

            # Prefixed with the split name so Roboflow's own train/valid/test folders
            # don't collide once pooled together.
            out_stem = f"{split_dir.name}_{image_path.stem}"
            shutil.copy2(image_path, out_images / f"{out_stem}{image_path.suffix}")
            (out_labels / f"{out_stem}.txt").write_text("\n".join(kept_lines))
            total_images += 1

    manifest = {
        "dataset_name": dataset_name,
        "source": str(source_dir),
        "mapping": mapping_name,
        "images": total_images,
        "boxes_kept": total_boxes_kept,
        "boxes_dropped": total_boxes_dropped,
    }
    (output_dir / dataset_name / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Converted '{dataset_name}': {total_images} images, {total_boxes_kept} boxes kept, {total_boxes_dropped} dropped")
    print(f"  -> {output_dir / dataset_name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, type=Path, help="Path to the downloaded source dataset (Roboflow YOLO export root)")
    parser.add_argument("--dataset-name", required=True, help="Short name for this dataset, used as its sequence-id prefix downstream")
    parser.add_argument("--mapping", default="roboflow_generic", help=f"Which class mapping to use. Options: {list(MAPPINGS)}")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "datasets" / "interim")
    args = parser.parse_args()

    convert(args.source, args.dataset_name, args.mapping, args.output)


if __name__ == "__main__":
    main()
