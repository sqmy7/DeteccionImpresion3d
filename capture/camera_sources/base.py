from abc import ABC, abstractmethod

import numpy as np


class CameraSource(ABC):
    """Common interface for reading a single frame from a camera, regardless of transport.
    Synchronous by design (cv2 is blocking) - callers offload to a thread."""

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def read_frame(self) -> np.ndarray: ...

    @abstractmethod
    def close(self) -> None: ...
