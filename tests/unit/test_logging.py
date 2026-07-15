"""Unit tests for structured logging setup (Phase 2/8)."""

from __future__ import annotations

import logging

from autofuzz.core.logging import configure_logging, get_logger


def test_configure_logging_does_not_raise() -> None:
    configure_logging(level="DEBUG")
    log = get_logger("test")
    log.info("hello", key="value")


def test_configure_logging_json_mode_does_not_raise() -> None:
    configure_logging(level="INFO", json_output=True)
    log = get_logger("test")
    log.warning("json mode")


def test_httpx_logger_is_silenced_even_at_debug_level() -> None:
    # httpx logs every request at INFO via stdlib logging; even when the
    # user asks for -v/DEBUG output, httpx's own per-request noise must
    # stay suppressed (it collides with a live Rich progress bar and floods
    # the console - see Phase 8 for the incident this covers).
    configure_logging(level="DEBUG")

    assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() == logging.WARNING


def test_httpx_logger_silenced_at_default_info_level() -> None:
    configure_logging(level="INFO")

    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
