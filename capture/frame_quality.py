"""Telling a camera that delivers images from one that delivers only black.

A webcam that is unplugged and replaced by another, covered, or held by another application can keep
"working" as far as OpenCV is concerned: read() succeeds and returns a black frame. That frame is fresh,
so nothing downstream notices (on 2026-10-08 the web showed a black video as if it were live). Numpy only,
so it can be tested without a camera."""

import numpy as np

# A frame is black when it is both dark on average and has no bright pixel: a dark room still has some
# lit pixel (a LED, the printer's screen); a lens cap or a dead feed has none.
BLACK_MEAN_MAX = 2.0
BLACK_PIXEL_MAX = 24


def is_black_frame(frame: np.ndarray) -> bool:
    if frame is None or frame.size == 0:
        return True
    return float(frame.mean()) < BLACK_MEAN_MAX and int(frame.max()) <= BLACK_PIXEL_MAX


class SignalWatch:
    """Follows a camera frame by frame and says when it loses the signal (only black) or gets it back.

    Losing takes a run of black frames, so the first dark frames of a camera that is still starting do not
    count; getting it back takes only a few good ones. observe() returns "lost" or "back" once per change,
    so the log says it once instead of at every frame."""

    def __init__(self, frames_to_lose: int = 12, frames_to_recover: int = 3) -> None:
        self._frames_to_lose = frames_to_lose
        self._frames_to_recover = frames_to_recover
        self._black_run = 0
        self._good_run = 0
        self.lost = False

    def observe(self, frame: np.ndarray) -> str | None:
        if is_black_frame(frame):
            self._black_run += 1
            self._good_run = 0
            if not self.lost and self._black_run >= self._frames_to_lose:
                self.lost = True
                return "lost"
        else:
            self._good_run += 1
            self._black_run = 0
            if self.lost and self._good_run >= self._frames_to_recover:
                self.lost = False
                return "back"
        return None
