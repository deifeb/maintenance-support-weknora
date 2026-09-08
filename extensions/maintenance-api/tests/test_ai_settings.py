from app.core.config import Settings


def test_ai_settings_have_safe_local_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.ai_models_config_path.name == "ai-models.yaml"
    assert settings.ai_remote_enabled is False
    assert settings.ai_default_sensitivity == "INTERNAL"
    assert settings.ai_sse_poll_interval_seconds == 0.25
    assert settings.ai_max_plan_steps == 30
    assert settings.ai_report_export_dir.name == "ai-reports"
    assert settings.weknora_evidence_url is None
