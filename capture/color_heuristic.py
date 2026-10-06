import cv2
import numpy as np

# k=1-2 per architecture note - just enough to separate filament from background,
# not a general-purpose color quantizer.
_KMEANS_K = 2
_KMEANS_CRITERIA = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)


def detect_dominant_color_rgb(frame: np.ndarray) -> str:
    """HSV + k-means dominant color estimate for a (typically ROI-cropped) frame,
    returned as '#rrggbb'."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    pixels = hsv.reshape(-1, 3).astype(np.float32)

    k = min(_KMEANS_K, len(pixels))
    _compactness, labels, centers = cv2.kmeans(
        pixels, k, None, _KMEANS_CRITERIA, attempts=3, flags=cv2.KMEANS_PP_CENTERS
    )

    counts = np.bincount(labels.flatten())
    dominant_hsv = centers[np.argmax(counts)]

    dominant_hsv_uint8 = np.uint8([[dominant_hsv]])
    b, g, r = (int(c) for c in cv2.cvtColor(dominant_hsv_uint8, cv2.COLOR_HSV2BGR)[0][0])
    return f"#{r:02x}{g:02x}{b:02x}"
