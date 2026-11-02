"""Command-line entry point: ``uv run pitchiq <command>``."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pandas as pd
import typer

from pitchiq import __version__
from pitchiq.config import PIPELINE_DIR, load_leagues, load_settings, season_range
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


REPORTS = PIPELINE_DIR / "reports"


def _db_seasons() -> list[str]:
    s = load_settings().seasons
    return season_range(s.first, s.current)[-s.db_window :]


@app.command()
def fbref(force: bool = typer.Option(False, help="Refresh even if fetched recently.")) -> None:
    """Weekly, soft: FBref birth year / nation / position, linked to Understat players."""
    from pitchiq.canonical.players import link_players
    from pitchiq.ingest.fbref import fetch_players

    store, settings, leagues = Store(), load_settings(), load_leagues()
    meta = store.read_json("fbref_meta.json", {}) or {}
    age_days = (
        (pd.Timestamp.now(tz="UTC") - pd.Timestamp(meta["fetched_utc"])).days
        if meta.get("fetched_utc")
        else None
    )
    if settings.scraping.fbref_enabled and (
        force or age_days is None or age_days >= settings.scraping.fbref_refresh_days
    ):
        try:
            players = fetch_players(leagues, _db_seasons(), store)
            store.write("fbref_players", players)
            store.write_json(
                "fbref_meta.json",
                {"fetched_utc": pd.Timestamp.now(tz="UTC").isoformat(), "rows": len(players)},
            )
        except Exception as exc:  # noqa: BLE001 - FBref is a soft source: never fail the run
            log.warning("FBref fetch failed (soft source, keeping previous data): %s", exc)
    stats = link_players(store, settings)
    _summary(f"## FBref player linking\n\n{stats}")


@app.command("train-xg")
def train_xg() -> None:
    """Train + evaluate the xG model, save production/backtest models, score all shots."""
    from pitchiq.models.xg.train import evaluate, score_all

    store = Store()
    summary = evaluate(load_settings(), store, REPORTS)
    score_all(store)
    _summary((REPORTS / "xg_report.md").read_text(encoding="utf-8"))
    log.info("chosen xG model: %s", summary["chosen_model"])


@app.command("score-xg")
def score_xg() -> None:
    """Apply the saved xG models to all shots (trains first if no model exists)."""
    from pitchiq.models.xg.train import score_all

    store = Store()
    if not (store.artifacts / "xg" / "production.joblib").exists():
        train_xg()
        return
    score_all(store)


@app.command()
def xpts() -> None:
    """Shot-level xPts simulation and season tables for the database window."""
    from pitchiq.models.xpts import run

    table = run(Store(), load_settings().xpts, _db_seasons())
    log.info("season_table rows: %d", len(table))


@app.command()
def backtest() -> None:
    """Walk-forward backtest of the match predictor vs bookmaker closing odds."""
    from pitchiq.models.predictor.backtest import run

    run(Store(), load_settings(), load_leagues(), REPORTS)
    _summary((REPORTS / "predictor_report.md").read_text(encoding="utf-8"))


@app.command()
def predict() -> None:
    """Predict upcoming fixtures and append them to the git ledger."""
    from pitchiq.models.predictor.predict import append_ledger, predict_upcoming

    preds = predict_upcoming(Store(), load_settings(), load_leagues(), pd.Timestamp.now(tz="UTC"))
    n = append_ledger(preds)
    _summary(
        f"## Predictions\n\n{preds['match_id'].nunique() if not preds.empty else 0} fixtures, {n} ledger rows appended"
    )


@app.command()
def similarity() -> None:
    """Player embeddings, top-10 similar players and percentiles."""
    from pitchiq.models.similarity import run

    stats = run(Store(), load_settings().similarity, _db_seasons())
    _summary(f"## Similarity\n\n{stats}")


@app.command()
def models() -> None:
    """Daily model refresh: score new shots, xPts, predictions, similarity."""
    score_xg()
    xpts()
    predict()
    similarity()


@app.command()
def publish() -> None:
    """Publish the database window to Supabase (needs SUPABASE_DB_URL)."""
    from pitchiq.publish.supabase import publish as do_publish

    counts = do_publish(Store(), load_settings(), load_leagues())
    _summary("## Published to Supabase\n\n" + "\n".join(f"- {k}: {v:,}" for k, v in counts.items()))


@app.command()
def revalidate() -> None:
    """Ask the website to refresh its cache (needs SITE_URL and REVALIDATE_SECRET)."""
    import os

    import requests

    url, secret = os.environ.get("SITE_URL"), os.environ.get("REVALIDATE_SECRET")
    if not url or not secret:
        log.warning("SITE_URL / REVALIDATE_SECRET not set; skipping revalidation")
        return
    resp = requests.post(
        f"{url.rstrip('/')}/api/revalidate",
        headers={"Authorization": f"Bearer {secret}"},
        timeout=30,
    )
    if resp.status_code != 200:
        log.error("revalidation failed: HTTP %s %s", resp.status_code, resp.text[:200])
        raise typer.Exit(code=1)
    log.info("site revalidated")


if __name__ == "__main__":
    sys.exit(app())
