"""Command-line entry point: ``uv run pitchiq <command>``."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import typer

from pitchiq import __version__
from pitchiq.config import load_leagues, load_settings
from pitchiq.storage.parquet import Store

app = typer.Typer(help="PitchIQ data pipeline.", no_args_is_help=True, add_completion=False)
log = logging.getLogger("pitchiq")


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging.")) -> None:
    """PitchIQ data pipeline commands."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _summary(markdown: str) -> None:
    """Print, and append to the GitHub job summary when running in Actions."""
    typer.echo(markdown)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with Path(path).open("a", encoding="utf-8") as fh:
            fh.write(markdown + "\n\n")


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command()
def ingest(
    details: bool = typer.Option(True, help="Fetch per-match shots and lineups."),
    max_match_requests: int = typer.Option(
        0, help="Cap on per-match requests (0 = config default)."
    ),
) -> None:
    """Fetch new data from every source (incremental; cached; polite)."""
    from pitchiq.build import build_core
    from pitchiq.ingest.run import Ingestor
    from pitchiq.publish.freshness import build_freshness, write_freshness

    store, settings, leagues = Store(), load_settings(), load_leagues()
    result = Ingestor(store, settings, leagues).run(
        details=details, max_match_requests=max_match_requests or None
    )
    if store.exists("matches"):
        build_core(store)
    write_freshness(build_freshness(store, settings, leagues, result), store)
    lines = ["## Ingest", "", "| source | ok | rows | seconds | message |", "|---|---|---|---|---|"]
    for s in result.statuses:
        lines.append(
            f"| {s.source} | {'yes' if s.ok else '**NO**'} | {s.rows} | {s.seconds} | {s.message} {s.extra or ''} |"
        )
    _summary("\n".join(lines))
    if not result.ok:
        log.error("one or more sources failed; previously stored data was kept")
        raise typer.Exit(code=1)


@app.command()
def validate() -> None:
    """Run all data-quality checks (non-zero exit on a hard failure)."""
    from pitchiq.validate.checks import ValidationFailed, validate_all

    try:
        report = validate_all(Store(), load_settings(), load_leagues())
    except ValidationFailed as exc:
        _summary(f"## Validation FAILED\n\n{exc}")
        raise typer.Exit(code=1) from exc
    _summary("## Validation\n\n" + report.to_markdown())


@app.command()
def profile() -> None:
    """Print an aggregate profile of the processed data."""
    from pitchiq.profile import profile_markdown

    _summary(profile_markdown(Store()))


if __name__ == "__main__":
    sys.exit(app())
