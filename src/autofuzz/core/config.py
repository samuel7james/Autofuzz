"""Configuration models and scan-profile loading.

A ``ScanProfile`` is a named, validated, YAML-loadable set of parameters for
one scan. It replaces v1's module-level constants (``TARGET_HOST``,
``TARGET_PORT``, ``BASE_SEQUENCE``, ...) with a single, typed, testable
object shared by both engines.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from autofuzz.core.errors import ConfigError


class SchedulerConfig(BaseModel):
    """Concurrency, rate limiting, and retry behavior shared by both engines."""

    concurrency: int = Field(default=10, ge=1, le=500)
    rate_limit_per_second: float = Field(default=20.0, gt=0)
    max_retries: int = Field(default=2, ge=0, le=10)
    retry_backoff_seconds: float = Field(default=1.0, gt=0)
    request_timeout_seconds: float = Field(default=10.0, gt=0)


class WebEngineConfig(BaseModel):
    """Parameters specific to the Web Assessment Engine (implemented in Phase 4)."""

    max_crawl_depth: int = Field(default=3, ge=0, le=20)
    max_pages: int = Field(default=500, ge=1)
    follow_redirects: bool = True
    respect_robots_txt: bool = True
    user_agent: str = "AutoFuzz/2.0 (+authorized-security-assessment)"


class ProtocolEngineConfig(BaseModel):
    """Parameters specific to the Protocol Fuzzing Engine (implemented in Phase 3/5)."""

    adapter: str = "ftp"
    target_host: str = "127.0.0.1"
    target_port: int = 21
    iterations: int = Field(default=1000, ge=1)
    target_controller: Literal["docker", "none"] = "none"
    docker_container_name: str | None = None


class PluginConfig(BaseModel):
    """Plugin enable/disable and per-plugin option overrides for one scan."""

    enabled: list[str] | None = Field(
        default=None,
        description=(
            "If set, only these plugin ids run (allow-list). None means all registered plugins run."
        ),
    )
    disabled: list[str] = Field(default_factory=list)
    options: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ScanProfile(BaseModel):
    """A named, loadable set of scan parameters for one engine."""

    name: str
    engine: Literal["web", "proto"]
    authorized: bool = Field(
        default=False,
        description=(
            "Must be explicitly set to true in the profile. Confirms the "
            "operator has authorization to test the configured target."
        ),
    )
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    web: WebEngineConfig = Field(default_factory=WebEngineConfig)
    protocol: ProtocolEngineConfig = Field(default_factory=ProtocolEngineConfig)
    plugins: PluginConfig = Field(default_factory=PluginConfig)


def load_profile(path: str | Path) -> ScanProfile:
    """Load and validate a YAML scan profile from disk.

    Raises ``ConfigError`` if the file is missing or fails validation, so
    callers (the CLI) can catch one error type and print a clean message
    instead of a pydantic traceback.
    """
    profile_path = Path(path)
    if not profile_path.is_file():
        raise ConfigError(f"Profile not found: {profile_path}")

    try:
        raw = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Profile {profile_path} is not valid YAML: {exc}") from exc

    try:
        return ScanProfile.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Invalid profile {profile_path}: {exc}") from exc


class AutoFuzzSettings(BaseSettings):
    """Process-wide settings sourced from environment variables (``AUTOFUZZ_*``)."""

    model_config = SettingsConfigDict(env_prefix="AUTOFUZZ_", extra="ignore")

    config_dir: Path = Path.home() / ".autofuzz"
    log_level: str = "INFO"
    log_json: bool = False

    @field_validator("config_dir")
    @classmethod
    def _expand_user(cls, value: Path) -> Path:
        # pydantic's Path type does not expand a leading `~` on its own -
        # without this, AUTOFUZZ_CONFIG_DIR=~/.autofuzz would silently
        # create a literal directory named "~" under the current working
        # directory instead of resolving to the user's home directory.
        return value.expanduser()
