import time

import cv2
import numpy as np

from capture.camera_sources.base import CameraSource


class SyntheticCameraSource(CameraSource):
    """Generates a deterministic-looking test frame instead of reading real hardware.
    Not a fourth production source_type - only used when CAPTURE_MOCK_CAMERAS=true,
    for testing the capture pipeline end-to-end without a physical USB camera. Swap back
    to a real camera source_type in the DB once hardware is available; UsbCameraSource
    is already functional for that."""

    def __init__(
        self, label: str, fill_bgr: tuple[int, int, int] = (40, 40, 40), image_path: str | None = None
    ) -> None:
        self._label = label
        self._fill_bgr = fill_bgr
        self._image_path = image_path

    def open(self) -> None:
        pass

    def read_frame(self) -> np.ndarray:
        if self._image_path is not None:
            # Test-only: replay a real photo (e.g. a known print defect) as if a camera saw it,
            # so the whole capture -> worker chain can be exercised with realistic content.
            frame = cv2.imread(self._image_path)
            if frame is None:
                raise RuntimeError(f"CAPTURE_MOCK_IMAGE could not be read: {self._image_path}")
            return frame

        frame = np.full((480, 640, 3), self._fill_bgr, dtype=np.uint8)
        cv2.putText(frame, self._label, (20, 230), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
        cv2.putText(frame, time.strftime("%Y-%m-%d %H:%M:%S"), (20, 270), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        return frame

    def close(self) -> None:
        pass
