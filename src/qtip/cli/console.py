"""
Console output utilities for helpful CLI messaging.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from typing import NoReturn

import click


# === Styled Output ===


def info(message: str) -> None:
    """Print an info message."""
    click.echo(click.style("ℹ ", fg="blue") + message)


def success(message: str) -> None:
    """Print a success message."""
    click.echo(click.style("✓ ", fg="green") + message)


def warning(message: str) -> None:
    """Print a warning message."""
    click.echo(click.style("⚠ ", fg="yellow") + message, err=True)


def error(message: str) -> None:
    """Print an error message."""
    click.echo(click.style("✗ ", fg="red") + message, err=True)


def fatal(message: str, hint: str | None = None) -> NoReturn:
    """Print an error and exit."""
    error(message)
    if hint:
        click.echo(click.style("  hint: ", fg="cyan") + hint, err=True)
    sys.exit(1)


def dim(message: str) -> None:
    """Print dimmed/secondary text."""
    click.echo(click.style(message, dim=True))


def header(title: str) -> None:
    """Print a section header."""
    click.echo()
    click.echo(
        click.style(f"── {title} ", fg="cyan", bold=True)
        + click.style("─" * 40, dim=True)
    )


# === Progress Indicators ===


@contextmanager
def spinner(message: str):
    """
    Simple spinner for long operations.

    Usage:
        with spinner("Connecting to database..."):
            await db.connect()
    """
    click.echo(click.style("◐ ", fg="blue") + message, nl=False)
    try:
        yield
        click.echo(click.style(" ✓", fg="green"))
    except Exception:
        click.echo(click.style(" ✗", fg="red"))
        raise


@contextmanager
def step(message: str):
    """
    Step indicator with pass/fail.

    Usage:
        with step("Running migrations"):
            run_migrations()
    """
    click.echo(click.style("→ ", fg="blue") + message + "... ", nl=False)
    try:
        yield
        click.echo(click.style("done", fg="green"))
    except Exception as e:
        click.echo(click.style("failed", fg="red"))
        raise


# === Helpful Error Messages ===

ERROR_HINTS = {
    "no_pyproject": (
        "Could not find pyproject.toml",
        "Make sure you're running from your project root, or use --config to specify the path",
    ),
    "no_app_module": (
        "Could not load application module",
        "Check that [tool.qtip].app_module points to your Application instance",
    ),
    "no_database_url": (
        "DATABASE_URL is not configured",
        "Set it in pyproject.toml, .env, or as an environment variable",
    ),
    "database_connection": (
        "Could not connect to database",
        "Check that your database is running and DATABASE_URL is correct",
    ),
    "redis_connection": (
        "Could not connect to Redis",
        "Check that Redis is running and REDIS_URL is correct",
    ),
    "migration_conflict": (
        "Migration conflict detected",
        "You may have multiple heads. Run 'db heads' to see them, then 'db merge' to resolve",
    ),
    "port_in_use": (
        "Port is already in use",
        "Either stop the other process or use --port to specify a different port",
    ),
    "import_error": (
        "Could not import module",
        "Check your PYTHONPATH and that all dependencies are installed",
    ),
}


def hint_for_error(error_key: str, exception: Exception | None = None) -> None:
    """Print a helpful error message with hint."""
    if error_key in ERROR_HINTS:
        msg, hint = ERROR_HINTS[error_key]
        error(msg)
        if exception:
            dim(f"  {type(exception).__name__}: {exception}")
        click.echo(click.style("  hint: ", fg="cyan") + hint, err=True)
    elif exception:
        error(str(exception))


# === Tables and Structured Output ===


def table(headers: list[str], rows: list[list[str]]) -> None:
    """Print a simple table."""
    if not rows:
        dim("  (no data)")
        return

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    # Print header
    header_row = "  ".join(
        click.style(h.ljust(widths[i]), bold=True) for i, h in enumerate(headers)
    )
    click.echo(header_row)
    click.echo(click.style("─" * (sum(widths) + 2 * (len(headers) - 1)), dim=True))

    # Print rows
    for row in rows:
        click.echo("  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))


def key_value(data: dict[str, str], title: str | None = None) -> None:
    """Print key-value pairs."""
    if title:
        header(title)

    max_key_len = max(len(k) for k in data.keys()) if data else 0

    for key, value in data.items():
        key_str = click.style(key.ljust(max_key_len), fg="cyan")
        # Mask secrets
        if (
            "secret" in key.lower()
            or "password" in key.lower()
            or "token" in key.lower()
        ):
            value = "***"
        click.echo(f"  {key_str}  {value}")


# === Confirmations ===


def confirm(message: str, default: bool = False) -> bool:
    """Ask for confirmation."""
    return click.confirm(click.style("? ", fg="yellow") + message, default=default)


def prompt(message: str, default: str | None = None, hide_input: bool = False) -> str:
    """Prompt for input."""
    return click.prompt(
        click.style("? ", fg="yellow") + message,
        default=default,
        hide_input=hide_input,
    )
