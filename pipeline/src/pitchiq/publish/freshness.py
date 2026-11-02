"""Data-freshness report: written to the store and committed to the repo as ``data-freshness.json``.

The daily commit of this file is also what keeps GitHub from pausing scheduled workflows.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from pitchiq.config import REPO_DIR, LeaguesConfig, Settings
from pitchiq.ingest.run import IngestResult
from pitchiq.storage.parquet import Store


def build_freshness(
    store: Store, settings: Settings, leagues: LeaguesConfig, result: IngestResult | None
) -> dict:
    """Assemble the freshness document."""
    now = datetime.now(UTC)
    tz = ZoneInfo(settings.timezone["display"])
    m = store.read("matches")
    per_league = {}
    for lg in leagues.leagues:
        fin = (
            m[(m["league_id"] == lg.league_id) & (m["status"] == "finished")] if not m.empty else m
        )
        latest = pd.to_datetime(fin["kickoff_utc"]).max() if not fin.empty else None
        per_league[lg.league_id] = {
            "name": lg.name,
            "latest_finished_match_utc": latest.isoformat() if latest is not None else None,
            "finished_matches_current_season": int(
                (fin["season_id"] == settings.seasons.current).sum()
            )
            if not fin.empty
            else 0,
        }
    sources = {}
    if result is not None:
        for s in result.statuses:
            sources[s.source] = {
                "ok": s.ok,
                "hard": s.hard,
                "message": s.message,
                "rows": s.rows,
                "seconds": s.seconds,
                **s.extra,
            }
    previous = store.read_json("freshness.json", {}) or {}
    last_success = previous.get("last_success_utc")
    if result is not None and result.ok:
        last_success = now.isoformat()
    return {
        "generated_utc": now.isoformat(),
        "generated_display": now.astimezone(tz).strftime("%-d %b %Y, %H:%M IST"),
        "last_success_utc": last_success,
        "season": settings.seasons.current,
        "leagues": per_league,
        "sources": sources,
    }


def write_freshness(
    doc: dict, store: Store, repo_file: Path = REPO_DIR / "data-freshness.json"
) -> None:
    """Persist to the store and the repo root."""
    store.write_json("freshness.json", doc)
    repo_file.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
