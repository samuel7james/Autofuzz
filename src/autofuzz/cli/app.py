"""AutoFuzz CLI entry point.

Provides ``autofuzz web <url>`` and ``autofuzz proto <profile>`` as explicit
subcommands, plus a shorthand: ``autofuzz <target>`` auto-detects which
engine to dispatch to (a URL implies ``web``; anything else implies
``proto``) by rewriting argv *before* Click/Typer parses it, so normal
subcommand parsing is never affected.

Both ``web`` and ``proto`` run their real engines, show a live progress
bar, checkpoint a ``ScanSession`` as they go (so ``autofuzz history`` can
list the run and ``autofuzz resume`` can continue an interrupted protocol
fuzzing scan), and write a scan report (HTML by default;
``--report-format``/``--report-output`` to change that).
"""

from __future__ import annotations

import asyncio
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import typer
from rich.progress import Progress
from rich.table import Table

from autofuzz.cli.ui import console, print_error, print_warning, severity_tag
from autofuzz.core.config import AutoFuzzSettings, ScanProfile, load_profile
from autofuzz.core.errors import AutoFuzzError, ConfigError, EngineError
from autofuzz.core.logging import configure_logging, get_logger
from autofuzz.core.plugin import PluginRegistry
from autofuzz.core.scan import ScanSession, ScanState
from autofuzz.core.target_controller import (
    DockerTargetController,
    NoOpTargetController,
    TargetController,
)
from autofuzz.plugins.base import Finding
from autofuzz.protocol_fuzzing.engine import ProtocolFuzzingEngine
from autofuzz.reporting import ReportFormat, ScanReport, default_extension, render_report
from autofuzz.web.crawler import CrawlResult
from autofuzz.web.engine import WebAssessmentEngine, default_web_plugin_registry

log = get_logger(__name__)

app = typer.Typer(
    name="autofuzz",
    help="Modular framework for authorized protocol fuzzing and web app security assessment.",
    no_args_is_help=True,
    add_completion=False,
)

_KNOWN_COMMANDS = {"web", "proto", "history", "resume"}


def _inject_implicit_command(argv: list[str]) -> list[str]:
    """Rewrite ``autofuzz <target> ...`` to ``autofuzz web|proto <target> ...``.

    Leaves argv untouched if it already starts with a known subcommand, an
    option, or is empty. Pure function so it can be unit tested without
    touching ``sys.argv``.
    """
    positional = [a for a in argv if not a.startswith("-")]
    if not positional or positional[0] in _KNOWN_COMMANDS:
        return argv

    candidate = positional[0]
    insert_at = argv.index(candidate)
    engine = "web" if candidate.startswith(("http://", "https://")) else "proto"
    return [*argv[:insert_at], engine, *argv[insert_at:]]


def _version_callback(value: bool) -> None:
    if not value:
        return
    try:
        current_version = version("autofuzz")
    except PackageNotFoundError:
        current_version = "0.0.0+dev"
    console.print(f"autofuzz {current_version}")
    raise typer.Exit()


@app.callback()
def main(
    version_: bool | None = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the AutoFuzz version and exit.",
    ),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Increase log verbosity."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-essential output."),
) -> None:
    """AutoFuzz: authorized-use security assessment framework."""
    level = "ERROR" if quiet else ("DEBUG" if verbose >= 1 else "INFO")
    configure_logging(level=level)


def _sessions_dir() -> Path:
    return AutoFuzzSettings().config_dir / "scans"


def _load_and_authorize(profile_path: str, expected_engine: str) -> ScanProfile:
    """Load a YAML profile, confirm it targets the invoked engine, and enforce
    the authorization gate. Exits the CLI with code 2 on any failure — never
    silently falls through to running a scan."""
    try:
        profile = load_profile(profile_path)
    except ConfigError as exc:
        print_error(str(exc))
        raise typer.Exit(code=2) from exc

    if profile.engine != expected_engine:
        print_error(
            f"Profile '{profile.name}' is for the '{profile.engine}' engine, "
            f"not '{expected_engine}'."
        )
        raise typer.Exit(code=2)

    if not profile.authorized:
        print_error(
            f"Profile '{profile.name}' has authorized: false. Set it to true only "
            "after confirming you are authorized to test this target."
        )
        raise typer.Exit(code=2)

    return profile


def _build_report(
    *,
    scan_id: str,
    engine: str,
    target: str,
    profile_name: str,
    findings: list[Finding],
    stats: dict[str, int],
) -> ScanReport:
    report = ScanReport.create(
        scan_id=scan_id, engine=engine, target=target, profile_name=profile_name
    )
    report.findings = findings
    report.stats = stats
    report.complete()
    return report


def _print_summary(report: ScanReport) -> None:
    console.print(f"Findings: {len(report.findings)}  |  Risk score: {report.risk.score}")
    for finding in report.findings:
        console.print(f"  {severity_tag(finding.severity)} {finding.title}")


def _write_report_file(report: ScanReport, fmt: ReportFormat, output: str | None) -> Path:
    default_name = f"autofuzz-report-{report.scan_id}.{default_extension(fmt)}"
    path = Path(output) if output else Path(default_name)
    path.write_text(render_report(report, fmt), encoding="utf-8")
    return path


def _build_target_controller(profile: ScanProfile) -> TargetController:
    if profile.protocol.target_controller != "docker":
        return NoOpTargetController()
    if not profile.protocol.docker_container_name:
        print_error("protocol.target_controller is 'docker' but docker_container_name is not set.")
        raise typer.Exit(code=2)
    return DockerTargetController(profile.protocol.docker_container_name)


def _run_web_engine(
    profile: ScanProfile, target: str, session: ScanSession
) -> tuple[list[Finding], dict[str, int]]:
    registry: PluginRegistry[CrawlResult] = default_web_plugin_registry()
    registry.configure(enabled_ids=profile.plugins.enabled, disabled_ids=profile.plugins.disabled)
    registry.apply_options(profile.plugins.options)

    with Progress(console=console) as progress_bar:
        task = progress_bar.add_task("Crawling", total=profile.web.max_pages)

        def on_progress(completed: int, total: int) -> None:
            progress_bar.update(task, completed=completed, total=total)
            session.progress["pages_crawled"] = completed
            session.save(_sessions_dir())

        engine = WebAssessmentEngine(profile.web, profile.scheduler, registry, on_progress)
        return asyncio.run(engine.run(target))


def _run_proto_engine(
    profile: ScanProfile,
    target_controller: TargetController,
    session: ScanSession,
    *,
    start_iteration: int = 0,
    prior_findings: list[Finding] | None = None,
    progress_label: str = "Fuzzing",
) -> list[Finding]:
    prior = prior_findings or []
    total = profile.protocol.iterations

    with Progress(console=console) as progress_bar:
        task = progress_bar.add_task(progress_label, total=total, completed=start_iteration)

        def on_progress(completed: int, _total: int, findings_so_far: list[Finding]) -> None:
            progress_bar.update(task, completed=completed)
            combined = prior + findings_so_far
            session.progress["iterations_completed"] = completed
            session.progress["findings"] = [f.to_dict() for f in combined]
            session.save(_sessions_dir())

        engine = ProtocolFuzzingEngine(
            profile.protocol, profile.scheduler, target_controller, on_progress
        )
        new_findings = asyncio.run(engine.run(start_iteration=start_iteration))

    return prior + new_findings


_REPORT_FORMAT_OPTION = typer.Option(
    ReportFormat.HTML, "--report-format", help="Report output format."
)
_REPORT_OUTPUT_OPTION = typer.Option(
    None,
    "--report-output",
    "-o",
    help="Report file path (default: autofuzz-report-<scan-id>.<ext>).",
)


@app.command()
def web(
    target: str = typer.Argument(..., help="Target URL, e.g. https://target.example"),
    profile: str = typer.Option(..., "--profile", "-p", help="Path to a YAML profile."),
    report_format: ReportFormat = _REPORT_FORMAT_OPTION,
    report_output: str | None = _REPORT_OUTPUT_OPTION,
) -> None:
    """Run the Web Assessment Engine against TARGET and write a scan report."""
    loaded = _load_and_authorize(profile, expected_engine="web")
    console.print(f"[green]Loaded profile:[/green] {loaded.name}")

    session = ScanSession.create(loaded, target=target)
    session.start()
    session.save(_sessions_dir())

    try:
        findings, stats = _run_web_engine(loaded, target, session)
    except Exception as exc:
        session.fail(str(exc))
        session.save(_sessions_dir())
        raise

    session.complete()
    session.save(_sessions_dir())

    report = _build_report(
        scan_id=session.id,
        engine="web",
        target=target,
        profile_name=loaded.name,
        findings=findings,
        stats=stats,
    )
    _print_summary(report)
    output_path = _write_report_file(report, report_format, report_output)
    console.print(f"Report written to {output_path}")

    raise typer.Exit(code=1 if findings else 0)


@app.command()
def proto(
    target: str = typer.Argument(..., help="Target as host:port, e.g. 127.0.0.1:21"),
    profile: str = typer.Option(..., "--profile", "-p", help="Path to a YAML profile."),
    report_format: ReportFormat = _REPORT_FORMAT_OPTION,
    report_output: str | None = _REPORT_OUTPUT_OPTION,
) -> None:
    """Run the Protocol Fuzzing Engine against TARGET and write a scan report."""
    loaded = _load_and_authorize(profile, expected_engine="proto")
    console.print(f"[green]Loaded profile:[/green] {loaded.name}")

    expected_target = f"{loaded.protocol.target_host}:{loaded.protocol.target_port}"
    if target != expected_target:
        print_warning(
            f"TARGET argument ({target}) differs from the profile's target "
            f"({expected_target}); using the profile's target."
        )

    target_controller = _build_target_controller(loaded)

    session = ScanSession.create(loaded, target=expected_target)
    session.start()
    session.save(_sessions_dir())

    try:
        findings = _run_proto_engine(loaded, target_controller, session)
    except Exception as exc:
        session.fail(str(exc))
        session.save(_sessions_dir())
        raise

    session.complete()
    session.save(_sessions_dir())

    report = _build_report(
        scan_id=session.id,
        engine="proto",
        target=expected_target,
        profile_name=loaded.name,
        findings=findings,
        stats={"iterations": loaded.protocol.iterations},
    )
    _print_summary(report)
    output_path = _write_report_file(report, report_format, report_output)
    console.print(f"Report written to {output_path}")

    raise typer.Exit(code=1 if findings else 0)


@app.command()
def history(
    limit: int = typer.Option(20, "--limit", help="Maximum number of scans to show."),
) -> None:
    """List past scans recorded in the local session store."""
    sessions_dir = _sessions_dir()
    if not sessions_dir.is_dir():
        console.print("No scan history yet.")
        return

    session_files = sorted(
        sessions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not session_files:
        console.print("No scan history yet.")
        return

    table = Table("Scan ID", "Engine", "Target", "State", "Findings", "Started")
    for path in session_files[:limit]:
        try:
            entry = ScanSession.load(path)
        except Exception as exc:
            log.warning("history_session_unreadable", path=str(path), error=str(exc))
            continue
        finding_count = len(entry.progress.get("findings", []))
        table.add_row(
            entry.id,
            entry.profile.engine,
            entry.target or "-",
            entry.state.value,
            str(finding_count),
            entry.created_at,
        )

    console.print(table)


@app.command()
def resume(
    scan_id: str = typer.Argument(..., help="Scan ID to resume, from `autofuzz history`."),
    report_format: ReportFormat = _REPORT_FORMAT_OPTION,
    report_output: str | None = _REPORT_OUTPUT_OPTION,
) -> None:
    """Resume an interrupted protocol-fuzzing scan. Web-scan resume isn't supported yet."""
    try:
        session = ScanSession.load(_sessions_dir() / f"{scan_id}.json")
    except EngineError as exc:
        print_error(str(exc))
        raise typer.Exit(code=2) from exc

    if session.profile.engine != "proto":
        print_error(
            f"Resuming web scans isn't supported yet (scan '{scan_id}' is a web scan). "
            "Start a new scan with `autofuzz web` instead."
        )
        raise typer.Exit(code=2)

    if session.state == ScanState.COMPLETED:
        print_error(f"Scan '{scan_id}' already completed; nothing to resume.")
        raise typer.Exit(code=2)

    total = session.profile.protocol.iterations
    start_iteration = int(session.progress.get("iterations_completed", 0))
    if start_iteration >= total:
        print_error(f"Scan '{scan_id}' already reached its {total} configured iterations.")
        raise typer.Exit(code=2)

    prior_findings = [Finding.from_dict(d) for d in session.progress.get("findings", [])]
    console.print(
        f"[green]Resuming scan {scan_id}[/green] from iteration {start_iteration}/{total} "
        f"({len(prior_findings)} finding(s) so far)."
    )

    target_controller = _build_target_controller(session.profile)

    session.start()
    session.save(_sessions_dir())

    try:
        findings = _run_proto_engine(
            session.profile,
            target_controller,
            session,
            start_iteration=start_iteration,
            prior_findings=prior_findings,
            progress_label="Resuming fuzzing",
        )
    except Exception as exc:
        session.fail(str(exc))
        session.save(_sessions_dir())
        raise

    session.complete()
    session.save(_sessions_dir())

    expected_target = (
        f"{session.profile.protocol.target_host}:{session.profile.protocol.target_port}"
    )
    report = _build_report(
        scan_id=session.id,
        engine="proto",
        target=expected_target,
        profile_name=session.profile.name,
        findings=findings,
        stats={"iterations": total},
    )
    _print_summary(report)
    output_path = _write_report_file(report, report_format, report_output)
    console.print(f"Report written to {output_path}")

    raise typer.Exit(code=1 if findings else 0)


def cli_main() -> None:
    """Console-script entry point (registered in pyproject.toml).

    Wraps the whole app so an AutoFuzzError that escapes a command body
    (e.g. a Docker recovery failure mid-scan) still prints a clean message
    instead of a raw traceback, and Ctrl-C exits quietly.
    """
    sys.argv = [sys.argv[0], *_inject_implicit_command(sys.argv[1:])]
    try:
        app()
    except AutoFuzzError as exc:
        print_error(str(exc))
        sys.exit(2)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)


if __name__ == "__main__":
    cli_main()
