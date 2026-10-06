from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    database_url: str
    redis_url: str
    storage_root: Path = ROOT_DIR / "storage" / "snapshots"
    usb_frame_width: int = 1280
    usb_frame_height: int = 720
    # Independent of the per-layer inference capture: how often the continuous background
    # stream (live_stream.py) grabs and publishes a frame for the "actually live" video feed.
    # The C922 tops out around ~10fps at 1280x720 (measured); 6 is comfortably fluid without
    # pushing CPU/JPEG-encode load or competing much with Docker/WSL2 for the one camera thread.
    live_stream_fps: float = 6.0


settings = Settings()
