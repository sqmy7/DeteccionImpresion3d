import numpy as np

from capture.camera_sources.base import CameraSource


class MjpegCameraSource(CameraSource):
    """Stub - e.g. for ESP32-CAM sources (see project architecture), not needed yet."""

    def __init__(self, source_uri: str) -> None:
        self._source_uri = source_uri

    def open(self) -> None:
        raise NotImplementedError("MJPEG-over-HTTP camera source is not implemented yet")

    def read_frame(self) -> np.ndarray:
        raise NotImplementedError("MJPEG-over-HTTP camera source is not implemented yet")

    def close(self) -> None:
        pass
