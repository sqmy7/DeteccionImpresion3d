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


settings = Settings()
