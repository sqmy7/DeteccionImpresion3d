import numpy as np

from capture.frame_quality import SignalWatch, is_black_frame

BLACK = np.zeros((720, 1280, 3), dtype=np.uint8)
IMAGE = np.full((720, 1280, 3), 114, dtype=np.uint8)  # the mean of a real frame of the printer was 114


def test_black_means_dark_on_average_and_no_bright_pixel():
    assert is_black_frame(BLACK)
    noise = np.random.default_rng(1).integers(0, 4, size=(720, 1280, 3), dtype=np.uint8)  # sensor noise in the dark
    assert is_black_frame(noise)
    assert not is_black_frame(IMAGE)
    dim_room = np.full((720, 1280, 3), 10, dtype=np.uint8)  # dark, but there is a scene
    assert not is_black_frame(dim_room)
    lit = BLACK.copy()
    lit[100:120, 100:120] = 255  # a lit LED on an otherwise black frame is still a picture
    assert not is_black_frame(lit)


def test_an_empty_frame_counts_as_black():
    assert is_black_frame(np.zeros((0, 0, 3), dtype=np.uint8))


def test_signal_is_lost_after_a_run_of_black_frames_and_said_once():
    watch = SignalWatch(frames_to_lose=12, frames_to_recover=3)
    changes = [watch.observe(BLACK) for _ in range(11)]
    assert changes == [None] * 11 and not watch.lost  # a camera that is still starting does not count
    assert watch.observe(BLACK) == "lost" and watch.lost
    assert [watch.observe(BLACK) for _ in range(50)] == [None] * 50  # not repeated at every frame


def test_a_single_dark_frame_among_good_ones_does_not_lose_the_signal():
    watch = SignalWatch()
    sequence = [IMAGE] * 20 + [BLACK] + [IMAGE] * 20
    assert [watch.observe(frame) for frame in sequence] == [None] * len(sequence)


def test_signal_comes_back_after_a_few_good_frames_and_the_run_starts_over():
    watch = SignalWatch(frames_to_lose=12, frames_to_recover=3)
    for _ in range(12):
        watch.observe(BLACK)
    assert watch.lost
    assert [watch.observe(IMAGE), watch.observe(IMAGE)] == [None, None]
    assert watch.observe(IMAGE) == "back" and not watch.lost
    # a black frame in the middle of the recovery resets it
    for _ in range(12):
        watch.observe(BLACK)
    assert [watch.observe(IMAGE), watch.observe(IMAGE), watch.observe(BLACK), watch.observe(IMAGE), watch.observe(IMAGE)] == [None] * 5
    assert watch.lost and watch.observe(IMAGE) == "back"
