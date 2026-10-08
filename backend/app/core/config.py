from pathlib import Path

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


settings = Settings()
