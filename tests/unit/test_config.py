"""Unit tests for scan profile loading and validation (Phase 2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from autofuzz.core.config import PluginConfig, ScanProfile, load_profile
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
