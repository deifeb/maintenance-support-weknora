from app.services.ai_model_runtime import redact_secrets


def test_secret_redaction_masks_tokens_and_keys() -> None:
    raw = (
        "Authorization: Bearer abc api_key=xyz OPENAI_COMPATIBLE_API_KEY=secret WEKNORA_API_KEY=wk"
    )
    redacted = redact_secrets(raw, configured_secrets=("secret", "wk"))
    assert "abc" not in redacted
    assert "xyz" not in redacted
    assert "secret" not in redacted
    assert "WEKNORA_API_KEY=***" in redacted
