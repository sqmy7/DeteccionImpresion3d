import os

from app.db.models import Camera, CameraSourceType

from capture.camera_sources.base import CameraSource
from capture.camera_sources.mjpeg_source import MjpegCameraSource
from capture.camera_sources.rtsp_source import RtspCameraSource
from capture.camera_sources.synthetic_source import SyntheticCameraSource
from capture.camera_sources.usb_source import UsbCameraSource
from capture.config import settings


def _mock_fill_bgr() -> tuple[int, int, int]:
    # Test-only override so the synthetic source can emit distinct solid colors
    # (for exercising the color heuristic) instead of the default gray. Format: "R,G,B".
    raw = os.environ.get("CAPTURE_MOCK_COLOR_RGB")
    if not raw:
        return (40, 40, 40)
    r, g, b = (int(v) for v in raw.split(","))
    return (b, g, r)


def get_camera_source(camera: Camera) -> CameraSource:
    if os.environ.get("CAPTURE_MOCK_CAMERAS", "").lower() == "true":
        return SyntheticCameraSource(
            label=f"{camera.name} ({camera.role.value})",
            fill_bgr=_mock_fill_bgr(),
            # Optional: path to a real image to replay instead of the synthetic frame (test-only).
            image_path=os.environ.get("CAPTURE_MOCK_IMAGE") or None,
        )

    if camera.source_type == CameraSourceType.usb:
        return UsbCameraSource(camera.source_uri, settings.usb_frame_width, settings.usb_frame_height)
    if camera.source_type == CameraSourceType.rtsp:
        return RtspCameraSource(camera.source_uri)
    if camera.source_type == CameraSourceType.mjpeg_http:
        return MjpegCameraSource(camera.source_uri)

    raise ValueError(f"Unknown camera source_type: {camera.source_type}")
