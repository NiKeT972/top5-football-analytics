"""Command-line entry point. Commands are added phase by phase."""

import typer

from pitchiq import __version__

app = typer.Typer(help="PitchIQ data pipeline.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """PitchIQ data pipeline commands."""


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)
