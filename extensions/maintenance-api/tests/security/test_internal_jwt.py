from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

TEST_SECRET = "unit-five-internal-jwt-secret-0001"


def test_settings_require_internal_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INTERNAL_JWT_SECRET", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    assert "internal_jwt_secret" in str(exc_info.value)


def test_settings_reject_short_secret_without_disclosing_it() -> None:
    short_secret = "not-long-enough"

    with pytest.raises(ValidationError) as exc_info:
        Settings(internal_jwt_secret=short_secret, _env_file=None)

    assert short_secret not in str(exc_info.value)
    assert "input_value=" not in str(exc_info.value)
    assert "32 UTF-8 bytes" in str(exc_info.value)


def test_settings_measure_secret_length_in_utf8_bytes() -> None:
    settings = Settings(internal_jwt_secret="密" * 11, _env_file=None)

    assert settings.internal_jwt_secret.get_secret_value() == "密" * 11


def test_settings_hide_valid_secret_in_diagnostics() -> None:
    settings = Settings(internal_jwt_secret=TEST_SECRET, _env_file=None)

    assert TEST_SECRET not in repr(settings)
    assert TEST_SECRET not in repr(settings.model_dump())
    assert str(settings.internal_jwt_secret) == "**********"


@pytest.mark.parametrize("field", ["internal_jwt_issuer", "internal_jwt_audience"])
def test_settings_reject_blank_identity_names(field: str) -> None:
    with pytest.raises(ValidationError):
        Settings(
            internal_jwt_secret=TEST_SECRET,
            **{field: " \t "},
            _env_file=None,
        )


@pytest.mark.parametrize("value", [0, -1, 181])
def test_settings_reject_invalid_max_lifetime(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(
            internal_jwt_secret=TEST_SECRET,
            internal_jwt_max_lifetime_seconds=value,
            _env_file=None,
        )


@pytest.mark.parametrize("value", [-1, 31])
def test_settings_reject_invalid_clock_skew(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(
            internal_jwt_secret=TEST_SECRET,
            internal_jwt_clock_skew_seconds=value,
            _env_file=None,
        )


@pytest.mark.parametrize("value", [1, 180])
def test_settings_accept_bounded_max_lifetime(value: int) -> None:
    settings = Settings(
        internal_jwt_secret=TEST_SECRET,
        internal_jwt_max_lifetime_seconds=value,
        _env_file=None,
    )

    assert settings.internal_jwt_max_lifetime_seconds == value


@pytest.mark.parametrize("value", [0, 5, 30])
def test_settings_accept_bounded_clock_skew(value: int) -> None:
    settings = Settings(
        internal_jwt_secret=TEST_SECRET,
        internal_jwt_clock_skew_seconds=value,
        _env_file=None,
    )

    assert settings.internal_jwt_clock_skew_seconds == value
