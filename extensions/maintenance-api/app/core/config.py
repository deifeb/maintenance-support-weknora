from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = (SERVICE_ROOT / "data" / "maintenance.db").as_posix()
DEFAULT_AI_CONFIG_DIR = SERVICE_ROOT / "config"
DEFAULT_AI_REPORT_EXPORT_DIR = SERVICE_ROOT / "exports" / "ai-reports"


class Settings(BaseSettings):
    app_name: str = "Maintenance Support API"
    app_version: str = "0.2.0"
    app_env: str = "development"
    app_debug: bool = True
    api_v1_prefix: str = "/api/v1"
    internal_jwt_secret: SecretStr
    internal_jwt_issuer: str = "weknora"
    internal_jwt_audience: str = "maintenance-api"
    internal_jwt_max_lifetime_seconds: int = Field(default=180, ge=1, le=180)
    internal_jwt_clock_skew_seconds: int = Field(default=5, ge=0, le=30)
    database_url: str = Field(
        default=f"sqlite:///{DEFAULT_DATABASE_PATH}",
        description="SQLAlchemy database URL",
    )
    database_echo: bool = False
    max_import_size_mb: int = 10
    max_import_rows_per_sheet: int = 10_000
    demand_worker_count: int = 2
    demand_sync_timeout_seconds: int = 5
    demand_max_pending_tasks: int = 20
    demand_max_monte_carlo_runs: int = 50_000
    demand_max_scenario_stages: int = 100
    demand_max_fleet_groups: int = 500
    demand_max_demand_items: int = 5_000
    demand_result_export_max_rows: int = 100_000

    ai_models_config_path: Path = DEFAULT_AI_CONFIG_DIR / "ai-models.yaml"
    ai_routes_config_path: Path = DEFAULT_AI_CONFIG_DIR / "ai-routes.yaml"
    ai_tools_config_path: Path = DEFAULT_AI_CONFIG_DIR / "ai-tools.yaml"
    ai_prompts_config_path: Path = DEFAULT_AI_CONFIG_DIR / "ai-prompts.yaml"
    ai_review_rules_path: Path = DEFAULT_AI_CONFIG_DIR / "review-rules.yaml"
    ai_report_templates_path: Path = DEFAULT_AI_CONFIG_DIR / "report-templates.yaml"
    ai_remote_enabled: bool = False
    ai_default_sensitivity: str = "INTERNAL"
    ai_sse_poll_interval_seconds: float = 0.25
    ai_sse_heartbeat_seconds: int = 15
    ai_confirmation_ttl_seconds: int = 900
    ai_context_recent_message_count: int = 12
    ai_max_plan_steps: int = 30
    ai_worker_count: int = 2
    ai_max_pending_tasks: int = 20
    ai_model_timeout_seconds: int = 60
    ai_model_max_retries: int = 2
    ai_report_export_dir: Path = DEFAULT_AI_REPORT_EXPORT_DIR
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    openai_compatible_base_url: str | None = None
    openai_compatible_api_key: str | None = None
    openai_compatible_model: str | None = None
    weknora_evidence_url: str | None = None
    weknora_api_key: str | None = None

    @field_validator("internal_jwt_secret")
    @classmethod
    def validate_internal_jwt_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().encode("utf-8")) < 32:
            raise ValueError("internal JWT secret must contain at least 32 UTF-8 bytes")
        return value

    @field_validator("internal_jwt_issuer", "internal_jwt_audience")
    @classmethod
    def validate_internal_jwt_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("internal JWT issuer and audience must not be blank")
        return normalized

    model_config = SettingsConfigDict(
        env_file=SERVICE_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        hide_input_in_errors=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
