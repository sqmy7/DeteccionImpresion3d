from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    database_url: str
    redis_url: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    field_encryption_key: str
    cors_allow_origins: str = "*"
    storage_root: Path = Path("/app/storage/snapshots")
    # Read (GET, rate-limited) the G-code file being printed to tell programmed changes from
    # interventions in the event log. False: those changes show as "external".
    gcode_scan_enabled: bool = True
    # Prepended to the Redis pub/sub channels this backend uses (layer_ready:*, events:*). Empty
    # for the real system; the demo mode (scripts/demo_environment.py) sets one so a second
    # backend on the same Redis never mixes with the real one.
    redis_channel_prefix: str = ""
    # What the spaghetti auto-pause does once three layers in a row show spaghetti:
    #   on   - announce it, count down 15 s and send the pause to Moonraker (the original behaviour);
    #   warn - announce it and log an "auto_pause.would_pause" event, but never send the pause;
    #   off  - do nothing at all (no announcement, no event, no pause).
    # A value that is none of these stops the backend at startup instead of silently pausing (or not).
    auto_pause_mode: str = "on"
    # Which detections open an incident by themselves (without waiting for the auto-pause streak): classes the
    # project calls imminent (docs/META_FINAL.md a.1) seen at or above this confidence. stringing and
    # blob_over_extrusion are cosmetic and never open one. One incident per job and class at most.
    incident_classes: str = "spaghetti,layer_shift"
    incident_min_confidence: float = 0.50

    @property
    def incident_class_list(self) -> list[str]:
        return [name.strip() for name in self.incident_classes.split(",") if name.strip()]

    @field_validator("auto_pause_mode", mode="before")
    @classmethod
    def _known_auto_pause_mode(cls, value: object) -> str:
        mode = str(value).strip().lower()
        if mode not in ("on", "warn", "off"):
            raise ValueError("AUTO_PAUSE_MODE must be on, warn or off")
        return mode


settings = Settings()
