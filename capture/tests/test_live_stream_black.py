"""The continuous live stream with a camera that delivers black frames, against a simulated camera and Redis."""

import asyncio
import os
import types

import numpy as np
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from capture import live_stream  # noqa: E402

BLACK = np.zeros((72, 128, 3), dtype=np.uint8)
IMAGE = np.full((72, 128, 3), 120, dtype=np.uint8)
CAMERA = types.SimpleNamespace(id=7, name="C922 Principal")


class FakeSource:
    def __init__(self, frames):
        self._frames = list(frames)

    def open(self):
        pass

    def read_frame(self):
        if not self._frames:
            raise RuntimeError("end of the simulated camera")
        return self._frames.pop(0)

    def close(self):
        pass


class FakeRedis:
    def __init__(self):
        self.writes = []

    async def mset(self, mapping):
        self.writes.append(mapping)


def run_stream(monkeypatch, frames):
    fake_redis = FakeRedis()
    monkeypatch.setattr(live_stream.redis, "from_url", lambda *args, **kwargs: fake_redis)
    monkeypatch.setattr(live_stream, "get_camera_source", lambda camera: FakeSource(frames))
    monkeypatch.setattr(live_stream.settings, "live_stream_fps", 1000.0)
    live_stream.live_frames._frames.clear()
    live_stream.live_frames._signal_lost.clear()
    with pytest.raises(RuntimeError, match="end of the simulated camera"):
        asyncio.run(live_stream._stream_once(CAMERA))
    return fake_redis


def test_black_frames_are_not_published_and_the_camera_is_marked_without_signal(monkeypatch):
    fake_redis = run_stream(monkeypatch, [BLACK] * 14)

    assert fake_redis.writes == []  # nothing fresh reaches Redis: the age of the last frame keeps growing
    assert live_stream.live_frames.signal_lost(CAMERA.id) is True
    assert live_stream.live_frames.get_recent(CAMERA.id) is None


def test_good_frames_are_published_and_the_signal_comes_back(monkeypatch, caplog):
    caplog.set_level("INFO")
    fake_redis = run_stream(monkeypatch, [BLACK] * 13 + [IMAGE] * 5)

    assert len(fake_redis.writes) == 5
    assert all(f"latest_frame:{CAMERA.id}" in write and f"latest_frame_at:{CAMERA.id}" in write for write in fake_redis.writes)
    assert live_stream.live_frames.signal_lost(CAMERA.id) is False
    assert live_stream.live_frames.get_recent(CAMERA.id) is not None
    assert caplog.text.count("delivers only black frames") == 1  # said once, not at every frame
    assert caplog.text.count("delivers images again") == 1


def test_a_short_dark_start_does_not_mark_the_camera(monkeypatch):
    fake_redis = run_stream(monkeypatch, [BLACK] * 4 + [IMAGE] * 4)

    assert len(fake_redis.writes) == 4
    assert live_stream.live_frames.signal_lost(CAMERA.id) is False


def test_a_layer_with_no_signal_gets_no_photo_and_does_not_open_the_device_itself(monkeypatch, caplog):
    from capture import capture_worker

    reads = []
    monkeypatch.setattr(capture_worker, "_read_frame_sync", lambda camera: reads.append(camera) or IMAGE)
    live_stream.live_frames.set_signal_lost(CAMERA.id, True)
    try:
        # db and redis are None on purpose: with no signal the function must return before touching either.
        asyncio.run(capture_worker._capture_from_camera(None, None, 1, 2, 3, 4, CAMERA))
    finally:
        live_stream.live_frames.set_signal_lost(CAMERA.id, False)

    assert reads == []
    assert "layer 3 of job 2 has no photo" in caplog.text
