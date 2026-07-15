"""Unit tests for PluginRegistry (Phase 5)."""

from __future__ import annotations

from typing import Any

import pytest

from autofuzz.core.errors import PluginError
from autofuzz.core.plugin import PluginRegistry
from autofuzz.plugins.base import Finding, Plugin, PluginMetadata, Severity


class _FindingPlugin(Plugin[str]):
    def __init__(self, plugin_id: str, *, applies: bool = True) -> None:
        self.metadata = PluginMetadata(id=plugin_id, name=plugin_id, description="d", engine="web")
        self._applies = applies
        self.options: dict[str, Any] = {}

    def applies_to(self, context: str) -> bool:
        return self._applies

    def run(self, context: str) -> list[Finding]:
        return [
            Finding(
                plugin_id=self.metadata.id,
                title=self.metadata.id,
                severity=Severity.INFO,
                description="d",
                target=context,
            )
        ]

    def configure(self, options: dict[str, Any]) -> None:
        self.options = options


class _RaisingPlugin(Plugin[str]):
    metadata = PluginMetadata(id="raises", name="raises", description="d", engine="web")

    def applies_to(self, context: str) -> bool:
        return True

    def run(self, context: str) -> list[Finding]:
        raise RuntimeError("plugin blew up")


def test_register_and_run_all() -> None:
    registry: PluginRegistry[str] = PluginRegistry()
    registry.register(_FindingPlugin("a"))
    registry.register(_FindingPlugin("b"))

    findings = registry.run_all("ctx")

    assert {f.plugin_id for f in findings} == {"a", "b"}


def test_register_duplicate_id_raises() -> None:
    registry: PluginRegistry[str] = PluginRegistry()
    registry.register(_FindingPlugin("a"))

    with pytest.raises(PluginError):
        registry.register(_FindingPlugin("a"))


def test_disable_excludes_plugin_from_run_all() -> None:
    registry: PluginRegistry[str] = PluginRegistry()
    registry.register(_FindingPlugin("a"))
    registry.register(_FindingPlugin("b"))

    registry.disable("a")
    findings = registry.run_all("ctx")

    assert {f.plugin_id for f in findings} == {"b"}


def test_enable_reverses_disable() -> None:
    registry: PluginRegistry[str] = PluginRegistry()
    registry.register(_FindingPlugin("a"))
    registry.disable("a")
    registry.enable("a")

    findings = registry.run_all("ctx")

    assert {f.plugin_id for f in findings} == {"a"}


def test_disable_unknown_plugin_raises() -> None:
    registry: PluginRegistry[str] = PluginRegistry()

    with pytest.raises(PluginError):
        registry.disable("nope")


def test_configure_with_allowlist_disables_everything_else() -> None:
    registry: PluginRegistry[str] = PluginRegistry()
    registry.register(_FindingPlugin("a"))
    registry.register(_FindingPlugin("b"))
    registry.register(_FindingPlugin("c"))

    registry.configure(enabled_ids=["a", "c"])
    findings = registry.run_all("ctx")

    assert {f.plugin_id for f in findings} == {"a", "c"}


def test_configure_with_unknown_enabled_id_raises() -> None:
    registry: PluginRegistry[str] = PluginRegistry()
    registry.register(_FindingPlugin("a"))

    with pytest.raises(PluginError):
        registry.configure(enabled_ids=["nope"])


def test_configure_with_disabled_ids() -> None:
    registry: PluginRegistry[str] = PluginRegistry()
    registry.register(_FindingPlugin("a"))
    registry.register(_FindingPlugin("b"))

    registry.configure(disabled_ids=["a"])
    findings = registry.run_all("ctx")

    assert {f.plugin_id for f in findings} == {"b"}


def test_run_all_skips_plugins_that_do_not_apply() -> None:
    registry: PluginRegistry[str] = PluginRegistry()
    registry.register(_FindingPlugin("a", applies=False))

    assert registry.run_all("ctx") == []


def test_run_all_isolates_a_raising_plugin() -> None:
    registry: PluginRegistry[str] = PluginRegistry()
    registry.register(_RaisingPlugin())
    registry.register(_FindingPlugin("ok"))

    findings = registry.run_all("ctx")

    assert {f.plugin_id for f in findings} == {"ok"}


def test_apply_options_calls_plugin_configure() -> None:
    registry: PluginRegistry[str] = PluginRegistry()
    plugin = _FindingPlugin("a")
    registry.register(plugin)

    registry.apply_options({"a": {"threshold": 5}})

    assert plugin.options == {"threshold": 5}


def test_apply_options_unknown_plugin_raises() -> None:
    registry: PluginRegistry[str] = PluginRegistry()

    with pytest.raises(PluginError):
        registry.apply_options({"nope": {}})
