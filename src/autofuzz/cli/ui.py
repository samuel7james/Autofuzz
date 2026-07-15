"""Shared Rich console helpers for the CLI: plain output, errors/warnings,
and severity-colored finding output."""

from __future__ import annotations

from rich.console import Console

from autofuzz.plugins.base import Severity

console = Console()
error_console = Console(stderr=True)

_SEVERITY_STYLES: dict[Severity, str] = {
    Severity.CRITICAL: "bold white on red",
    Severity.HIGH: "bold red",
    Severity.MEDIUM: "bold yellow",
    Severity.LOW: "cyan",
    Severity.INFO: "dim",
}


def print_error(message: str) -> None:
    error_console.print(f"[bold red]Error:[/bold red] {message}")


def print_warning(message: str) -> None:
    console.print(f"[yellow]Warning:[/yellow] {message}")


def severity_tag(severity: Severity) -> str:
    """A Rich markup tag rendering SEVERITY in a color matching its risk level."""
    style = _SEVERITY_STYLES.get(severity, "white")
    return f"[{style}]{severity.value.upper()}[/{style}]"
