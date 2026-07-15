"""AutoFuzz CLI entry point.

Provides ``autofuzz web <url>`` and ``autofuzz proto <profile>`` as explicit
subcommands, plus a shorthand: ``autofuzz <target>`` auto-detects which
engine to dispatch to (a URL implies ``web``; anything else implies
``proto``) by rewriting argv *before* Click/Typer parses it, so normal
subcommand parsing is never affected.

The engines themselves are stubs until Phase 4 (web) and Phase 3/5 (proto)
land; this phase only establishes the CLI shape and dispatch behavior.
"""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version

import typer

from autofuzz.cli.ui import console, print_error
from autofuzz.core.config import ScanProfile, load_profile
from autofuzz.core.errors import ConfigError
from autofuzz.core.logging import configure_logging, get_logger

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
    """Run the Web Assessment Engine against TARGET. (Engine lands in Phase 4.)"""
    if profile is not None:
        loaded = _load_and_authorize(profile, expected_engine="web")
        console.print(f"[green]Loaded profile:[/green] {loaded.name}")
    console.print(f"[yellow]Web Assessment Engine not implemented yet.[/yellow] Target: {target}")
    raise typer.Exit(code=1)


@app.command()
def proto(
    target: str = typer.Argument(..., help="Target as host:port, e.g. 127.0.0.1:21"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Path to a YAML profile."),
) -> None:
    """Run the Protocol Fuzzing Engine against TARGET. (Engine lands in Phase 3/5.)"""
    if profile is not None:
        loaded = _load_and_authorize(profile, expected_engine="proto")
        console.print(f"[green]Loaded profile:[/green] {loaded.name}")
    console.print(f"[yellow]Protocol Fuzzing Engine not implemented yet.[/yellow] Target: {target}")
    raise typer.Exit(code=1)


def cli_main() -> None:
    """Console-script entry point (registered in pyproject.toml)."""
    sys.argv = [sys.argv[0], *_inject_implicit_command(sys.argv[1:])]
    app()


if __name__ == "__main__":
    cli_main()
