import logging

import cv2
import numpy as np

from capture.camera_sources.base import CameraSource

logger = logging.getLogger(__name__)


class UsbCameraSource(CameraSource):
    """Real, functional adapter for USB webcams via cv2.VideoCapture.
    source_uri is a device index ("0", "1", ...) or a device path."""

    def __init__(self, source_uri: str, width: int | None = None, height: int | None = None) -> None:
        self._source_uri = source_uri
        self._width = width
        self._height = height
        self._capture: cv2.VideoCapture | None = None

    def open(self) -> None:
        target = int(self._source_uri) if self._source_uri.isdigit() else self._source_uri
        self._capture = cv2.VideoCapture(target)
        if not self._capture.isOpened():
            raise RuntimeError(f"Could not open USB camera at '{self._source_uri}'")

        if self._width and self._height:
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
            actual = (
                int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            )
            # Webcams silently fall back to their default mode when the requested one isn't honored.
            if actual != (self._width, self._height):
                logger.warning(
                    "USB camera '%s' delivers %sx%s, not the requested %sx%s",
                    self._source_uri,
                    actual[0],
                    actual[1],
                    self._width,
                    self._height,
                )

    def read_frame(self) -> np.ndarray:
        if self._capture is None:
            raise RuntimeError("Camera not open - call open() first")
        ok, frame = self._capture.read()
        if not ok:
            raise RuntimeError(f"Failed to read frame from USB camera '{self._source_uri}'")
        return frame

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
