"""Publish the database window (current + previous seasons) from the Parquet store to Postgres.

Everything happens in one transaction, so the site never sees a half-published state:

* reference tables (leagues, teams, players) are upserted;
* match-level tables are upserted for the window, and seasons that fell out of the
  window are deleted (shots, odds, predictions... cascade);
* fully derived tables (tables, percentiles, similarity...) are replaced for the window;
* predictions are insert-only (the DB trigger rejects anything stored after kickoff).

Rows are streamed with ``COPY`` into temporary tables and merged with ``INSERT ... ON
CONFLICT``. The run fails if the database grows beyond ``database.max_size_mb``.
"""

from __future__ import annotations

import json
import logging
import math
import os
from collections.abc import Iterable

import numpy as np
import pandas as pd

from pitchiq.config import LeaguesConfig, Settings, season_range
from pitchiq.evaluation.bookmaker import implied_probs
from pitchiq.models.xg.features import geometry
from pitchiq.storage.parquet import Store

log = logging.getLogger(__name__)
BYTES_PER_MB = 1024 * 1024


class PublishError(RuntimeError):
    """Publishing failed (connection, constraint or size limit)."""


# ------------------------------------------------------------------ frame preparation (pure)


def window_seasons(settings: Settings) -> list[str]:
    """Seasons kept in the database."""
    s = settings.seasons
    return season_range(s.first, s.current)[-s.db_window :]


def prepare(store: Store, settings: Settings, leagues: LeaguesConfig) -> dict[str, pd.DataFrame]:
    """Build every table exactly as it is stored in Postgres (column order = DB order)."""
    win = window_seasons(settings)
    matches = store.read("matches")
    matches = matches[matches["season_id"].isin(win)].copy()
    ids = set(matches["match_id"])
    out: dict[str, pd.DataFrame] = {}

    out["leagues"] = pd.DataFrame(
        [
            {
                "league_id": lg.league_id,
                "name": lg.name,
                "country": lg.country,
                "n_teams": lg.n_teams,
            }
            for lg in leagues.leagues
        ]
    )
    teams = store.read("teams")
    out["teams"] = teams[["team_id", "name", "league_id", "country"]]

    shots = store.read("shots")
    shots = shots[shots["match_id"].isin(ids)]
    sx = store.read("shots_xg")
    if not sx.empty:
        shots = shots.merge(sx[["shot_id", "xg"]], on="shot_id", how="left")
    else:
        shots = shots.assign(xg=np.nan)
    match_xg = shots.groupby(["match_id", "side"])["xg"].sum(min_count=1).unstack()
    match_xg = match_xg.reindex(columns=["h", "a"])
    matches["home_xg"] = matches["match_id"].map(match_xg["h"]) if not match_xg.empty else np.nan
    matches["away_xg"] = matches["match_id"].map(match_xg["a"]) if not match_xg.empty else np.nan
    out["matches"] = matches[
        [
            "match_id",
            "league_id",
            "season_id",
            "kickoff_utc",
            "home_team_id",
            "away_team_id",
            "status",
            "home_goals",
            "away_goals",
            "home_xg",
            "away_xg",
            "home_xg_us",
            "away_xg_us",
        ]
    ].rename(columns={"home_xg_us": "home_xg_understat", "away_xg_us": "away_xg_understat"})

    odds = store.read("odds")
    odds = odds[odds["match_id"].isin(ids)]
    if not odds.empty:
        odds = implied_probs(odds)
    out["odds"] = odds.reindex(
        columns=[
            "match_id",
            "bookmaker",
            "kind",
            "odds_h",
            "odds_d",
            "odds_a",
            "p_h",
            "p_d",
            "p_a",
            "overround",
            "captured_at",
        ]
    )

    if not shots.empty:
        geo = geometry(shots["x"], shots["y"], settings.xg)
        shots = shots.assign(
            x_m=shots["x"] * settings.xg.pitch_length_m,
            y_m=shots["y"] * settings.xg.pitch_width_m,
            distance_m=geo["distance_m"],
            angle_rad=geo["angle_rad"],
            is_goal=shots["result"] == "Goal",
            xg_understat=shots["xg_us"],
        )
    out["shots"] = shots.reindex(
        columns=[
            "shot_id",
            "match_id",
            "team_id",
            "player_id",
            "side",
            "minute",
            "x_m",
            "y_m",
            "distance_m",
            "angle_rad",
            "situation",
            "shot_type",
            "last_action",
            "result",
            "is_goal",
            "xg",
            "xg_understat",
        ]
    )

    pm = store.read("player_match")
    pm = pm[pm["match_id"].isin(ids)] if not pm.empty else pm
    out["player_match"] = pm.reindex(
        columns=[
            "match_id",
            "player_id",
            "team_id",
            "position",
            "minutes",
            "goals",
            "own_goals",
            "assists",
            "shots",
            "key_passes",
            "yellow_cards",
            "red_cards",
            "xg",
            "xa",
            "xg_chain",
            "xg_buildup",
        ]
    )

    ps = store.read("player_season")
    ps = ps[ps["season_id"].isin(win)] if not ps.empty else ps
    out["player_season"] = ps.reindex(
        columns=[
            "player_id",
            "season_id",
            "league_id",
            "team_id",
            "team_names",
            "position_group",
            "games",
            "minutes",
            "goals",
            "np_goals",
            "assists",
            "shots",
            "key_passes",
            "yellow_cards",
            "red_cards",
            "xg",
            "npxg",
            "xa",
            "xg_chain",
            "xg_buildup",
            "age",
            "nation",
        ]
    )

    players = store.read("players")
    born = (
        ps.dropna(subset=["born"]).drop_duplicates("player_id", keep="last").set_index("player_id")
        if "born" in ps
        else pd.DataFrame()
    )
    if not players.empty:
        players = players[
            players["player_id"].isin(
                set(ps["player_id"]) | set(pm["player_id"]) | set(shots["player_id"])
            )
        ].copy()
        players["born"] = players["player_id"].map(born["born"]) if "born" in born else pd.NA
        players["nation"] = players["player_id"].map(born["nation"]) if "nation" in born else pd.NA
    out["players"] = players.reindex(
        columns=[
            "player_id",
            "name",
            "team_id",
            "league_id",
            "last_season_id",
            "position_group",
            "born",
            "nation",
        ]
    )

    first_day = pd.Timestamp(f"20{win[0][:2]}-07-01").date()
    elo = store.read("elo")
    elo = elo[pd.to_datetime(elo["valid_to"]).dt.date >= first_day] if not elo.empty else elo
    out["elo"] = elo.reindex(columns=["team_id", "valid_from", "valid_to", "elo"])

    xp = store.read("xpts_match")
    xp = xp[xp["match_id"].isin(ids)] if not xp.empty else xp
    out["xpts_match"] = xp.reindex(
        columns=[
            "match_id",
            "team_id",
            "side",
            "p_win",
            "p_draw",
            "p_loss",
            "xpts",
            "xg_for",
            "xg_against",
            "n_sims",
        ]
    )
    st = store.read("season_table")
    st = st[st["season_id"].isin(win)] if not st.empty else st
    out["season_table"] = st.reindex(
        columns=[
            "league_id",
            "season_id",
            "team_id",
            "position",
            "xpts_position",
            "played",
            "w",
            "d",
            "l",
            "gf",
            "ga",
            "gd",
            "pts",
            "xg_for",
            "xg_against",
            "xpts",
            "pts_minus_xpts",
        ]
    )

    preds = store.read("predictions")
    preds = preds[preds["match_id"].isin(ids)] if not preds.empty else preds
    out["predictions"] = preds.reindex(
        columns=[
            "match_id",
            "model",
            "created_utc",
            "p_home",
            "p_draw",
            "p_away",
            "exp_home_goals",
            "exp_away_goals",
            "top_score",
            "score_grid",
        ]
    )

    bt = store.read("backtest_summary")
    out["backtest_summary"] = bt.reindex(
        columns=["scope", "league_id", "season_id", "model", "n", "log_loss", "brier", "rps"]
    )
    cal = store.read("backtest_calibration")
    cal = cal.assign(family="predictor") if not cal.empty else cal
    xg_meta = store.read_json("xg/metrics.json", {}) or {}
    xg_cal = [
        pd.DataFrame(rows).assign(family="xg", model=name, outcome="goal")
        for name, rows in (xg_meta.get("calibration") or {}).items()
    ]
    cal_all = (
        pd.concat([c for c in [cal, *xg_cal] if not c.empty], ignore_index=True)
        if (not cal.empty or xg_cal)
        else pd.DataFrame()
    )
    out["calibration"] = cal_all.reindex(
        columns=["family", "model", "outcome", "bin", "mean_pred", "obs_freq", "n"]
    )

    meta = []
    for name, path in (
        ("xg", "xg/metrics.json"),
        ("predictor", "predictor/meta.json"),
        ("player_link", "player_link_stats.json"),
    ):
        doc = store.read_json(path)
        if doc:
            if name == "xg":
                doc = {k: v for k, v in doc.items() if k != "calibration"}
            meta.append({"name": name, "meta": doc})
    out["model_meta"] = pd.DataFrame(meta, columns=["name", "meta"])

    emb = store.read("player_embeddings")
    out["player_embeddings"] = emb.reindex(
        columns=[
            "player_id",
            "season_id",
            "league_id",
            "team_id",
            "position_group",
            "minutes",
            "age",
            "embedding",
        ]
    )
    out["player_similar"] = store.read("player_similar").reindex(
        columns=[
            "player_id",
            "season_id",
            "league_id",
            "rank",
            "other_player_id",
            "other_league_id",
            "similarity",
        ]
    )
    out["player_percentiles"] = store.read("player_percentiles").reindex(
        columns=[
            "player_id",
            "season_id",
            "league_id",
            "position_group",
            "metric",
            "per90",
            "percentile",
        ]
    )
    fresh = store.read_json("freshness.json", {}) or {}
    out["freshness"] = (
        pd.DataFrame([{"id": True, "doc": fresh}]) if fresh else pd.DataFrame(columns=["id", "doc"])
    )
    return out


# ------------------------------------------------------------------ database writes

# table -> (conflict keys or None for plain insert, update on conflict?)
UPSERT = {
    "leagues": ["league_id"],
    "teams": ["team_id"],
    "players": ["player_id"],
    "matches": ["match_id"],
    "odds": ["match_id", "bookmaker", "kind"],
    "shots": ["shot_id"],
    "player_match": ["match_id", "player_id"],
}
# Replaced wholesale inside the transaction.
REPLACE = [
    "player_season",
    "elo",
    "xpts_match",
    "season_table",
    "backtest_summary",
    "calibration",
    "model_meta",
    "player_embeddings",
    "player_similar",
    "player_percentiles",
    "freshness",
]
ORDER = [
    "leagues",
    "teams",
    "players",
    "matches",
    "odds",
    "shots",
    "player_match",
    "player_season",
    "elo",
    "xpts_match",
    "season_table",
    "predictions",
    "backtest_summary",
    "calibration",
    "model_meta",
    "player_embeddings",
    "player_similar",
    "player_percentiles",
    "freshness",
]


def _clean(value: object) -> object:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict | list):
        return json.dumps(value, default=str)
    if isinstance(value, np.ndarray):
        return "[" + ",".join(f"{v:.6f}" for v in value) + "]"
    if isinstance(value, np.generic):
        return value.item()
    return value


def rows(df: pd.DataFrame) -> Iterable[tuple]:
    """Yield DB-ready tuples (NaN -> NULL, dict/list -> JSON, arrays -> vector text)."""
    for rec in df.itertuples(index=False, name=None):
        yield tuple(_clean(v) for v in rec)


def _copy(cur: object, table: str, df: pd.DataFrame) -> None:
    cols = ", ".join(df.columns)
    with cur.copy(f"COPY {table} ({cols}) FROM STDIN") as cp:  # type: ignore[attr-defined]
        for r in rows(df):
            cp.write_row(r)


def publish(
    store: Store, settings: Settings, leagues: LeaguesConfig, dsn: str | None = None
) -> dict[str, int]:
    """Publish the window in one transaction; returns rows written per table."""
    import psycopg

    dsn = dsn or os.environ.get("SUPABASE_DB_URL")
    if not dsn:
        raise PublishError("SUPABASE_DB_URL is not set")
    frames = prepare(store, settings, leagues)
    win = window_seasons(settings)
    counts: dict[str, int] = {}
    with psycopg.connect(dsn, autocommit=False) as conn, conn.cursor() as cur:
        cur.execute("set local search_path = core, public, extensions")
        cur.execute("delete from core.matches where season_id <> all(%s)", (win,))
        for table in ORDER:
            df = frames[table]
            counts[table] = len(df)
            if table in REPLACE:
                cur.execute(f"delete from core.{table}")
                if not df.empty:
                    _copy(cur, f"core.{table}", df)
                continue
            if df.empty:
                continue
            tmp = f"tmp_{table}"
            cur.execute(
                f"create temp table {tmp} (like core.{table} including defaults) on commit drop"
            )
            _copy(cur, tmp, df)
            cols = ", ".join(df.columns)
            if table == "predictions":
                # Insert-only: snapshots are immutable; the trigger rejects post-kickoff rows.
                cur.execute(
                    f"insert into core.{table} ({cols}) select {cols} from {tmp} t "
                    "where t.created_utc < (select kickoff_utc from core.matches m where m.match_id = t.match_id) "
                    "on conflict do nothing"
                )
                continue
            keys = UPSERT[table]
            updates = ", ".join(f"{c} = excluded.{c}" for c in df.columns if c not in keys)
            cur.execute(
                f"insert into core.{table} ({cols}) select {cols} from {tmp} "
                f"on conflict ({', '.join(keys)}) do update set {updates}"
            )
        cur.execute("select pg_database_size(current_database())")
        size_mb = cur.fetchone()[0] / BYTES_PER_MB
        counts["database_size_mb"] = int(size_mb)
        if size_mb > settings.database.max_size_mb:
            conn.rollback()
            raise PublishError(
                f"database is {size_mb:.0f} MB, above the {settings.database.max_size_mb} MB limit"
            )
        conn.commit()
    log.info("published: %s", counts)
    return counts
