"""Choosing a USB camera by name instead of by index.

An index ("0") is whatever Windows lists first: plug in another webcam, or unplug the one in use, and "0" is
a different camera with no warning (on 2026-10-08 a generic webcam took the index of the Logitech and the
capture kept reading it). A source_uri of the form "name:C922" picks the connected camera whose name
contains that text, and raises a clear error when none does, so the capture waits (it retries every few
seconds) for the right camera instead of falling back to another one.

Names come from DirectShow (pygrabber), which lists devices in the same order as OpenCV's CAP_DSHOW
backend, so the position in the list is the index to open with that backend. Windows only; the list is
passed in as a function so it can be tested without a camera."""

import logging
import sys
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)

NAME_PREFIX = "name:"


class CameraNotFound(RuntimeError):
    """The named camera is not connected (or cannot be looked up)."""


def list_video_devices() -> list[str]:
    """Friendly names of the video capture devices, in OpenCV CAP_DSHOW index order."""
    if sys.platform != "win32":
        raise CameraNotFound("Selecting a camera by name is only available on Windows: use its index or device path")
    try:
        from pygrabber.dshow_graph import FilterGraph
    except ImportError as error:
        raise CameraNotFound("Selecting a camera by name needs pygrabber (pip install pygrabber)") from error
    return list(FilterGraph().get_input_devices())


@dataclass(frozen=True)
class UsbTarget:
    value: int | str  # what cv2.VideoCapture opens
    directshow: bool  # open with the DirectShow backend (the one the index of a named camera refers to)
    description: str


def resolve_usb_target(source_uri: str, devices: Callable[[], list[str]] = list_video_devices) -> UsbTarget:
    uri = source_uri.strip()
    if uri.lower().startswith(NAME_PREFIX):
        needle = uri[len(NAME_PREFIX):].strip()
        if not needle:
            raise CameraNotFound(f"'{source_uri}' names no camera: write it as name:<part of the camera's name>")
        names = devices()
        matches = [index for index, name in enumerate(names) if needle.lower() in name.lower()]
        if not matches:
            present = ", ".join(f"'{name}'" for name in names) or "none"
            raise CameraNotFound(f"No connected camera has '{needle}' in its name (connected: {present})")
        if len(matches) > 1:
            logger.warning(
                "More than one camera has '%s' in its name (%s): using the first", needle, ", ".join(names[i] for i in matches)
            )
        index = matches[0]
        return UsbTarget(index, True, f"'{names[index]}' (index {index})")
    if uri.isdigit():
        return UsbTarget(int(uri), False, f"index {uri}")
    return UsbTarget(uri, False, f"device '{uri}'")
