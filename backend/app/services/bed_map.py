"""Where on the bed a detection is, in millimetres.

Calibration: the user marks the four bed corners on a camera frame. Those four point pairs give the
homography between the image and the bed plane (with exactly four points this is what
cv2.findHomography computes; solved here in plain Python so the backend doesn't need OpenCV).

From the same homography, assuming square pixels and the optical centre in the middle of the image,
the focal length and the camera's position are estimated (Zhang's single-view constraints). The
position corrects parallax: a defect on top of a part at height z is seen where the line of sight
crosses the bed plane, farther from the camera than the defect itself.

On a bed-slinger like the Creality Hi with the camera fixed to the frame or the table, the bed
moves along Y inside the image: the toolhead's Y when the frame was taken, minus its Y at
calibration time, is the shift to add back.

Everything here is pure math, tested against a simulated pinhole camera."""

import math
from dataclasses import dataclass

# Assumed when the focal length can't be recovered from the calibration (a nearly fronto-parallel
# view): the Logitech C922's 78 degree diagonal field of view.
DEFAULT_DIAGONAL_FOV_DEGREES = 78.0
# How far apart in time the frame and the head position can be: Klipper reports every 250 ms and
# the live stream keeps the latest frame at ~6 fps. Only matters when the bed moves in the image.
FRAME_SYNC_SECONDS = 0.3
# Typical error of a hand-marked corner, as a fraction of the bed size.
CLICK_ERROR_FRACTION = 0.015
# A location with a larger estimated error is shown but flagged as unreliable.
RELIABLE_MM = 20.0


Matrix = list[float]  # 3x3, row-major


@dataclass(frozen=True)
class CameraModel:
    focal_px: float
    center: tuple[float, float, float]  # camera position in bed millimetres (calibration pose)
    focal_estimated: bool  # False: taken from DEFAULT_DIAGONAL_FOV_DEGREES


@dataclass(frozen=True)
class Calibration:
    image_to_bed: Matrix  # pixels of a width x height frame -> bed mm on the plane z = 0
    width: int
    height: int
    bed_moves_in_image: bool
    reference_y: float | None  # toolhead Y when the calibration frame was taken
    camera: CameraModel | None
    bed_size: float  # mm, for the click-error estimate


@dataclass(frozen=True)
class BedLocation:
    x: float
    y: float
    uncertainty_mm: float
    parallax_mm: float  # how far the parallax correction moved the point
    shift_mm: float  # bed travel added back on a bed-slinger
    reliable: bool


def solve_homography(src: list[tuple[float, float]], dst: list[tuple[float, float]]) -> Matrix:
    """The 3x3 homography (h33 = 1) mapping four src points onto four dst points, by Gaussian
    elimination with partial pivoting on the usual 8x8 system. Raises ValueError if degenerate."""
    if len(src) != 4 or len(dst) != 4:
        raise ValueError("exactly four point pairs are needed")
    rows = []
    for (x, y), (u, v) in zip(src, dst):
        rows.append([x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y, u])
        rows.append([0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y, v])
    for col in range(8):
        pivot = max(range(col, 8), key=lambda row: abs(rows[row][col]))
        if abs(rows[pivot][col]) < 1e-12:
            raise ValueError("degenerate points (three of them in a line?)")
        rows[col], rows[pivot] = rows[pivot], rows[col]
        for row in range(8):
            if row != col:
                factor = rows[row][col] / rows[col][col]
                rows[row] = [a - factor * b for a, b in zip(rows[row], rows[col])]
    return [rows[i][8] / rows[i][i] for i in range(8)] + [1.0]


def apply_homography(h: Matrix, x: float, y: float) -> tuple[float, float]:
    w = h[6] * x + h[7] * y + h[8]
    if abs(w) < 1e-12:
        raise ValueError("point maps to infinity")
    return (h[0] * x + h[1] * y + h[2]) / w, (h[3] * x + h[4] * y + h[5]) / w


def invert_homography(h: Matrix) -> Matrix:
    a, b, c, d, e, f, g, i, k = h
    adjugate = [
        e * k - f * i, c * i - b * k, b * f - c * e,
        f * g - d * k, a * k - c * g, c * d - a * f,
        d * i - e * g, b * g - a * i, a * e - b * d,
    ]
    det = a * adjugate[0] + b * adjugate[3] + c * adjugate[6]
    if abs(det) < 1e-12:
        raise ValueError("homography is not invertible")
    scale = adjugate[8] if abs(adjugate[8]) > 1e-12 else det
    return [value / scale for value in adjugate]


def _signed_area(points: list[tuple[float, float]]) -> float:
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1])) / 2


def is_convex_in_order(points: list[tuple[float, float]]) -> bool:
    """True if the four points, in the given order, form a convex quadrilateral (no crossing)."""
    signs = []
    for index in range(4):
        (x1, y1), (x2, y2), (x3, y3) = points[index], points[(index + 1) % 4], points[(index + 2) % 4]
        signs.append((x2 - x1) * (y3 - y2) - (y2 - y1) * (x3 - x2))
    return all(sign > 0 for sign in signs) or all(sign < 0 for sign in signs)


def _focal_from_fov(width: int, height: int, diagonal_fov_degrees: float) -> float:
    return math.hypot(width, height) / 2 / math.tan(math.radians(diagonal_fov_degrees) / 2)


def estimate_camera(
    bed_to_pixels: Matrix, width: int, height: int, diagonal_fov_degrees: float = DEFAULT_DIAGONAL_FOV_DEGREES
) -> CameraModel | None:
    """Focal length and camera position from the bed-to-image homography, assuming square pixels
    and the principal point at the image centre. None if the result isn't a camera above the bed."""
    cx, cy = width / 2, height / 2
    # Move the principal point to the origin: G' = T * G.
    g = list(bed_to_pixels)
    g = [
        g[0] - cx * g[6], g[1] - cx * g[7], g[2] - cx * g[8],
        g[3] - cy * g[6], g[4] - cy * g[7], g[5] - cy * g[8],
        g[6], g[7], g[8],
    ]
    g1 = (g[0], g[3], g[6])
    g2 = (g[1], g[4], g[7])
    g3 = (g[2], g[5], g[8])

    # r1 . r2 = 0 and |r1| = |r2| each give an estimate of f^2; keep the better conditioned ones.
    candidates = []
    if abs(g1[2] * g2[2]) > 1e-15:
        candidates.append((-(g1[0] * g2[0] + g1[1] * g2[1]) / (g1[2] * g2[2]), abs(g1[2] * g2[2])))
    if abs(g1[2] ** 2 - g2[2] ** 2) > 1e-15:
        candidates.append(
            ((g2[0] ** 2 + g2[1] ** 2 - g1[0] ** 2 - g1[1] ** 2) / (g1[2] ** 2 - g2[2] ** 2), abs(g1[2] ** 2 - g2[2] ** 2))
        )
    diagonal = math.hypot(width, height)
    plausible = [(f2, weight) for f2, weight in candidates if f2 > 0 and 0.2 * diagonal < math.sqrt(f2) < 5 * diagonal]
    if plausible:
        focal = math.sqrt(sum(f2 * weight for f2, weight in plausible) / sum(weight for _, weight in plausible))
        estimated = True
    else:
        focal = _focal_from_fov(width, height, diagonal_fov_degrees)
        estimated = False

    m1 = (g1[0] / focal, g1[1] / focal, g1[2])
    m2 = (g2[0] / focal, g2[1] / focal, g2[2])
    m3 = (g3[0] / focal, g3[1] / focal, g3[2])
    scale = 2 / (math.hypot(*m1) + math.hypot(*m2))
    if m3[2] * scale < 0:  # the bed must be in front of the camera
        scale = -scale
    r1 = tuple(component * scale for component in m1)
    r2 = tuple(component * scale for component in m2)
    t = tuple(component * scale for component in m3)
    r3 = (r1[1] * r2[2] - r1[2] * r2[1], r1[2] * r2[0] - r1[0] * r2[2], r1[0] * r2[1] - r1[1] * r2[0])
    # Camera centre in world coordinates: C = -R^T t, with R's columns r1, r2, r3.
    center = tuple(-(r[0] * t[0] + r[1] * t[1] + r[2] * t[2]) for r in (r1, r2, r3))
    if center[2] <= 0:
        return None
    return CameraModel(focal_px=focal, center=center, focal_estimated=estimated)


def build_calibration(
    image_points: list[tuple[float, float]],
    bed_points: list[tuple[float, float]],
    width: int,
    height: int,
    bed_moves_in_image: bool,
    reference_y: float | None,
) -> Calibration:
    """image_points are normalized (0..1 of the frame), in the same order as bed_points (mm)."""
    pixels = [(u * width, v * height) for u, v in image_points]
    if not is_convex_in_order(pixels) or not is_convex_in_order(list(bed_points)):
        raise ValueError("the four points must be marked in order around the bed, without crossing")
    if _signed_area(pixels) == 0:
        raise ValueError("the four points are degenerate")
    bed_to_pixels = solve_homography(list(bed_points), pixels)
    xs = [x for x, _ in bed_points]
    ys = [y for _, y in bed_points]
    return Calibration(
        image_to_bed=invert_homography(bed_to_pixels),
        width=width,
        height=height,
        bed_moves_in_image=bed_moves_in_image,
        reference_y=reference_y,
        camera=estimate_camera(bed_to_pixels, width, height),
        bed_size=max(max(xs) - min(xs), max(ys) - min(ys)),
    )


def locate(
    calibration: Calibration,
    u: float,
    v: float,
    *,
    z: float = 0.0,
    toolhead_y: float | None = None,
    speed: float | None = None,
) -> BedLocation:
    """Bed position of the normalized image point (u, v) for a feature at height z (mm), seen
    when the toolhead was at toolhead_y moving at `speed` mm/s."""
    x0, y0 = apply_homography(calibration.image_to_bed, u * calibration.width, v * calibration.height)
    x, y = x0, y0

    camera = calibration.camera
    parallax = 0.0
    parallax_residual = abs(z)  # unknown camera: assume a ~45 degree view, error of the order of z
    if camera is not None and z > 0:
        cx, cy, cz = camera.center
        if z < cz:
            factor = (cz - z) / cz
            x, y = cx + (x0 - cx) * factor, cy + (y0 - cy) * factor
            parallax = math.hypot(x - x0, y - y0)
            # The camera estimate itself is approximate; keep part of the correction as error.
            parallax_residual = 0.15 * parallax if camera.focal_estimated else 0.3 * parallax

    shift = 0.0
    motion = 0.0
    if calibration.bed_moves_in_image:
        if toolhead_y is not None and calibration.reference_y is not None:
            shift = toolhead_y - calibration.reference_y
            y += shift
        else:
            motion = calibration.bed_size  # no way to know where the bed was
        motion += abs(speed or 0.0) * FRAME_SYNC_SECONDS

    click = CLICK_ERROR_FRACTION * calibration.bed_size
    uncertainty = math.sqrt(click**2 + parallax_residual**2 + motion**2)
    return BedLocation(
        x=round(x, 1),
        y=round(y, 1),
        uncertainty_mm=round(uncertainty, 1),
        parallax_mm=round(parallax, 1),
        shift_mm=round(shift, 1),
        reliable=uncertainty <= RELIABLE_MM,
    )


def project_bed_point(
    bed_to_pixels: Matrix, camera: CameraModel, x: float, y: float, z: float
) -> tuple[float, float] | None:
    """Image pixel of a bed point at height z (the inverse of locate's parallax step), used to
    draw object outlines and checks. None if the point is not in front of the camera."""
    cx, cy, cz = camera.center
    if z >= cz:
        return None
    factor = cz / (cz - z)
    return apply_homography(bed_to_pixels, cx + (x - cx) * factor, cy + (y - cy) * factor)
