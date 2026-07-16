"""Unit tests for scan profile loading and validation (Phase 2/10)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from autofuzz.core.config import AutoFuzzSettings, PluginConfig, ScanProfile, load_profile
from autofuzz.core.errors import ConfigError


def test_load_valid_web_profile(tmp_path: Path) -> None:
    profile_file = tmp_path / "profile.yaml"
    profile_file.write_text("name: quick-web\nengine: web\nauthorized: true\n", encoding="utf-8")

    profile = load_profile(profile_file)

    assert isinstance(profile, ScanProfile)
    assert profile.engine == "web"
    assert profile.authorized is True
    assert profile.scheduler.concurrency == 10


def test_load_missing_profile_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_profile(tmp_path / "does-not-exist.yaml")


def test_load_invalid_yaml_raises_config_error(tmp_path: Path) -> None:
    profile_file = tmp_path / "bad.yaml"
    profile_file.write_text("engine: [unterminated\n", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_profile(profile_file)


def test_load_profile_with_invalid_engine_raises_config_error(tmp_path: Path) -> None:
    profile_file = tmp_path / "bad-engine.yaml"
    profile_file.write_text("name: x\nengine: not-a-real-engine\n", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_profile(profile_file)


def test_scheduler_config_rejects_zero_concurrency() -> None:
    with pytest.raises(ValidationError):
        ScanProfile(name="x", engine="web", scheduler={"concurrency": 0})


def test_plugin_config_defaults_to_all_plugins_enabled() -> None:
    profile = ScanProfile(name="x", engine="web")

    assert profile.plugins.enabled is None
    assert profile.plugins.disabled == []
    assert profile.plugins.options == {}


def test_plugin_config_loads_from_profile(tmp_path: Path) -> None:
    profile_file = tmp_path / "profile.yaml"
    profile_file.write_text(
        "name: x\n"
        "engine: web\n"
        "plugins:\n"
        "  enabled: [web.missing-security-headers]\n"
        "  disabled: []\n"
        "  options:\n"
        "    web.missing-security-headers:\n"
        "      ignore_headers: [x-frame-options]\n",
        encoding="utf-8",
    )

    profile = load_profile(profile_file)

    assert isinstance(profile.plugins, PluginConfig)
    assert profile.plugins.enabled == ["web.missing-security-headers"]
    assert profile.plugins.options["web.missing-security-headers"]["ignore_headers"] == [
        "x-frame-options"
    ]


class TestAutoFuzzSettings:
    def test_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in ("AUTOFUZZ_CONFIG_DIR", "AUTOFUZZ_LOG_LEVEL", "AUTOFUZZ_LOG_JSON"):
            monkeypatch.delenv(var, raising=False)

        settings = AutoFuzzSettings()

        assert settings.log_level == "INFO"
        assert settings.log_json is False
        assert settings.config_dir == Path.home() / ".autofuzz"

    def test_config_dir_env_var_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AUTOFUZZ_CONFIG_DIR", str(tmp_path / "custom"))

        settings = AutoFuzzSettings()

        assert settings.config_dir == tmp_path / "custom"

    def test_config_dir_expands_leading_tilde(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A bare pydantic Path field does not expand "~" on its own - this
        # covers the fix, not just the passthrough case above.
        monkeypatch.setenv("AUTOFUZZ_CONFIG_DIR", "~/.autofuzz-test-only")

        settings = AutoFuzzSettings()

        assert "~" not in str(settings.config_dir)
        assert settings.config_dir == Path.home() / ".autofuzz-test-only"

    def test_log_level_and_json_env_var_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTOFUZZ_LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("AUTOFUZZ_LOG_JSON", "true")

        settings = AutoFuzzSettings()

        assert settings.log_level == "DEBUG"
        assert settings.log_json is True
