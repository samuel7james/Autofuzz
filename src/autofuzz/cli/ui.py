"""Shared Rich console helpers for the CLI.

Kept minimal in Phase 2 (plain print helpers); progress bars, spinners, and
severity-colored finding output land in Phase 7.
"""

from __future__ import annotations

from rich.console import Console

console = Console()
error_console = Console(stderr=True)


def print_error(message: str) -> None:
    error_console.print(f"[bold red]Error:[/bold red] {message}")


def print_warning(message: str) -> None:
    console.print(f"[yellow]Warning:[/yellow] {message}")
