"""Unit tests for scan profile loading and validation (Phase 2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from autofuzz.core.config import ScanProfile, load_profile
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
