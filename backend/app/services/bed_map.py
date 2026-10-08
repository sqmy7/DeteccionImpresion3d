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
# A mark whose reprojection error exceeds this fraction of the bed size (three times the typical
# click error) is flagged: the camera model cannot explain it, so it is probably off its corner.
FAR_MARK_FRACTION = 3 * CLICK_ERROR_FRACTION
# An estimated focal this far from the camera's known one is flagged (fraction of the known one).
UNUSUAL_FOCAL_FRACTION = 0.25


Matrix = list[float]  # 3x3, row-major


@dataclass(frozen=True)
class CameraModel:
    focal_px: float
    center: tuple[float, float, float]  # camera position in bed millimetres (calibration pose)
    # "estimated" from the marks, "assumed" from DEFAULT_DIAGONAL_FOV_DEGREES (the marks could not
    # give one), or "fixed": a known focal given by the user.
    focal_source: str

    @property
    def focal_estimated(self) -> bool:
        return self.focal_source == "estimated"


@dataclass(frozen=True)
class MarkError:
    """How far the pinhole model (this focal, the pose recovered from the four marks) puts a bed
    corner from where the user marked it. The homography itself fits four points exactly, so this
    error comes only from the camera model: the larger it is, the less the four marks agree with a
    camera of that focal."""

    error_px: float
    error_mm: float  # the same gap, measured on the bed plane


@dataclass(frozen=True)
class Calibration:
    image_to_bed: Matrix  # pixels of a width x height frame -> bed mm on the plane z = 0
    width: int
    height: int
    bed_moves_in_image: bool
    reference_y: float | None  # toolhead Y when the calibration frame was taken
    camera: CameraModel | None
    bed_size: float  # mm, for the click-error estimate
    marks: tuple[MarkError, ...] | None = None  # one per mark, in order; None without a camera model


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


def typical_focal_px(width: int, height: int, diagonal_fov_degrees: float = DEFAULT_DIAGONAL_FOV_DEGREES) -> float:
    """The known focal of the Logitech C922 at this resolution (~907 px at 1280x720)."""
    return _focal_from_fov(width, height, diagonal_fov_degrees)


def _orthonormal_pair(a: tuple[float, float, float], b: tuple[float, float, float]):
    """The closest orthonormal pair to two vectors that are nearly so, splitting the error evenly
    between them (the vectors are the first two columns of a rotation estimated from noisy marks)."""

    def unit(v):
        norm = math.sqrt(sum(c * c for c in v)) or 1.0
        return tuple(c / norm for c in v)

    a, b = unit(a), unit(b)
    total = unit(tuple(x + y for x, y in zip(a, b)))
    difference = unit(tuple(x - y for x, y in zip(a, b)))
    r1 = tuple((x + y) / math.sqrt(2) for x, y in zip(total, difference))
    r2 = tuple((x - y) / math.sqrt(2) for x, y in zip(total, difference))
    return r1, r2


def _rotate(vector, axis_angle):
    """Rodrigues' rotation of `vector` about the axis_angle vector (radians)."""
    angle = math.sqrt(sum(c * c for c in axis_angle))
    if angle < 1e-12:
        return vector
    k = tuple(c / angle for c in axis_angle)
    cos, sin = math.cos(angle), math.sin(angle)
    dot = sum(a * b for a, b in zip(k, vector))
    cross = (k[1] * vector[2] - k[2] * vector[1], k[2] * vector[0] - k[0] * vector[2], k[0] * vector[1] - k[1] * vector[0])
    return tuple(v * cos + c * sin + a * dot * (1 - cos) for v, c, a in zip(vector, cross, k))


def _solve_linear(matrix, vector):
    n = len(vector)
    rows = [list(matrix[i]) + [vector[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(rows[row][col]))
        if abs(rows[pivot][col]) < 1e-18:
            return None
        rows[col], rows[pivot] = rows[pivot], rows[col]
        for row in range(n):
            if row != col:
                factor = rows[row][col] / rows[col][col]
                rows[row] = [a - factor * b for a, b in zip(rows[row], rows[col])]
    return [rows[i][n] / rows[i][i] for i in range(n)]


def _reprojection_residuals(params, base, focal, cx, cy, bed_points, pixels):
    r1, r2, t = base
    omega, shift = params[:3], params[3:]
    c1, c2 = _rotate(r1, omega), _rotate(r2, omega)
    t = tuple(a + b for a, b in zip(t, shift))
    residuals = []
    for (x, y), (mark_u, mark_v) in zip(bed_points, pixels):
        depth = c1[2] * x + c2[2] * y + t[2]
        if depth <= 1e-9:
            return None
        residuals.append(cx + focal * (c1[0] * x + c2[0] * y + t[0]) / depth - mark_u)
        residuals.append(cy + focal * (c1[1] * x + c2[1] * y + t[1]) / depth - mark_v)
    return residuals


def _refine_pose(pose, focal, cx, cy, bed_points, pixels):
    """Least-squares pose for a known focal: minimises the pixel distance between the four marks
    and the reprojected corners (Levenberg-Marquardt over a rotation and a translation). The
    decomposition of the homography fits one corner exactly and leaves the others the error; this
    spreads it, so the mark that is off stands out as the one with the largest residual."""
    base = pose
    params = [0.0] * 6
    residuals = _reprojection_residuals(params, base, focal, cx, cy, bed_points, pixels)
    if residuals is None:
        return pose
    cost = sum(r * r for r in residuals)
    damping = 1e-3
    for _ in range(60):
        if cost < 1e-9:
            break
        jacobian = []
        for index in range(6):
            step = 1e-6 if index < 3 else 1e-3
            shifted = list(params)
            shifted[index] += step
            other = _reprojection_residuals(shifted, base, focal, cx, cy, bed_points, pixels)
            if other is None:
                return _apply_params(base, params)
            jacobian.append([(a - b) / step for a, b in zip(other, residuals)])
        normal = [[sum(a * b for a, b in zip(jacobian[i], jacobian[j])) for j in range(6)] for i in range(6)]
        gradient = [sum(a * r for a, r in zip(jacobian[i], residuals)) for i in range(6)]
        improved = False
        for _ in range(12):
            damped = [[normal[i][j] + (damping * (normal[i][i] + 1e-9) if i == j else 0.0) for j in range(6)] for i in range(6)]
            delta = _solve_linear(damped, [-g for g in gradient])
            if delta is None:
                damping *= 10
                continue
            trial = [p + d for p, d in zip(params, delta)]
            trial_residuals = _reprojection_residuals(trial, base, focal, cx, cy, bed_points, pixels)
            trial_cost = sum(r * r for r in trial_residuals) if trial_residuals else float("inf")
            if trial_cost < cost:
                params, residuals, cost = trial, trial_residuals, trial_cost
                damping = max(damping / 10, 1e-9)
                improved = True
                break
            damping *= 10
        if not improved:
            break
    return _apply_params(base, params)


def _apply_params(base, params):
    r1, r2, t = base
    omega = params[:3]
    return _rotate(r1, omega), _rotate(r2, omega), tuple(a + b for a, b in zip(t, params[3:]))


def estimate_camera(
    bed_to_pixels: Matrix,
    width: int,
    height: int,
    diagonal_fov_degrees: float = DEFAULT_DIAGONAL_FOV_DEGREES,
    fixed_focal_px: float | None = None,
) -> CameraModel | None:
    """Focal length and camera position from the bed-to-image homography, assuming square pixels
    and the principal point at the image centre. With fixed_focal_px the focal is a known value
    and only the position is derived. None if the result isn't a camera above the bed."""
    pose = _camera_pose(bed_to_pixels, width, height, diagonal_fov_degrees, fixed_focal_px)
    return pose[0] if pose else None


def _camera_pose(
    bed_to_pixels, width, height, diagonal_fov_degrees=DEFAULT_DIAGONAL_FOV_DEGREES, fixed_focal_px=None, marks=None
):
    """(CameraModel, (r1, r2, t)) with the rotation columns made orthonormal, or None. With
    `marks` (bed points, pixels) the pose is then refined by least squares over the four marks."""
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

    diagonal = math.hypot(width, height)
    if fixed_focal_px is not None:
        if not 0.2 * diagonal < fixed_focal_px < 5 * diagonal:
            raise ValueError("the known focal length is out of any plausible range for this image size")
        focal, source = float(fixed_focal_px), "fixed"
    else:
        # r1 . r2 = 0 and |r1| = |r2| each give an estimate of f^2; keep the better conditioned ones.
        candidates = []
        if abs(g1[2] * g2[2]) > 1e-15:
            candidates.append((-(g1[0] * g2[0] + g1[1] * g2[1]) / (g1[2] * g2[2]), abs(g1[2] * g2[2])))
        if abs(g1[2] ** 2 - g2[2] ** 2) > 1e-15:
            candidates.append(
                ((g2[0] ** 2 + g2[1] ** 2 - g1[0] ** 2 - g1[1] ** 2) / (g1[2] ** 2 - g2[2] ** 2), abs(g1[2] ** 2 - g2[2] ** 2))
            )
        plausible = [(f2, weight) for f2, weight in candidates if f2 > 0 and 0.2 * diagonal < math.sqrt(f2) < 5 * diagonal]
        if plausible:
            focal, source = math.sqrt(sum(f2 * weight for f2, weight in plausible) / sum(weight for _, weight in plausible)), "estimated"
        else:
            focal, source = _focal_from_fov(width, height, diagonal_fov_degrees), "assumed"

    m1 = (g1[0] / focal, g1[1] / focal, g1[2])
    m2 = (g2[0] / focal, g2[1] / focal, g2[2])
    m3 = (g3[0] / focal, g3[1] / focal, g3[2])
    scale = 2 / (math.hypot(*m1) + math.hypot(*m2))
    if m3[2] * scale < 0:  # the bed must be in front of the camera
        scale = -scale
    r1, r2 = _orthonormal_pair(tuple(c * scale for c in m1), tuple(c * scale for c in m2))
    t = tuple(component * scale for component in m3)
    if marks is not None:
        r1, r2, t = _refine_pose((r1, r2, t), focal, cx, cy, marks[0], marks[1])
    r3 = (r1[1] * r2[2] - r1[2] * r2[1], r1[2] * r2[0] - r1[0] * r2[2], r1[0] * r2[1] - r1[1] * r2[0])
    # Camera centre in world coordinates: C = -R^T t, with R's columns r1, r2, r3.
    center = tuple(-(r[0] * t[0] + r[1] * t[1] + r[2] * t[2]) for r in (r1, r2, r3))
    if center[2] <= 0:
        return None
    return CameraModel(focal_px=focal, center=center, focal_source=source), (r1, r2, t)


def mark_errors(
    pose, focal: float, width: int, height: int, bed_points, pixels, image_to_bed: Matrix
) -> tuple[MarkError, ...] | None:
    """Reproject each bed corner with the pinhole model and compare with the mark."""
    r1, r2, t = pose
    cx, cy = width / 2, height / 2
    errors = []
    for (x, y), (mark_u, mark_v) in zip(bed_points, pixels):
        depth = r1[2] * x + r2[2] * y + t[2]
        if depth <= 1e-9:
            return None
        u = cx + focal * (r1[0] * x + r2[0] * y + t[0]) / depth
        v = cy + focal * (r1[1] * x + r2[1] * y + t[1]) / depth
        bed_x, bed_y = apply_homography(image_to_bed, u, v)
        errors.append(MarkError(error_px=math.hypot(u - mark_u, v - mark_v), error_mm=math.hypot(bed_x - x, bed_y - y)))
    return tuple(errors)


def build_calibration(
    image_points: list[tuple[float, float]],
    bed_points: list[tuple[float, float]],
    width: int,
    height: int,
    bed_moves_in_image: bool,
    reference_y: float | None,
    fixed_focal_px: float | None = None,
) -> Calibration:
    """image_points are normalized (0..1 of the frame), in the same order as bed_points (mm).
    fixed_focal_px: the camera's known focal length in pixels (not estimated from the marks)."""
    pixels = [(u * width, v * height) for u, v in image_points]
    if not is_convex_in_order(list(bed_points)):
        raise ValueError("the bed corners (bed_points) do not form a quadrilateral: the bed size is zero or the corners are repeated")
    if not is_convex_in_order(pixels):
        raise ValueError("the four points must be marked in order around the bed, without crossing")
    if _signed_area(pixels) == 0:
        raise ValueError("the four points are degenerate")
    bed_to_pixels = solve_homography(list(bed_points), pixels)
    image_to_bed = invert_homography(bed_to_pixels)
    xs = [x for x, _ in bed_points]
    ys = [y for _, y in bed_points]
    pose = _camera_pose(bed_to_pixels, width, height, fixed_focal_px=fixed_focal_px, marks=(list(bed_points), pixels))
    camera = pose[0] if pose else None
    marks = mark_errors(pose[1], camera.focal_px, width, height, bed_points, pixels, image_to_bed) if pose else None
    return Calibration(
        image_to_bed=image_to_bed,
        width=width,
        height=height,
        bed_moves_in_image=bed_moves_in_image,
        reference_y=reference_y,
        camera=camera,
        bed_size=max(max(xs) - min(xs), max(ys) - min(ys)),
        marks=marks,
    )


def calibration_warnings(calibration: Calibration) -> list[str]:
    """Codes the web explains (see CalibrationPage). The marks' reprojection error is judged on the
    bed plane: more than FAR_MARK_FRACTION of the bed means the model cannot place that mark."""
    camera = calibration.camera
    if camera is None:
        return ["camera_not_estimated"]
    warnings = []
    if camera.focal_source == "assumed":
        warnings.append("focal_assumed")
    elif camera.focal_source == "fixed":
        warnings.append("focal_fixed")
    else:
        typical = typical_focal_px(calibration.width, calibration.height)
        if abs(camera.focal_px - typical) > UNUSUAL_FOCAL_FRACTION * typical:
            warnings.append("focal_unusual")
    if calibration.marks and any(mark.error_mm > FAR_MARK_FRACTION * calibration.bed_size for mark in calibration.marks):
        warnings.append("mark_far_from_corner")
    return warnings


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
            parallax_residual = 0.3 * parallax if camera.focal_source == "assumed" else 0.15 * parallax

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
