"""The bed-map math against the simulated printer's pinhole camera, whose geometry is known."""

import pytest

from app.services.bed_map import (
    apply_homography,
    build_calibration,
    invert_homography,
    is_convex_in_order,
    locate,
    solve_homography,
)

BED = [(0.0, 0.0), (260.0, 0.0), (260.0, 260.0), (0.0, 260.0)]
WIDTH, HEIGHT = 640, 480


def _clicks(mock, toolhead_y: float) -> list[tuple[float, float]]:
    """The bed corners as a user would mark them on a frame taken with the toolhead at toolhead_y."""
    return [(u / WIDTH, v / HEIGHT) for u, v in (mock.camera_project(x, y, 0.0, toolhead_y) for x, y in BED)]


def _seen_at(mock, x: float, y: float, z: float, toolhead_y: float) -> tuple[float, float]:
    u, v = mock.camera_project(x, y, z, toolhead_y)
    return u / WIDTH, v / HEIGHT


def test_homography_maps_the_four_points_and_inverts():
    image = [(110.0, 440.0), (530.0, 440.0), (450.0, 150.0), (190.0, 150.0)]
    h = solve_homography(BED, image)
    for bed_point, image_point in zip(BED, image):
        assert apply_homography(h, *bed_point) == pytest.approx(image_point)
    assert apply_homography(invert_homography(h), 450.0, 150.0) == pytest.approx((260.0, 260.0))


def test_camera_focal_and_position_are_recovered_from_four_corners(mock_moonraker):
    reference_y = mock_moonraker.NOZZLE_WORLD_Y  # bed and world coordinates coincide
    calibration = build_calibration(_clicks(mock_moonraker, reference_y), BED, WIDTH, HEIGHT, True, reference_y)

    camera = calibration.camera
    assert camera.focal_estimated is True
    assert camera.focal_px == pytest.approx(mock_moonraker.CAMERA_FOCAL_PX, rel=0.01)
    assert camera.center == pytest.approx(mock_moonraker.CAMERA_POSITION, abs=1.0)


@pytest.mark.parametrize("toolhead_y", [20.0, 130.0, 240.0])
@pytest.mark.parametrize("z", [0.0, 12.0, 40.0])
def test_a_point_on_a_part_is_located_on_the_bed(mock_moonraker, toolhead_y, z):
    """Bed-slinger with the camera on the frame: calibrated with the bed at one Y, the frame taken
    with the bed elsewhere, the defect on top of a part z mm high."""
    reference_y = 75.0
    calibration = build_calibration(_clicks(mock_moonraker, reference_y), BED, WIDTH, HEIGHT, True, reference_y)

    for x, y in [(95.0, 130.0), (200.0, 60.0), (40.0, 220.0)]:
        u, v = _seen_at(mock_moonraker, x, y, z, toolhead_y)
        location = locate(calibration, u, v, z=z, toolhead_y=toolhead_y, speed=0.0)
        assert (location.x, location.y) == pytest.approx((x, y), abs=1.0)
        assert location.shift_mm == pytest.approx(toolhead_y - reference_y, abs=0.1)
        assert location.reliable


def test_parallax_is_large_without_the_correction(mock_moonraker):
    calibration = build_calibration(_clicks(mock_moonraker, 130.0), BED, WIDTH, HEIGHT, True, 130.0)
    u, v = _seen_at(mock_moonraker, 95.0, 130.0, 40.0, 130.0)

    naive = locate(calibration, u, v, z=0.0, toolhead_y=130.0)  # as if the defect were on the bed
    corrected = locate(calibration, u, v, z=40.0, toolhead_y=130.0)

    assert abs(naive.y - 130.0) > 20  # tens of millimetres off for a 40 mm tall part
    assert corrected.parallax_mm > 20
    assert corrected.y == pytest.approx(130.0, abs=1.0)


def test_a_moving_bed_makes_the_location_unreliable(mock_moonraker):
    calibration = build_calibration(_clicks(mock_moonraker, 130.0), BED, WIDTH, HEIGHT, True, 130.0)
    u, v = _seen_at(mock_moonraker, 95.0, 130.0, 0.0, 130.0)

    still = locate(calibration, u, v, toolhead_y=130.0, speed=0.0)
    moving = locate(calibration, u, v, toolhead_y=130.0, speed=200.0)
    unknown_y = locate(calibration, u, v, toolhead_y=None)

    assert still.reliable and still.uncertainty_mm < 10
    assert not moving.reliable and moving.uncertainty_mm >= 60
    assert not unknown_y.reliable


def test_camera_riding_on_the_bed_needs_no_shift(mock_moonraker, monkeypatch):
    monkeypatch.setattr(mock_moonraker, "camera_on_bed", True)
    calibration = build_calibration(_clicks(mock_moonraker, 0.0), BED, WIDTH, HEIGHT, False, None)
    u, v = _seen_at(mock_moonraker, 200.0, 60.0, 10.0, 250.0)

    location = locate(calibration, u, v, z=10.0, toolhead_y=250.0)

    assert (location.x, location.y) == pytest.approx((200.0, 60.0), abs=1.0)
    assert location.shift_mm == 0.0


def test_crossed_or_degenerate_marks_are_rejected():
    crossed = [(0.1, 0.9), (0.9, 0.1), (0.9, 0.9), (0.1, 0.1)]
    collinear = [(0.1, 0.5), (0.5, 0.5), (0.9, 0.5), (0.5, 0.9)]
    assert not is_convex_in_order([(u * WIDTH, v * HEIGHT) for u, v in crossed])
    for points in (crossed, collinear):
        with pytest.raises(ValueError):
            build_calibration(points, BED, WIDTH, HEIGHT, True, 0.0)


def test_bed_corners_of_size_zero_are_blamed_on_the_bed_not_on_the_marks():
    good_marks = [(0.2, 0.8), (0.8, 0.8), (0.8, 0.5), (0.2, 0.5)]
    with pytest.raises(ValueError, match="bed corners"):
        build_calibration(good_marks, [(0.0, 0.0)] * 4, WIDTH, HEIGHT, True, 0.0)


def test_bed_size_comes_from_the_mesh_not_from_the_head_travel():
    """Measured on the real Creality Hi: the axes travel 285 x 273 (the cutter sits past the bed), the mesh
    covers 10..250 on both axes and the bed is 260 x 260."""
    from app.services.defect_map import bed_dimensions, default_bed_points

    real = {"axis_maximum": [285.0, 273.0, 310.0, 0.0], "bed_mesh": {"mesh_min": [10.0, 10.0], "mesh_max": [250.0, 250.0]}}
    assert bed_dimensions(real) == (260.0, 260.0)
    assert default_bed_points(real)[2] == (260.0, 260.0)
    assert bed_dimensions({"axis_maximum": [285.0, 273.0]}) == (260.0, 260.0)  # no mesh: the spec size
    assert bed_dimensions({"axis_maximum": [220.0, 220.0]}) == (220.0, 220.0)  # never more than the head can reach
    assert bed_dimensions(None) == (260.0, 260.0)
    # idle after a boot: no mesh loaded, Klipper reports [0, 0] to [0, 0]; that is not a bed size
    idle = {"axis_maximum": [285.0, 273.0, 310.0, 0.0], "bed_mesh": {"mesh_min": [0.0, 0.0], "mesh_max": [0.0, 0.0], "probed_matrix": [[0.0]]}}
    assert bed_dimensions(idle) == (260.0, 260.0)
    assert default_bed_points(idle)[1] == (260.0, 0.0)