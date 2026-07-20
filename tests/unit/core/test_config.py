"""Tests for core.config: defaults, layering, validation."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError as PydanticValidationError

from contexttrading.core.config import (
    AIConfig,
    SessionConfig,
    Settings,
    get_settings,
)
from contexttrading.core.errors import ConfigurationError


class TestDefaults:
    def test_default_settings(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.engine.swing_lookback == 5
        assert settings.sessions.default_timezone == "UTC"
        assert settings.api.port == 8000
        assert settings.storage.backend == "sqlite"
        assert settings.ai.provider == "none"
        assert settings.logging.level == "INFO"

    def test_get_settings_cached(self) -> None:
        assert get_settings() is get_settings()


class TestEnvLayering:
    def test_env_overrides_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CT_API__PORT", "9001")
        monkeypatch.setenv("CT_SESSIONS__DEFAULT_TIMEZONE", "America/New_York")
        settings = Settings(_env_file=None)
        assert settings.api.port == 9001
        assert settings.sessions.default_timezone == "America/New_York"

    def test_env_nested_section(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CT_ENGINE__MIN_CANDLES", "120")
        settings = Settings(_env_file=None)
        assert settings.engine.min_candles == 120


class TestFileLayering:
    def test_from_json_file(self, tmp_path) -> None:
        path = tmp_path / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "sessions": {"default_timezone": "Europe/London"},
                    "engine": {"swing_lookback": 3},
                }
            ),
            encoding="utf-8",
        )
        settings = Settings.from_file(path)
        assert settings.sessions.default_timezone == "Europe/London"
        assert settings.engine.swing_lookback == 3

    def test_from_file_with_overrides(self, tmp_path) -> None:
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"engine": {"swing_lookback": 3}}), encoding="utf-8")
        settings = Settings.from_file(path, engine={"swing_lookback": 7})
        assert settings.engine.swing_lookback == 7

    def test_missing_file_raises(self, tmp_path) -> None:
        with pytest.raises(ConfigurationError) as excinfo:
            Settings.from_file(tmp_path / "nope.json")
        assert excinfo.value.code == "CT-4000"

    def test_unsupported_suffix_raises(self, tmp_path) -> None:
        path = tmp_path / "settings.toml"
        path.write_text("[engine]", encoding="utf-8")
        with pytest.raises(ConfigurationError, match="Unsupported config file suffix"):
            Settings.from_file(path)

    def test_non_mapping_raises(self, tmp_path) -> None:
        path = tmp_path / "settings.json"
        path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        with pytest.raises(ConfigurationError, match="mapping"):
            Settings.from_file(path)

    def test_malformed_json_raises(self, tmp_path) -> None:
        path = tmp_path / "settings.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(ConfigurationError, match="Failed to parse"):
            Settings.from_file(path)


class TestValidation:
    def test_bad_timezone_rejected(self) -> None:
        with pytest.raises(PydanticValidationError, match="Unknown IANA timezone"):
            SessionConfig(default_timezone="Mars/Olympus_Mons")

    def test_tzinfo_resolution(self) -> None:
        from zoneinfo import ZoneInfo

        config = SessionConfig(default_timezone="America/New_York")
        assert isinstance(config.tzinfo(), ZoneInfo)
        assert config.tzinfo().key == "America/New_York"

    def test_session_window_validation(self) -> None:
        valid = SessionConfig(sessions={"london": {"start": "07:00", "end": "10:00"}})
        assert valid.sessions["london"]["start"] == "07:00"

    @pytest.mark.parametrize(
        "window",
        [
            {"start": "25:00", "end": "10:00"},
            {"start": "07:60", "end": "10:00"},
            {"start": "7am", "end": "10:00"},
            {"start": "07:00"},
        ],
    )
    def test_invalid_session_windows(self, window: dict[str, str]) -> None:
        with pytest.raises(PydanticValidationError):
            SessionConfig(sessions={"london": window})

    def test_ai_config_never_stores_key(self) -> None:
        config = AIConfig(api_key_env="MY_SECRET_VAR")
        dumped = json.dumps(config.model_dump())
        assert "MY_SECRET_VAR" in dumped  # only the *name* of the env var
