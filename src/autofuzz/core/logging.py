"""Structured logging setup shared by both engines and the CLI.

Replaces v1's ad-hoc mix of ``print()`` and manual file writes with one
configuration call that produces both a human-readable console stream and
(optionally) machine-parseable JSON, from the same log calls.
"""

from __future__ import annotations

import logging
import sys

import structlog

# httpx/httpcore log every single request/connection at INFO level via the
# stdlib logging module. Since they have no handler of their own, those
# records propagate to our root handler and flood the console with
# "HTTP Request: ..." lines on every fetch during a crawl or fuzzing run -
# at best noisy, at worst visually corrupting a live Rich progress bar
# (raw print()-style lines interleaving with its in-place redraws makes it
# look frozen even while it's still working). Silenced regardless of
# AutoFuzz's own configured level; -vv still shows AutoFuzz's own DEBUG
# logs without also drowning them in every third-party HTTP call.
_NOISY_THIRD_PARTY_LOGGERS = ("httpx", "httpcore")


def configure_logging(level: str = "INFO", *, json_output: bool = False) -> None:
    """Configure stdlib logging and structlog to share a single pipeline.

    Safe to call more than once (e.g. the CLI reconfigures on ``-v``); each
    call replaces the prior configuration rather than stacking handlers.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=numeric_level, force=True)

    for logger_name in _NOISY_THIRD_PARTY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to ``name`` (typically ``__name__``)."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
