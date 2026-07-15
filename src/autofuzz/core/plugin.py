"""Plugin registry: holds a set of plugins for one engine, applies enable/
disable/option configuration from a ScanProfile, and runs them against a
stream of contexts, collecting Findings.

Registration is explicit (``register()``) rather than entry-point or
package-scan discovery - AutoFuzz isn't hosting third-party plugin
packages yet, so building that discovery machinery ahead of a real need
would be speculative. Explicit registration is the natural extension
point when that need shows up.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Generic, TypeVar

from autofuzz.core.errors import PluginError
from autofuzz.core.logging import get_logger
from autofuzz.plugins.base import Finding, Plugin

log = get_logger(__name__)

ContextT = TypeVar("ContextT")


class PluginRegistry(Generic[ContextT]):
    """Holds a set of plugins for one engine and runs them against contexts."""

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin[ContextT]] = {}
        self._disabled: set[str] = set()

    def register(self, plugin: Plugin[ContextT]) -> None:
        if plugin.metadata.id in self._plugins:
            raise PluginError(f"Plugin id already registered: {plugin.metadata.id!r}")
        self._plugins[plugin.metadata.id] = plugin

    def enable(self, plugin_id: str) -> None:
        self._require_known(plugin_id)
        self._disabled.discard(plugin_id)

    def disable(self, plugin_id: str) -> None:
        self._require_known(plugin_id)
        self._disabled.add(plugin_id)

    def configure(
        self,
        enabled_ids: Iterable[str] | None = None,
        disabled_ids: Iterable[str] | None = None,
    ) -> None:
        """Apply an allow-list (``enabled_ids``) and/or deny-list (``disabled_ids``)
        of plugin ids, typically sourced from ``ScanProfile.plugins``."""
        if enabled_ids is not None:
            allowed = set(enabled_ids)
            unknown = allowed - self._plugins.keys()
            if unknown:
                raise PluginError(f"Unknown plugin id(s): {sorted(unknown)}")
            self._disabled = self._plugins.keys() - allowed
        for plugin_id in disabled_ids or ():
            self.disable(plugin_id)

    def apply_options(self, options: dict[str, dict[str, object]]) -> None:
        for plugin_id, plugin_options in options.items():
            self._require_known(plugin_id)
            self._plugins[plugin_id].configure(plugin_options)

    def _require_known(self, plugin_id: str) -> None:
        if plugin_id not in self._plugins:
            raise PluginError(f"Unknown plugin id: {plugin_id!r}")

    @property
    def active_plugins(self) -> list[Plugin[ContextT]]:
        return [plugin for pid, plugin in self._plugins.items() if pid not in self._disabled]

    def run_all(self, context: ContextT) -> list[Finding]:
        """Run every active, applicable plugin against ``context``.

        A plugin that raises is logged and skipped - one bad plugin must
        never abort an entire scan.
        """
        findings: list[Finding] = []
        for plugin in self.active_plugins:
            try:
                if not plugin.applies_to(context):
                    continue
                findings.extend(plugin.run(context))
            except Exception as exc:
                log.warning("plugin_execution_failed", plugin_id=plugin.metadata.id, error=str(exc))
        return findings
