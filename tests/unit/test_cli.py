"""Smoke tests for the CLI skeleton (Phase 2), profile/authorization gate
(Phase 3), and the wired Protocol Fuzzing Engine (Phase 5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import autofuzz.cli.app as cli_app
from autofuzz.cli.app import _inject_implicit_command, app
from autofuzz.plugins.base import Finding, Severity

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "autofuzz" in result.stdout.lower()


def test_help_lists_subcommands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "web" in result.stdout
    assert "proto" in result.stdout


def test_web_stub_reports_not_implemented() -> None:
    result = runner.invoke(app, ["web", "https://target.example"])
    assert result.exit_code == 1
    assert "not implemented yet" in result.stdout


def test_proto_requires_profile() -> None:
    result = runner.invoke(app, ["proto", "127.0.0.1:21"])
    assert result.exit_code != 0
    assert "profile" in result.output.lower()


def test_inject_implicit_command_detects_url_as_web() -> None:
    assert _inject_implicit_command(["https://target.example"]) == [
        "web",
        "https://target.example",
    ]


def test_inject_implicit_command_detects_host_port_as_proto() -> None:
    assert _inject_implicit_command(["127.0.0.1:21"]) == ["proto", "127.0.0.1:21"]


def test_inject_implicit_command_noop_for_known_subcommand() -> None:
    argv = ["web", "https://target.example"]
    assert _inject_implicit_command(argv) == argv


def test_inject_implicit_command_noop_for_empty_argv() -> None:
    assert _inject_implicit_command([]) == []


def test_inject_implicit_command_preserves_leading_options() -> None:
    assert _inject_implicit_command(["-v", "https://target.example"]) == [
        "-v",
        "web",
        "https://target.example",
    ]


def _write_profile(tmp_path: Path, name: str = "profile.yaml", **overrides: object) -> Path:
    fields = {"name": "test", "engine": "web", "authorized": True, **overrides}
    body = "\n".join(f"{key}: {value}" for key, value in fields.items())
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_web_with_authorized_profile_loads_and_still_reports_stub(tmp_path: Path) -> None:
    profile_path = _write_profile(tmp_path)

    result = runner.invoke(app, ["web", "https://target.example", "--profile", str(profile_path)])

    assert "Loaded profile: test" in result.stdout
    assert "not implemented yet" in result.stdout
    assert result.exit_code == 1


def test_web_with_unauthorized_profile_is_rejected(tmp_path: Path) -> None:
    profile_path = _write_profile(tmp_path, authorized=False)

    result = runner.invoke(app, ["web", "https://target.example", "--profile", str(profile_path)])

    assert result.exit_code == 2
    assert "authorized: false" in result.output


def test_web_with_mismatched_engine_profile_is_rejected(tmp_path: Path) -> None:
    profile_path = _write_profile(tmp_path, engine="proto")

    result = runner.invoke(app, ["web", "https://target.example", "--profile", str(profile_path)])

    assert result.exit_code == 2
    assert "not 'web'" in result.output


def test_proto_with_missing_profile_file_is_rejected(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.yaml"

    result = runner.invoke(app, ["proto", "127.0.0.1:21", "--profile", str(missing)])

    assert result.exit_code == 2
    assert "not found" in result.output


class _FakeEngine:
    """Stands in for ProtocolFuzzingEngine so CLI tests never touch the network."""

    last_args: tuple[Any, ...] | None = None
    findings: list[Finding] = []

    def __init__(self, *args: Any) -> None:
        type(self).last_args = args

    async def run(self) -> list[Finding]:
        return type(self).findings


def _write_proto_profile(tmp_path: Path, **overrides: object) -> Path:
    fields = {
        "name": "ftp-test",
        "engine": "proto",
        "authorized": True,
        "protocol": {"target_host": "127.0.0.1", "target_port": 21, "iterations": 5},
        **overrides,
    }
    path = tmp_path / "proto.yaml"
    path.write_text(_to_yaml(fields), encoding="utf-8")
    return path


def _to_yaml(value: object, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(value, dict):
        lines = []
        for key, val in value.items():
            if isinstance(val, dict):
                lines.append(f"{pad}{key}:")
                lines.append(_to_yaml(val, indent + 1))
            else:
                lines.append(f"{pad}{key}: {val}")
        return "\n".join(lines)
    return f"{pad}{value}"


def test_proto_runs_engine_and_reports_no_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_app, "ProtocolFuzzingEngine", _FakeEngine)
    _FakeEngine.findings = []
    profile_path = _write_proto_profile(tmp_path)

    result = runner.invoke(app, ["proto", "127.0.0.1:21", "--profile", str(profile_path)])

    assert result.exit_code == 0
    assert "Findings: 0" in result.output


def test_proto_runs_engine_and_reports_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_app, "ProtocolFuzzingEngine", _FakeEngine)
    _FakeEngine.findings = [
        Finding(
            plugin_id="protocol-fuzzing.crash-classifier",
            title="Target crashed",
            severity=Severity.HIGH,
            description="d",
            target="127.0.0.1:21",
        )
    ]
    profile_path = _write_proto_profile(tmp_path)

    result = runner.invoke(app, ["proto", "127.0.0.1:21", "--profile", str(profile_path)])

    assert result.exit_code == 1
    assert "Findings: 1" in result.output
    assert "Target crashed" in result.output


def test_proto_warns_on_target_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_app, "ProtocolFuzzingEngine", _FakeEngine)
    _FakeEngine.findings = []
    profile_path = _write_proto_profile(tmp_path)

    result = runner.invoke(app, ["proto", "10.0.0.5:9999", "--profile", str(profile_path)])

    assert result.exit_code == 0
    assert "differs from the profile's target" in result.output


def test_proto_docker_controller_without_container_name_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_app, "ProtocolFuzzingEngine", _FakeEngine)
    profile_path = _write_proto_profile(
        tmp_path,
        protocol={
            "target_host": "127.0.0.1",
            "target_port": 21,
            "iterations": 5,
            "target_controller": "docker",
        },
    )

    result = runner.invoke(app, ["proto", "127.0.0.1:21", "--profile", str(profile_path)])

    assert result.exit_code == 2
    assert "docker_container_name" in result.output
