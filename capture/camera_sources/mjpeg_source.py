import cv2
import numpy as np

from capture.camera_sources.base import CameraSource

# A network camera that stops answering must not block the capture thread forever.
_TIMEOUT_MS = 5000


class MjpegCameraSource(CameraSource):
    """Network camera read through OpenCV's FFmpeg backend. source_uri is a stream URL: MJPEG over
    HTTP (the mjpg-streamer style `/webcam/?action=stream` that Klipper printers usually expose)
    or, through RtspCameraSource, an rtsp:// URL."""

    def __init__(self, source_uri: str) -> None:
        self._source_uri = source_uri
        self._capture: cv2.VideoCapture | None = None

    def open(self) -> None:
        self._capture = cv2.VideoCapture(
            self._source_uri,
            cv2.CAP_FFMPEG,
            [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, _TIMEOUT_MS, cv2.CAP_PROP_READ_TIMEOUT_MSEC, _TIMEOUT_MS],
        )
        if not self._capture.isOpened():
            raise RuntimeError(f"Could not open network camera at '{self._source_uri}'")

    def read_frame(self) -> np.ndarray:
        if self._capture is None:
            raise RuntimeError("Camera not open - call open() first")
        ok, frame = self._capture.read()
        if not ok:
            raise RuntimeError(f"Failed to read frame from network camera '{self._source_uri}'")
        return frame

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
