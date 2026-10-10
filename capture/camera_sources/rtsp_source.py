import os

from capture.camera_sources.mjpeg_source import MjpegCameraSource


class RtspCameraSource(MjpegCameraSource):
    """RTSP camera through the same FFmpeg-backed reader, over TCP: RTSP's default UDP transport
    drops and smears frames on a busy Wi-Fi network."""

    def open(self) -> None:
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
        super().open()
