"""Turn raw ingested tables into the clean core tables used by models and the database."""

from __future__ import annotations

import logging

import pandas as pd
import yaml

from pitchiq.config import CONFIG_DIR
from pitchiq.storage.parquet import Store

log = logging.getLogger(__name__)


def load_position_maps() -> tuple[dict[str, str], dict[str, str]]:
    """Return (match position -> group, season position token -> group)."""
    with (CONFIG_DIR / "positions.yaml").open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data["match_position_groups"], data["season_position_groups"]


def season_position_groups(player_match: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    """Minutes-weighted modal position group per player-season from match lineups."""
    match_map, _ = load_position_maps()
    pm = player_match.merge(matches[["match_id", "season_id"]], on="match_id")
    pm = pm.assign(group=pm["position"].map(match_map)).dropna(subset=["group"])
    mins = pm.groupby(["player_id", "season_id", "group"])["minutes"].sum().reset_index()
    best = mins.sort_values("minutes", ascending=False).drop_duplicates(["player_id", "season_id"])
    return best[["player_id", "season_id", "group"]].rename(columns={"group": "position_group"})


def build_core(store: Store) -> dict[str, int]:
    """Build ``shots``, ``player_match``, ``player_season`` and ``players``; return row counts."""
    matches = store.read("matches")
    shots = store.read("shots_raw")
    pm = store.read("player_match_raw")
    ps = store.read("player_season_us")

    if not shots.empty:
        shots = shots.astype({"minute": int, "x": float, "y": float, "xg_us": float})
        store.write("shots", shots)
    if not pm.empty:
        num = [
            "minutes",
            "goals",
            "own_goals",
            "shots",
            "assists",
            "key_passes",
            "yellow_cards",
            "red_cards",
        ]
        pm[num] = pm[num].fillna(0).astype(int)
        pm[["xg", "xa", "xg_chain", "xg_buildup"]] = (
            pm[["xg", "xa", "xg_chain", "xg_buildup"]].fillna(0.0).astype(float)
        )
        store.write("player_match", pm)

    _, season_map = load_position_maps()
    groups = (
        season_position_groups(pm, matches)
        if not pm.empty
        else pd.DataFrame(columns=["player_id", "season_id", "position_group"])
    )
    ps = ps.merge(groups, on=["player_id", "season_id"], how="left")
    fallback = ps["us_position"].fillna("").str.split().str[0].map(season_map)
    ps["position_group"] = ps["position_group"].fillna(fallback)
    store.write("player_season", ps)

    latest = ps.sort_values(["season_id", "minutes"]).drop_duplicates("player_id", keep="last")
    players = latest[
        ["player_id", "player_name", "team_id", "league_id", "season_id", "position_group"]
    ].rename(columns={"player_name": "name", "season_id": "last_season_id"})
    store.write("players", players)
    counts = {
        "shots": len(shots),
        "player_match": len(pm),
        "player_season": len(ps),
        "players": len(players),
    }
    log.info("build_core: %s", counts)
    return counts
