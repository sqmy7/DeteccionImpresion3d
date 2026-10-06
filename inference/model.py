import ast

import cv2
import numpy as np
import onnxruntime as ort

from config import settings

_INPUT_SIZE = 640
_IOU_THRESHOLD = 0.45


def _read_class_names(session: ort.InferenceSession) -> list[str]:
    """Class names come from the model itself: Ultralytics embeds them in the ONNX
    metadata as a Python dict literal ("{0: 'spaghetti', 1: 'warping', ...}"). Reading
    them from there means the worker can never disagree with the model about what a
    given class_id means - there is deliberately no hardcoded fallback list, since a
    silent fallback is exactly how a mislabelled detection would go unnoticed."""
    raw = session.get_modelmeta().custom_metadata_map.get("names")
    if raw is None:
        raise RuntimeError("ONNX model has no 'names' metadata - re-export it with Ultralytics, which embeds it")

    names = ast.literal_eval(raw)
    if not isinstance(names, dict) or sorted(names) != list(range(len(names))):
        raise RuntimeError(f"ONNX 'names' metadata must map class ids 0..N-1 to names, got: {raw!r}")
    return [str(names[i]) for i in range(len(names))]


class DefectDetector:
    """Loads the ONNX model once (persistent, per architecture) and runs inference
    per frame.

    Preprocessing is a plain resize to 640x640 (stretching non-square frames), not the
    aspect-preserving letterbox Ultralytics uses at train/val time. Compared on ~13 real
    failed-print photos with the trained INT8 model, letterbox was not clearly better
    (it helped some images and hurt others), so this was left as-is rather than changed
    on thin evidence. The proper way to settle it is to run val on the held-out test
    split with each preprocessing mode - worth doing before trusting per-class numbers.
    """

    def __init__(self, model_path: str) -> None:
        options = ort.SessionOptions()
        options.intra_op_num_threads = settings.intra_op_num_threads
        self._session = ort.InferenceSession(model_path, sess_options=options, providers=["CPUExecutionProvider"])
        self._input_name = self._session.get_inputs()[0].name

        self.class_names = _read_class_names(self._session)
        self._validate_signature()

    def _validate_signature(self) -> None:
        input_shape = self._session.get_inputs()[0].shape
        if input_shape[1:] != [3, _INPUT_SIZE, _INPUT_SIZE]:
            raise RuntimeError(f"Expected model input [N, 3, {_INPUT_SIZE}, {_INPUT_SIZE}], got {input_shape}")

        # (1, 4 box coords + one score per class, num_predictions) for a YOLO11/v8-style export.
        output_shape = self._session.get_outputs()[0].shape
        expected_channels = 4 + len(self.class_names)
        if output_shape[1] != expected_channels:
            raise RuntimeError(
                f"Model output has {output_shape[1]} channels but its metadata lists "
                f"{len(self.class_names)} classes (expected {expected_channels}) - class ids would be misaligned"
            )

    def predict(self, frame: np.ndarray) -> dict:
        tensor = self._preprocess(frame)
        outputs = self._session.run(None, {self._input_name: tensor})
        return self._postprocess(outputs[0])

    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        resized = cv2.resize(frame, (_INPUT_SIZE, _INPUT_SIZE))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        normalized = rgb.astype(np.float32) / 255.0
        chw = normalized.transpose(2, 0, 1)
        return np.expand_dims(chw, axis=0)

    def _postprocess(self, raw_output: np.ndarray) -> dict:
        predictions = raw_output[0].T  # -> (num_predictions, 4 + num_classes)
        boxes = predictions[:, :4]
        class_scores = predictions[:, 4:]

        class_ids = np.argmax(class_scores, axis=1)
        confidences = np.max(class_scores, axis=1)

        keep = confidences >= settings.confidence_threshold
        boxes, class_ids, confidences = boxes[keep], class_ids[keep], confidences[keep]

        indices: np.ndarray = np.array([], dtype=int)
        if len(boxes) > 0:
            nms_boxes = [[float(x - w / 2), float(y - h / 2), float(w), float(h)] for x, y, w, h in boxes]
            raw_indices = cv2.dnn.NMSBoxes(nms_boxes, confidences.tolist(), settings.confidence_threshold, _IOU_THRESHOLD)
            if len(raw_indices) > 0:
                indices = np.array(raw_indices).flatten()

        # box: [x1, y1, x2, y2], normalized 0..1 relative to the 640x640 model input - same
        # convention as inference/training/scripts/calibrate_thresholds.py::detect(), which is
        # the verified-correct reference (its overlays in inspect_false_positives.py are
        # confirmed correctly positioned). Earlier this stored the raw [xc, yc, w, h] in
        # unnormalized 640px space instead - a latent bug that nothing had read back yet.
        detections = []
        for i in indices:
            xc, yc, w, h = (float(v) for v in boxes[i])
            x1, y1 = (xc - w / 2) / _INPUT_SIZE, (yc - h / 2) / _INPUT_SIZE
            x2, y2 = (xc + w / 2) / _INPUT_SIZE, (yc + h / 2) / _INPUT_SIZE
            detections.append(
                {
                    "class": self.class_names[int(class_ids[i])],
                    "confidence": round(float(confidences[i]), 4),
                    "box": [round(max(0.0, min(1.0, v)), 4) for v in (x1, y1, x2, y2)],
                }
            )

        return {
            "has_defect": len(detections) > 0,
            "max_confidence": round(float(confidences[indices].max()), 4) if len(indices) > 0 else None,
            "defect_classes": sorted({d["class"] for d in detections}),
            "raw_output": {"detections": detections},
        }
