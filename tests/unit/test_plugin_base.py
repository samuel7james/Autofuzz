"""Unit tests for the shared Plugin/Finding contracts (Phase 5)."""

from __future__ import annotations

from autofuzz.plugins.base import Finding, Plugin, PluginMetadata, Severity


class _AlwaysFindsSomething(Plugin[str]):
    metadata = PluginMetadata(id="test.always", name="Always Finds", description="d", engine="web")

    def applies_to(self, context: str) -> bool:
        return True

    def run(self, context: str) -> list[Finding]:
        return [
            Finding(
                plugin_id=self.metadata.id,
                title="found something",
                severity=Severity.INFO,
                description="d",
                target=context,
            )
        ]


def test_finding_defaults_evidence_and_metadata() -> None:
    finding = Finding(
        plugin_id="test.x", title="t", severity=Severity.LOW, description="d", target="x"
    )

    assert finding.evidence == ""
    assert finding.metadata == {}
    assert finding.discovered_at


def test_finding_is_frozen() -> None:
    finding = Finding(
        plugin_id="test.x", title="t", severity=Severity.LOW, description="d", target="x"
    )

    try:
        finding.title = "changed"  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("Finding should be immutable")


def test_plugin_default_configure_is_a_noop() -> None:
    plugin = _AlwaysFindsSomething()

    plugin.configure({"anything": "goes"})  # must not raise


def test_plugin_applies_to_and_run() -> None:
    plugin = _AlwaysFindsSomething()

    assert plugin.applies_to("target") is True
    findings = plugin.run("target")
    assert len(findings) == 1
    assert findings[0].target == "target"
