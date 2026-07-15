"""Unit tests for the shared Plugin/Finding contracts (Phase 5/7)."""

from __future__ import annotations

import json

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


def test_finding_to_dict_is_json_serializable() -> None:
    finding = Finding(
        plugin_id="test.x",
        title="t",
        severity=Severity.CRITICAL,
        description="d",
        target="x",
        metadata={"count": 3},
    )

    data = finding.to_dict()
    encoded = json.dumps(data)  # must not raise

    assert data["severity"] == "critical"
    assert json.loads(encoded)["metadata"] == {"count": 3}


def test_finding_from_dict_round_trips() -> None:
    original = Finding(
        plugin_id="test.x",
        title="t",
        severity=Severity.MEDIUM,
        description="d",
        target="x",
        evidence="ev",
        metadata={"a": 1},
    )

    restored = Finding.from_dict(original.to_dict())

    assert restored == original
    assert restored.severity is Severity.MEDIUM
