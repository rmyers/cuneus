"""
CLI tools for application management.

Reads configuration from pyproject.toml:

    [tool.qtip]
    app_name = "myapp"
    app_module = "myapp.main:application"
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import click

from cuneus.core.application import load_pyproject_config, DEFAULT_TOOL_NAME
from cuneus.cli.console import (
    info,
    success,
    warning,
    error,
    fatal,
    dim,
    header,
    step,
    hint_for_error,
    key_value,
    confirm,
    table,
)


def get_config() -> dict:
    """Load configuration from pyproject.toml."""
    config = load_pyproject_config()
    if not config:
        hint_for_error("no_pyproject")
        sys.exit(1)
    return config


def get_app():
    """Load the Application instance."""
    config = get_config()
    module_path = config.get("app_module", "app.main:app")

    try:
        module_name, attr_name = module_path.rsplit(":", 1)
        module = importlib.import_module(module_name)
        return getattr(module, attr_name)
    except ImportError as e:
        hint_for_error("import_error", e)
        dim(f"  Tried to import: {module_path}")
        sys.exit(1)
    except AttributeError as e:
        hint_for_error("no_app_module", e)
        sys.exit(1)


@click.group()
@click.option("--config", "-c", type=click.Path(exists=True), help="Path to pyproject.toml")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.pass_context
def cli(ctx: click.Context, config: str | None, verbose: bool) -> None:
    """Application management CLI."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    if config:
        ctx.obj["config_path"] = config


@cli.command()
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=8000, type=int, help="Bind port")
@click.option("--workers", default=1, type=int, help="Number of workers")
@click.option("--reload", is_flag=True, help="Enable auto-reload")
@click.pass_context
def run(ctx: click.Context, host: str, port: int, workers: int, reload: bool) -> None:
    """Run the application server."""
    import uvicorn

    config = get_config()
    app_module = config.get("app_module", "app.main:app")

    # Convert Application reference to FastAPI app reference
    if ":application" in app_module:
        fastapi_module = app_module.replace(":application", ":app")
    else:
        fastapi_module = app_module

    info(f"Starting {config.get('app_name', 'app')}")
    dim(f"  Module: {fastapi_module}")
    dim(f"  Address: http://{host}:{port}")

    if reload:
        warning("Running in reload mode (not for production)")

    if workers > 1 and reload:
        warning("--reload is incompatible with multiple workers, using 1 worker")
        workers = 1

    click.echo()

    try:
        uvicorn.run(
            fastapi_module,
            host=host,
            port=port,
            workers=workers,
            reload=reload,
            log_level="info",
        )
    except OSError as e:
        if "address already in use" in str(e).lower():
            hint_for_error("port_in_use", e)
        else:
            raise


@cli.group()
def db() -> None:
    """Database management commands."""
    pass


@db.command()
@click.option("-m", "--message", required=True, help="Migration message")
def migrate(message: str) -> None:
    """Generate a new migration."""
    from alembic import command
    from alembic.util.exc import CommandError

    info(f"Creating migration: {message}")

    try:
        with step("Generating migration"):
            alembic_cfg = _get_alembic_config()
            command.revision(alembic_cfg, message=message, autogenerate=True)
        success(f"Created migration: {message}")
    except CommandError as e:
        if "Target database is not up to date" in str(e):
            error("Database is not up to date")
            dim("  hint: Run 'db upgrade' first, then create the migration")
        else:
            error(f"Migration failed: {e}")
        sys.exit(1)


@db.command()
@click.option("--revision", default="head", help="Target revision")
def upgrade(revision: str) -> None:
    """Upgrade database to a revision."""
    from alembic import command
    from sqlalchemy.exc import OperationalError

    info(f"Upgrading database to: {revision}")

    try:
        with step("Running migrations"):
            alembic_cfg = _get_alembic_config()
            command.upgrade(alembic_cfg, revision)
        success("Database upgraded successfully")
    except OperationalError as e:
        hint_for_error("database_connection", e)
        sys.exit(1)


@db.command()
@click.option("--revision", default="-1", help="Target revision")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def downgrade(revision: str, yes: bool) -> None:
    """Downgrade database to a revision."""
    from alembic import command

    if not yes:
        warning("This will downgrade your database and may cause data loss")
        if not confirm("Are you sure you want to continue?"):
            info("Aborted")
            return

    info(f"Downgrading database to: {revision}")

    with step("Running downgrade"):
        alembic_cfg = _get_alembic_config()
        command.downgrade(alembic_cfg, revision)

    success("Database downgraded successfully")


@db.command()
def history() -> None:
    """Show migration history."""
    from alembic import command
    from io import StringIO

    header("Migration History")
    alembic_cfg = _get_alembic_config()
    command.history(alembic_cfg, verbose=True)


@db.command()
def current() -> None:
    """Show current revision."""
    from alembic import command

    header("Current Database Revision")
    alembic_cfg = _get_alembic_config()
    command.current(alembic_cfg, verbose=True)


@db.command()
def heads() -> None:
    """Show migration heads (useful for detecting conflicts)."""
    from alembic import command

    header("Migration Heads")
    alembic_cfg = _get_alembic_config()
    command.heads(alembic_cfg, verbose=True)


@db.command()
def check() -> None:
    """Check if database is up to date."""
    from alembic.script import ScriptDirectory
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine

    alembic_cfg = _get_alembic_config()

    with step("Checking database status"):
        script = ScriptDirectory.from_config(alembic_cfg)
        head = script.get_current_head()

        db_url = alembic_cfg.get_main_option("sqlalchemy.url")
        if db_url is None:
            warning('unable to check "sqlalchemy.url" is missing')
            return
        engine = create_engine(db_url)

        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current = context.get_current_revision()

    if current == head:
        success("Database is up to date")
    else:
        warning(f"Database is behind: {current} → {head}")
        dim("  Run 'db upgrade' to apply pending migrations")


def _get_alembic_config():
    """Get Alembic config with database URL from settings."""
    from alembic.config import Config

    alembic_ini = Path("alembic.ini")
    if not alembic_ini.exists():
        fatal("alembic.ini not found", hint="Run 'alembic init alembic' to create it")

    alembic_cfg = Config("alembic.ini")

    app = get_app()
    if hasattr(app.settings, "database_url"):
        db_url = app.settings.database_url
        if db_url.startswith("postgresql+asyncpg://"):
            db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    else:
        fatal(
            "No database_url in settings",
            hint="Add database_url to your Settings class",
        )

    return alembic_cfg


@cli.command()
def shell() -> None:
    """Start an interactive shell with app context."""
    import asyncio
    import code

    app = get_app()

    info(f"Starting {app.settings.app_name} shell")

    with step("Building application"):
        fastapi_app = app.build()

    with step("Running startup hooks"):

        async def setup():
            async with asyncio.timeout(30):
                ctx = fastapi_app.router.lifespan_context(fastapi_app)
                await ctx.__aenter__()
                return ctx

        ctx = asyncio.run(setup())

    success("Shell ready")
    click.echo()

    banner = f"""{click.style(app.settings.app_name, fg="cyan", bold=True)} Interactive Shell

Available objects:
  {click.style("app", fg="green")}          Application instance
  {click.style("fastapi_app", fg="green")}  FastAPI instance
  {click.style("settings", fg="green")}     Application settings
  {click.style("state", fg="green")}        app.state (db_engine, redis, etc.)
"""

    local_vars = {
        "app": app,
        "fastapi_app": fastapi_app,
        "settings": app.settings,
        "state": fastapi_app.state,
    }

    code.interact(banner=banner, local=local_vars)


@cli.command("config")
def show_config() -> None:
    """Show current configuration."""
    config = get_config()

    header("Configuration")
    key_value(config)

    # Show where config was loaded from
    click.echo()
    dim(f"  Source: pyproject.toml [tool.{DEFAULT_TOOL_NAME}]")


@cli.command()
def health() -> None:
    """Verify configuration and connectivity."""
    import asyncio

    header("Configuration Check")

    # Check config loads
    with step("Loading configuration"):
        config = get_config()

    # Check app loads
    with step("Loading application"):
        app = get_app()

    with step("Building FastAPI app"):
        fastapi_app = app.build()

    # Check connections
    header("Connectivity Check")

    async def check_connections():
        async with asyncio.timeout(10):
            ctx = fastapi_app.router.lifespan_context(fastapi_app)
            await ctx.__aenter__()

            # Check database
            if hasattr(fastapi_app.state, "db_engine"):
                with step("Database connection"):
                    async with fastapi_app.state.db_engine.connect() as conn:
                        await conn.execute("SELECT 1")

            # Check Redis
            if hasattr(fastapi_app.state, "redis") and fastapi_app.state.redis:
                with step("Redis connection"):
                    await fastapi_app.state.redis.ping()

            await ctx.__aexit__(None, None, None)

    try:
        asyncio.run(check_connections())
        click.echo()
        success("All checks passed!")
    except Exception as e:
        click.echo()
        error(f"Check failed: {e}")
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
