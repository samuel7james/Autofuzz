"""Smoke tests for the CLI skeleton (Phase 2), profile/authorization gate
(Phase 3), the wired Protocol Fuzzing Engine (Phase 5), the wired Web
Assessment Engine + reporting (Phase 6), and scan sessions/history/resume
(Phase 7).

Every invocation that reaches report-writing passes --report-output
pointing into tmp_path - both `web` and `proto` write a report file by
default, and without an explicit path that would write into the real
working directory (littering the repo whenever the suite runs). The
autouse `_isolated_config_dir` fixture below does the same for scan
sessions, which otherwise default to the real `~/.autofuzz/scans/`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import autofuzz.cli.app as cli_app
from autofuzz.cli.app import _inject_implicit_command, app
from autofuzz.plugins.base import Finding, Severity

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolated_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point AutoFuzzSettings.config_dir at a per-test tmp directory so scan
    sessions never touch the real ~/.autofuzz/ during a test run."""
    monkeypatch.setenv("AUTOFUZZ_CONFIG_DIR", str(tmp_path / ".autofuzz-test"))


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "autofuzz" in result.stdout.lower()


def test_help_lists_subcommands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "web" in result.stdout
    assert "proto" in result.stdout
    assert "history" in result.stdout
    assert "resume" in result.stdout


def test_web_requires_profile() -> None:
    result = runner.invoke(app, ["web", "https://target.example"])
    assert result.exit_code != 0
    assert "profile" in result.output.lower()


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


def _report_args(tmp_path: Path) -> list[str]:
    return ["--report-output", str(tmp_path / "report.html")]


class _FakeWebEngine:
    """Stands in for WebAssessmentEngine so CLI tests never touch the network."""

    findings: list[Finding] = []
    stats: dict[str, int] = {}

    def __init__(self, *args: Any) -> None:
        pass

    async def run(self, start_url: str) -> tuple[list[Finding], dict[str, int]]:
        return type(self).findings, type(self).stats


def test_web_with_authorized_profile_runs_and_writes_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_app, "WebAssessmentEngine", _FakeWebEngine)
    _FakeWebEngine.findings = []
    _FakeWebEngine.stats = {"pages_crawled": 3}
    profile_path = _write_profile(tmp_path)
    report_path = tmp_path / "report.html"

    result = runner.invoke(
        app,
        ["web", "https://target.example", "--profile", str(profile_path), "-o", str(report_path)],
    )

    assert "Loaded profile: test" in result.stdout
    assert result.exit_code == 0
    assert report_path.is_file()
    assert "AutoFuzz Scan Report" in report_path.read_text(encoding="utf-8")


def test_web_with_findings_exits_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_app, "WebAssessmentEngine", _FakeWebEngine)
    _FakeWebEngine.findings = [
        Finding(
            plugin_id="web.missing-security-headers",
            title="Missing header",
            severity=Severity.LOW,
            description="d",
            target="https://target.example",
        )
    ]
    _FakeWebEngine.stats = {}
    profile_path = _write_profile(tmp_path)

    result = runner.invoke(
        app,
        [
            "web",
            "https://target.example",
            "--profile",
            str(profile_path),
            *_report_args(tmp_path),
        ],
    )

    assert result.exit_code == 1
    assert "Findings: 1" in result.output


def test_web_with_unauthorized_profile_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_app, "WebAssessmentEngine", _FakeWebEngine)
    profile_path = _write_profile(tmp_path, authorized=False)

    result = runner.invoke(
        app,
        [
            "web",
            "https://target.example",
            "--profile",
            str(profile_path),
            *_report_args(tmp_path),
        ],
    )

    assert result.exit_code == 2
    assert "authorized: false" in result.output


def test_web_with_mismatched_engine_profile_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_app, "WebAssessmentEngine", _FakeWebEngine)
    profile_path = _write_profile(tmp_path, engine="proto")

    result = runner.invoke(
        app,
        [
            "web",
            "https://target.example",
            "--profile",
            str(profile_path),
            *_report_args(tmp_path),
        ],
    )

    assert result.exit_code == 2
    assert "not 'web'" in result.output


def test_web_report_format_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_app, "WebAssessmentEngine", _FakeWebEngine)
    _FakeWebEngine.findings = []
    _FakeWebEngine.stats = {}
    profile_path = _write_profile(tmp_path)
    report_path = tmp_path / "report.json"

    result = runner.invoke(
        app,
        [
            "web",
            "https://target.example",
            "--profile",
            str(profile_path),
            "--report-format",
            "json",
            "-o",
            str(report_path),
        ],
    )

    assert result.exit_code == 0
    assert '"engine": "web"' in report_path.read_text(encoding="utf-8")


def test_proto_with_missing_profile_file_is_rejected(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.yaml"

    result = runner.invoke(
        app, ["proto", "127.0.0.1:21", "--profile", str(missing), *_report_args(tmp_path)]
    )

    assert result.exit_code == 2
    assert "not found" in result.output


class _FakeEngine:
    """Stands in for ProtocolFuzzingEngine so CLI tests never touch the network."""

    last_args: tuple[Any, ...] | None = None
    new_findings: list[Finding] = []

    def __init__(self, *args: Any) -> None:
        type(self).last_args = args

    async def run(self, start_iteration: int = 0) -> list[Finding]:
        return type(self).new_findings


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
    _FakeEngine.new_findings = []
    profile_path = _write_proto_profile(tmp_path)

    result = runner.invoke(
        app,
        ["proto", "127.0.0.1:21", "--profile", str(profile_path), *_report_args(tmp_path)],
    )

    assert result.exit_code == 0
    assert "Findings: 0" in result.output


def test_proto_runs_engine_and_reports_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_app, "ProtocolFuzzingEngine", _FakeEngine)
    _FakeEngine.new_findings = [
        Finding(
            plugin_id="protocol-fuzzing.crash-classifier",
            title="Target crashed",
            severity=Severity.HIGH,
            description="d",
            target="127.0.0.1:21",
        )
    ]
    profile_path = _write_proto_profile(tmp_path)

    result = runner.invoke(
        app,
        ["proto", "127.0.0.1:21", "--profile", str(profile_path), *_report_args(tmp_path)],
    )

    assert result.exit_code == 1
    assert "Findings: 1" in result.output
    assert "Target crashed" in result.output


def test_proto_warns_on_target_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_app, "ProtocolFuzzingEngine", _FakeEngine)
    _FakeEngine.new_findings = []
    profile_path = _write_proto_profile(tmp_path)

    result = runner.invoke(
        app,
        ["proto", "10.0.0.5:9999", "--profile", str(profile_path), *_report_args(tmp_path)],
    )

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

    result = runner.invoke(
        app,
        ["proto", "127.0.0.1:21", "--profile", str(profile_path), *_report_args(tmp_path)],
    )

    assert result.exit_code == 2
    assert "docker_container_name" in result.output


def test_proto_report_written_as_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_app, "ProtocolFuzzingEngine", _FakeEngine)
    _FakeEngine.new_findings = [
        Finding(
            plugin_id="protocol-fuzzing.crash-classifier",
            title="Target crashed",
            severity=Severity.HIGH,
            description="d",
            target="127.0.0.1:21",
        )
    ]
    profile_path = _write_proto_profile(tmp_path)
    report_path = tmp_path / "report.csv"

    result = runner.invoke(
        app,
        [
            "proto",
            "127.0.0.1:21",
            "--profile",
            str(profile_path),
            "--report-format",
            "csv",
            "-o",
            str(report_path),
        ],
    )

    assert result.exit_code == 1
    content = report_path.read_text(encoding="utf-8")
    assert "Target crashed" in content


def test_proto_creates_a_scan_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_app, "ProtocolFuzzingEngine", _FakeEngine)
    _FakeEngine.new_findings = []
    profile_path = _write_proto_profile(tmp_path)

    runner.invoke(
        app,
        ["proto", "127.0.0.1:21", "--profile", str(profile_path), *_report_args(tmp_path)],
    )

    sessions = list(cli_app._sessions_dir().glob("*.json"))
    assert len(sessions) == 1


def test_history_reports_no_sessions_initially() -> None:
    result = runner.invoke(app, ["history"])

    assert result.exit_code == 0
    assert "No scan history yet." in result.output


def test_history_lists_a_completed_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_app, "ProtocolFuzzingEngine", _FakeEngine)
    _FakeEngine.new_findings = []
    profile_path = _write_proto_profile(tmp_path)
    runner.invoke(
        app,
        ["proto", "127.0.0.1:21", "--profile", str(profile_path), *_report_args(tmp_path)],
    )

    result = runner.invoke(app, ["history"])

    assert result.exit_code == 0
    assert "proto" in result.output
    assert "completed" in result.output


def test_resume_unknown_scan_id_is_rejected() -> None:
    result = runner.invoke(app, ["resume", "does-not-exist"])

    assert result.exit_code == 2
    assert "not found" in result.output


def test_resume_web_scan_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_app, "WebAssessmentEngine", _FakeWebEngine)
    _FakeWebEngine.findings = []
    _FakeWebEngine.stats = {}
    profile_path = _write_profile(tmp_path)
    runner.invoke(
        app,
        ["web", "https://target.example", "--profile", str(profile_path), *_report_args(tmp_path)],
    )
    scan_id = next(cli_app._sessions_dir().glob("*.json")).stem

    result = runner.invoke(app, ["resume", scan_id])

    assert result.exit_code == 2
    assert "web scan" in result.output


def test_resume_continues_from_last_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_app, "ProtocolFuzzingEngine", _FakeEngine)
    profile_path = _write_proto_profile(
        tmp_path,
        protocol={"target_host": "127.0.0.1", "target_port": 21, "iterations": 10},
    )

    # Simulate an interrupted first run: engine "completes" 4 of 10
    # iterations with one finding, but the process dies before the CLI
    # marks the session complete (so it's left in the RUNNING state).
    class _InterruptedEngine(_FakeEngine):
        async def run(self, start_iteration: int = 0) -> list[Finding]:
            assert start_iteration == 0
            raise RuntimeError("simulated crash mid-scan")

    monkeypatch.setattr(cli_app, "ProtocolFuzzingEngine", _InterruptedEngine)
    result = runner.invoke(
        app,
        ["proto", "127.0.0.1:21", "--profile", str(profile_path), *_report_args(tmp_path)],
    )
    assert result.exit_code != 0  # the simulated crash propagates
    scan_id = next(cli_app._sessions_dir().glob("*.json")).stem

    # Manually checkpoint progress the way the real on_progress callback
    # would have, to simulate "died after completing iterations 0-3".
    session = cli_app.ScanSession.load(cli_app._sessions_dir() / f"{scan_id}.json")
    session.progress["iterations_completed"] = 4
    session.progress["findings"] = [
        Finding(
            plugin_id="protocol-fuzzing.crash-classifier",
            title="First crash",
            severity=Severity.HIGH,
            description="d",
            target="127.0.0.1:21",
        ).to_dict()
    ]
    session.save(cli_app._sessions_dir())

    monkeypatch.setattr(cli_app, "ProtocolFuzzingEngine", _FakeEngine)
    _FakeEngine.new_findings = [
        Finding(
            plugin_id="protocol-fuzzing.crash-classifier",
            title="Second crash",
            severity=Severity.HIGH,
            description="d",
            target="127.0.0.1:21",
        )
    ]

    result = runner.invoke(app, ["resume", scan_id, *_report_args(tmp_path)])

    assert result.exit_code == 1
    assert "from iteration 4/10" in result.output
    assert "Findings: 2" in result.output  # 1 prior + 1 new
    assert _FakeEngine.last_args is not None
    assert _FakeEngine.last_args[0].target_host == "127.0.0.1"


def test_resume_already_completed_scan_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_app, "ProtocolFuzzingEngine", _FakeEngine)
    _FakeEngine.new_findings = []
    profile_path = _write_proto_profile(tmp_path)
    runner.invoke(
        app,
        ["proto", "127.0.0.1:21", "--profile", str(profile_path), *_report_args(tmp_path)],
    )
    scan_id = next(cli_app._sessions_dir().glob("*.json")).stem

    result = runner.invoke(app, ["resume", scan_id])

    assert result.exit_code == 2
    assert "already completed" in result.output


class TestCliMainGlobalErrorHandling:
    """`cli_main()` wraps `app()` for a safety net CliRunner never exercises
    (CliRunner calls `app` directly, bypassing this wrapper entirely)."""

    def test_uncaught_autofuzz_error_exits_2_with_clean_message(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from autofuzz.core.errors import TargetError

        def _raise(*_args: Any, **_kwargs: Any) -> None:
            raise TargetError("docker restart failed")

        monkeypatch.setattr(cli_app, "app", _raise)
        monkeypatch.setattr("sys.argv", ["autofuzz", "web", "https://x"])

        with pytest.raises(SystemExit) as exc_info:
            cli_app.cli_main()

        assert exc_info.value.code == 2
        assert "docker restart failed" in capsys.readouterr().err

    def test_keyboard_interrupt_exits_130(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def _raise(*_args: Any, **_kwargs: Any) -> None:
            raise KeyboardInterrupt

        monkeypatch.setattr(cli_app, "app", _raise)
        monkeypatch.setattr("sys.argv", ["autofuzz", "proto", "1.2.3.4:21"])

        with pytest.raises(SystemExit) as exc_info:
            cli_app.cli_main()

        assert exc_info.value.code == 130
        assert "Interrupted" in capsys.readouterr().out
