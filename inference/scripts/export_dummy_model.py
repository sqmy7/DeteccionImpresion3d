"""One-off dev tool: exports an untrained YOLO11s architecture to ONNX so the
inference worker has something real to load while no trained model exists yet.
Not part of the worker's runtime - needs `ultralytics` installed separately
(pip install ultralytics), which is NOT in inference/requirements.txt on purpose
(it pulls in torch, unnecessary weight for the worker itself).

Once a real trained model is exported from Colab/Kaggle with our actual 6-class
taxonomy, this script (and its output) becomes unnecessary - replace
inference/models/yolo11s_dummy.onnx with the real export and update
main.py's ModelVersion bookkeeping (name/classes) to match.

Usage: pip install ultralytics onnx && python export_dummy_model.py
"""

import shutil
from pathlib import Path

from ultralytics import YOLO

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "models" / "yolo11s_dummy.onnx"


def main() -> None:
    model = YOLO("yolo11s.yaml")  # architecture only, random weights, no download needed
    exported_path = model.export(format="onnx", imgsz=640)
    shutil.copy(exported_path, OUTPUT_PATH)
    print(f"Dummy ONNX model written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
