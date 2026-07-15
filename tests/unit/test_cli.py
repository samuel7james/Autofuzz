"""Smoke tests for the CLI skeleton (Phase 2)."""

from __future__ import annotations

from typer.testing import CliRunner

from autofuzz.cli.app import _inject_implicit_command, app

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


def test_proto_stub_reports_not_implemented() -> None:
    result = runner.invoke(app, ["proto", "127.0.0.1:21"])
    assert result.exit_code == 1
    assert "not implemented yet" in result.stdout


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
