"""Base CLI that cuneus provides."""

import click
import importlib
import sys
from typing import Any, cast

from .core.settings import Settings


def import_from_string(import_str: str) -> Any:
    """Import an object from a module:attribute string."""
    module_path, _, attr = import_str.partition(":")
    if not attr:
        attr = "app"  # default attribute name

    module = importlib.import_module(module_path)
    return getattr(module, attr)


def get_user_cli() -> click.Group | None:
    """Attempt to load user's CLI from config."""
    config = Settings()

    try:
        return cast(click.Group, import_from_string(config.cli_module))
    except (ImportError, AttributeError) as e:
        click.echo(
            f"Warning: Could not load CLI from {config.cli_module}: {e}", err=True
        )

    return None


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Cuneus CLI - FastAPI application framework."""
    ctx.ensure_object(dict)


@cli.command()
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=8000, type=int, help="Bind port")
def dev(host: str, port: int) -> None:
    """Run the application server."""
    import uvicorn

    config = Settings()

    uvicorn.run(
        config.app_module,
        host=host,
        port=port,
        reload=True,
    )


@cli.command()
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=8000, type=int, help="Bind port")
@click.option("--workers", default=1, type=int, help="Number of workers")
def prod(host: str, port: int, workers: int) -> None:
    """Run the application server."""
    import uvicorn

    config = Settings()

    uvicorn.run(
        config.app_module,
        host=host,
        port=port,
        workers=workers,
    )


@cli.command()
def routes() -> None:
    """List all registered routes."""
    config = Settings()
    app = import_from_string(config.app_module)

    for route in app.routes:
        if hasattr(route, "methods"):
            methods = ",".join(route.methods - {"HEAD", "OPTIONS"})
            click.echo(f"{methods:8} {route.path}")


class CuneusCLI(click.Group):
    """Merges base cuneus commands with user's app CLI."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._user_cli: click.Group | None = None
        self._user_cli_loaded = False

        # Register base commands directly
        self.add_command(dev)
        self.add_command(prod)
        self.add_command(routes)

    @property
    def user_cli(self) -> click.Group | None:
        if not self._user_cli_loaded:
            self._user_cli = get_user_cli()
            self._user_cli_loaded = True
        return self._user_cli

    def list_commands(self, ctx: click.Context) -> list[str]:
        commands = set(super().list_commands(ctx))
        if self.user_cli:
            commands.update(self.user_cli.list_commands(ctx))
        return sorted(commands)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        # User CLI takes priority
        if self.user_cli:
            cmd = self.user_cli.get_command(ctx, cmd_name)
            if cmd:
                return cmd
        return super().get_command(ctx, cmd_name)


# This is the actual entry point
main = CuneusCLI(help="Cuneus CLI - FastAPI application framework")


if __name__ == "__main__":
    main()
