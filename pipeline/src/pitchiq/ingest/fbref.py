"""FBref basic player info (age/birth year, position, nationality, minutes) via soccerdata.

FBref is a *soft* source: it is only used for age, nationality and a second opinion on
position. It is refreshed weekly, cached by soccerdata (which also rate-limits to one
request every 7 s), and a failure never blocks the daily run. FBref's advanced Opta stats
were removed in January 2026, so only the "standard" table is read.
"""

from __future__ import annotations

import logging

import pandas as pd

from pitchiq.config import LeaguesConfig
from pitchiq.storage.parquet import Store

log = logging.getLogger(__name__)


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index()
    df.columns = [
        "_".join(str(p) for p in col if p and not str(p).startswith("Unnamed")).strip("_").lower()
        if isinstance(col, tuple)
        else str(col).lower()
        for col in df.columns
    ]
    return df


def fetch_players(leagues: LeaguesConfig, seasons: list[str], store: Store) -> pd.DataFrame:
    """Return one row per FBref player-team-season in the selected leagues."""
    import soccerdata as sd

    reader = sd.FBref(
        leagues=[lg.sources.soccerdata for lg in leagues.leagues],
        seasons=seasons,
        data_dir=store.raw / "fbref",
        headless=True,
    )
    raw = _flatten(reader.read_player_season_stats(stat_type="standard"))
    league_map = {lg.sources.soccerdata: lg.league_id for lg in leagues.leagues}
    minutes_col = next((c for c in raw.columns if c.endswith("min") and "playing" in c), None)
    out = pd.DataFrame(
        {
            "league_id": raw["league"].map(league_map),
            "season_id": raw["season"].astype(str),
            "fbref_team": raw["team"].astype(str),
            "fbref_player": raw["player"].astype(str),
            "nation": raw.get("nation"),
            "fbref_pos": raw.get("pos"),
            "born": pd.to_numeric(raw.get("born"), errors="coerce").astype("Int64"),
            "minutes": pd.to_numeric(raw[minutes_col], errors="coerce") if minutes_col else pd.NA,
        }
    )
    return out.dropna(subset=["league_id"])
