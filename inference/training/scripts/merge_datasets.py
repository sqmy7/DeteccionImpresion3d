"""Merges every dataset already converted by convert_to_yolo.py (under datasets/interim/)
into the final datasets/processed/{images,labels}/{train,val,test}/ split.

Splits by SEQUENCE, not by individual image: near-duplicate consecutive frames from
the same source video/recording must land entirely in one split, or validation/test
numbers become optimistic nonsense (the model would effectively be tested on frames
it already half-memorized from training). A sequence id is derived by stripping a
trailing frame number off each image's filename stem, scoped to its source dataset
name - e.g. "video1_frame001" and "video1_frame002" both become the sequence
"stringing_v3::video1"; a genuinely standalone image with no trailing number becomes
its own singleton sequence (fine - there's no leakage risk for an independent image).

The split is also approximately stratified by class: rarer classes (stringing is the
one this project cares most about) are placed across train/val/test first, greedily
balancing toward the target ratio, before leftover unannotated/common sequences fill
in the remaining ratio. This is a pragmatic greedy approximation of multi-label
stratification, not the full iterative-stratification algorithm - good enough for a
handful of source datasets, not meant to be a general-purpose solution.

Usage:
    python merge_datasets.py --interim datasets/interim --output datasets/processed
"""

import argparse
import random
import re
import shutil
from collections import defaultdict
from pathlib import Path

CLASS_NAMES = [
    "spaghetti",
    "warping",
    "stringing",
    "layer_shift",
    "under_extrusion",
    "blob_over_extrusion",
]

_TRAILING_NUMBER_RE = re.compile(r"^(.*?)[_\-]?\d+$")


def _sequence_id(dataset_name: str, image_stem: str) -> str:
    match = _TRAILING_NUMBER_RE.match(image_stem)
    base = match.group(1) if match and match.group(1) else image_stem
    return f"{dataset_name}::{base}"


def _parse_classes_in_label(label_path: Path) -> set[int]:
    if not label_path.is_file():
        return set()
    classes = set()
    for line in label_path.read_text().splitlines():
        parts = line.split()
        if parts:
            classes.add(int(parts[0]))
    return classes


def _collect_sequences(interim_dir: Path) -> dict[str, list[tuple[Path, Path]]]:
    sequences: dict[str, list[tuple[Path, Path]]] = defaultdict(list)

    dataset_dirs = [d for d in interim_dir.iterdir() if d.is_dir()]
    if not dataset_dirs:
        raise FileNotFoundError(f"No converted datasets found under {interim_dir} - run convert_to_yolo.py first")

    for dataset_dir in dataset_dirs:
        images_dir = dataset_dir / "images"
        labels_dir = dataset_dir / "labels"
        for image_path in sorted(images_dir.iterdir()):
            label_path = labels_dir / (image_path.stem + ".txt")
            seq_id = _sequence_id(dataset_dir.name, image_path.stem)
            sequences[seq_id].append((image_path, label_path))

    return sequences


def stratified_split(
    sequences: dict[str, list[tuple[Path, Path]]], ratios: tuple[float, float, float], seed: int
) -> dict[str, str]:
    rng = random.Random(seed)
    train_ratio, val_ratio, test_ratio = ratios
    splits = ("train", "val", "test")
    targets = {"train": train_ratio, "val": val_ratio, "test": test_ratio}

    sequence_classes: dict[str, set[int]] = {}
    class_to_sequences: dict[int, list[str]] = defaultdict(list)
    for seq_id, items in sequences.items():
        classes_in_seq: set[int] = set()
        for _image_path, label_path in items:
            classes_in_seq |= _parse_classes_in_label(label_path)
        sequence_classes[seq_id] = classes_in_seq
        for class_id in classes_in_seq:
            class_to_sequences[class_id].append(seq_id)

    assignment: dict[str, str] = {}
    split_class_counts = {split: defaultdict(int) for split in splits}

    # Rarest class first - gets first pick at balanced placement while the most
    # sequences are still unassigned.
    classes_by_rarity = sorted(class_to_sequences, key=lambda c: len(class_to_sequences[c]))

    for class_id in classes_by_rarity:
        seq_ids = [s for s in class_to_sequences[class_id] if s not in assignment]
        rng.shuffle(seq_ids)
        for seq_id in seq_ids:
            total_so_far = sum(split_class_counts[s][class_id] for s in splits) + 1
            deficits = {s: targets[s] * total_so_far - split_class_counts[s][class_id] for s in splits}
            best_split = max(deficits, key=deficits.get)
            assignment[seq_id] = best_split
            for c in sequence_classes[seq_id]:
                split_class_counts[best_split][c] += 1

    # Sequences with no annotations at all (background-only images) - plain ratio split.
    remaining = [s for s in sequences if s not in assignment]
    rng.shuffle(remaining)
    n_train = int(len(remaining) * train_ratio)
    n_val = int(len(remaining) * val_ratio)
    for i, seq_id in enumerate(remaining):
        assignment[seq_id] = "train" if i < n_train else "val" if i < n_train + n_val else "test"

    return assignment


def merge(interim_dir: Path, output_dir: Path, ratios: tuple[float, float, float], seed: int) -> None:
    sequences = _collect_sequences(interim_dir)
    assignment = stratified_split(sequences, ratios, seed)

    for split in ("train", "val", "test"):
        (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    split_image_counts = {"train": 0, "val": 0, "test": 0}
    split_class_counts = {"train": defaultdict(int), "val": defaultdict(int), "test": defaultdict(int)}

    for seq_id, items in sequences.items():
        split = assignment[seq_id]
        for image_path, label_path in items:
            dest_image = output_dir / "images" / split / image_path.name
            dest_label = output_dir / "labels" / split / (image_path.stem + ".txt")
            shutil.copy2(image_path, dest_image)
            dest_label.write_text(label_path.read_text() if label_path.is_file() else "")

            split_image_counts[split] += 1
            for class_id in _parse_classes_in_label(label_path):
                split_class_counts[split][class_id] += 1

    print(f"\n{len(sequences)} sequences -> {sum(split_image_counts.values())} images total\n")
    header = f"{'split':<8}{'images':<10}" + "".join(f"{name:<20}" for name in CLASS_NAMES)
    print(header)
    for split in ("train", "val", "test"):
        row = f"{split:<8}{split_image_counts[split]:<10}"
        row += "".join(f"{split_class_counts[split][i]:<20}" for i in range(len(CLASS_NAMES)))
        print(row)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--interim", type=Path, default=Path(__file__).resolve().parents[1] / "datasets" / "interim")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "datasets" / "processed")
    parser.add_argument("--train", type=float, default=0.7)
    parser.add_argument("--val", type=float, default=0.15)
    parser.add_argument("--test", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    merge(args.interim, args.output, (args.train, args.val, args.test), args.seed)


if __name__ == "__main__":
    main()
