"""AutoFuzz CLI entry point.

Provides ``autofuzz web <url>`` and ``autofuzz proto <profile>`` as explicit
subcommands, plus a shorthand: ``autofuzz <target>`` auto-detects which
engine to dispatch to (a URL implies ``web``; anything else implies
``proto``) by rewriting argv *before* Click/Typer parses it, so normal
subcommand parsing is never affected.

``proto`` runs the real Protocol Fuzzing Engine (Phase 3/5). ``web`` is
still a stub - the Web Assessment Engine's discovery half exists (Phase 4)
but isn't wired into a runnable, reportable scan until Phase 6's reporting
engine exists to give it something to produce.
"""

from __future__ import annotations

import asyncio
import sys
from importlib.metadata import PackageNotFoundError, version

import typer

from autofuzz.cli.ui import console, print_error, print_warning
from autofuzz.core.config import ScanProfile, load_profile
from autofuzz.core.errors import ConfigError, EngineError
from autofuzz.core.logging import configure_logging, get_logger
from autofuzz.core.target_controller import (
    DockerTargetController,
    NoOpTargetController,
    TargetController,
)
from autofuzz.protocol_fuzzing.engine import ProtocolFuzzingEngine

log = get_logger(__name__)

app = typer.Typer(
    name="autofuzz",
    help="Modular framework for authorized protocol fuzzing and web app security assessment.",
    no_args_is_help=True,
    add_completion=False,
)

_KNOWN_COMMANDS = {"web", "proto"}


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


@app.command()
def web(
    target: str = typer.Argument(..., help="Target URL, e.g. https://target.example"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Path to a YAML profile."),
) -> None:
    """Run the Web Assessment Engine against TARGET. (Runnable scan lands in Phase 6.)"""
    if profile is not None:
        loaded = _load_and_authorize(profile, expected_engine="web")
        console.print(f"[green]Loaded profile:[/green] {loaded.name}")
    console.print(f"[yellow]Web Assessment Engine not implemented yet.[/yellow] Target: {target}")
    raise typer.Exit(code=1)


def _build_target_controller(loaded: ScanProfile) -> TargetController:
    if loaded.protocol.target_controller != "docker":
        return NoOpTargetController()
    if not loaded.protocol.docker_container_name:
        print_error("protocol.target_controller is 'docker' but docker_container_name is not set.")
        raise typer.Exit(code=2)
    return DockerTargetController(loaded.protocol.docker_container_name)


@app.command()
def proto(
    target: str = typer.Argument(..., help="Target as host:port, e.g. 127.0.0.1:21"),
    profile: str = typer.Option(..., "--profile", "-p", help="Path to a YAML profile."),
) -> None:
    """Run the Protocol Fuzzing Engine against TARGET."""
    loaded = _load_and_authorize(profile, expected_engine="proto")
    console.print(f"[green]Loaded profile:[/green] {loaded.name}")

    expected_target = f"{loaded.protocol.target_host}:{loaded.protocol.target_port}"
    if target != expected_target:
        print_warning(
            f"TARGET argument ({target}) differs from the profile's target "
            f"({expected_target}); using the profile's target."
        )

    target_controller = _build_target_controller(loaded)
    engine = ProtocolFuzzingEngine(loaded.protocol, loaded.scheduler, target_controller)

    try:
        findings = asyncio.run(engine.run())
    except EngineError as exc:
        print_error(str(exc))
        raise typer.Exit(code=2) from exc

    console.print(f"Completed {loaded.protocol.iterations} attempts against {expected_target}.")
    console.print(f"Findings: {len(findings)}")
    for finding in findings:
        console.print(f"  [{finding.severity.value.upper()}] {finding.title}")

    raise typer.Exit(code=1 if findings else 0)


def cli_main() -> None:
    """Console-script entry point (registered in pyproject.toml)."""
    sys.argv = [sys.argv[0], *_inject_implicit_command(sys.argv[1:])]
    app()


if __name__ == "__main__":
    cli_main()
