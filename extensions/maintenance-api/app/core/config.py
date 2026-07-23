from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = (SERVICE_ROOT / "data" / "maintenance.db").as_posix()


class Settings(BaseSettings):
    app_name: str = "Maintenance Support API"
    app_version: str = "0.2.0"
    app_env: str = "development"
    app_debug: bool = True
    api_v1_prefix: str = "/api/v1"
    database_url: str = Field(
        default=f"sqlite:///{DEFAULT_DATABASE_PATH}",
        description="SQLAlchemy database URL",
    )
    database_echo: bool = False
    max_import_size_mb: int = 10
    max_import_rows_per_sheet: int = 10_000

    model_config = SettingsConfigDict(
        env_file=SERVICE_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
