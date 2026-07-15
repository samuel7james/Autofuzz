"""Unit tests for structured logging setup (Phase 2)."""

from __future__ import annotations

from autofuzz.core.logging import configure_logging, get_logger


def test_configure_logging_does_not_raise() -> None:
    configure_logging(level="DEBUG")
    log = get_logger("test")
    log.info("hello", key="value")


def test_configure_logging_json_mode_does_not_raise() -> None:
    configure_logging(level="INFO", json_output=True)
    log = get_logger("test")
    log.warning("json mode")
