"""AutoFuzz exception hierarchy.

All errors AutoFuzz raises deliberately derive from ``AutoFuzzError`` so the
CLI can catch one base type and print an actionable message instead of a raw
traceback (Phase 7). Do not use bare ``except:`` anywhere in this codebase —
v1's ``is_ftp_alive()`` did, and it silently swallowed ``KeyboardInterrupt``.
"""

from __future__ import annotations


class AutoFuzzError(Exception):
    """Base class for all AutoFuzz errors."""


class ConfigError(AutoFuzzError):
    """Configuration or scan profile is missing, malformed, or fails validation."""


class AuthorizationError(AutoFuzzError):
    """A scan was attempted without explicit authorization for the target."""


class TargetError(AutoFuzzError):
    """The target is unreachable, or behaved outside what the engine expects."""


class PluginError(AutoFuzzError):
    """A plugin failed to load or raised during execution."""


class EngineError(AutoFuzzError):
    """A web or protocol engine failed outside of a specific plugin/target error."""
