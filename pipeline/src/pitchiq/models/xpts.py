"""Expected points from shot-level xG.

Each shot is an independent Bernoulli trial with success probability equal to its xG. We
simulate ``n_sims`` replays of every match, count goals per side, and read off
P(win/draw/loss) and expected points (3 for a win, 1 for a draw). Own goals are not shots
and are therefore excluded, which is the standard convention.

:func:`exact_outcome_probs` computes the same probabilities analytically (Poisson-binomial
convolution); tests use it to check the simulation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pitchiq.config import XPtsSettings
from pitchiq.storage.parquet import Store

WIN_POINTS, DRAW_POINTS = 3, 1


def goal_distribution(xg: np.ndarray) -> np.ndarray:
    """Exact distribution of the number of goals from independent shots."""
    dist = np.array([1.0])
    for p in xg:
        dist = np.convolve(dist, [1 - p, p])
    return dist


def exact_outcome_probs(home_xg: np.ndarray, away_xg: np.ndarray) -> tuple[float, float, float]:
    """Exact P(home win), P(draw), P(away win)."""
    h, a = goal_distribution(home_xg), goal_distribution(away_xg)
    joint = np.outer(h, a)
    return float(np.tril(joint, -1).sum()), float(np.trace(joint)), float(np.triu(joint, 1).sum())


def simulate_match(home_xg: np.ndarray, away_xg: np.ndarray, n_sims: int, rng: np.random.Generator) -> tuple[float, float, float]:
    """Monte Carlo P(home win), P(draw), P(away win)."""
    hg = (rng.random((n_sims, len(home_xg))) < home_xg).sum(axis=1)
    ag = (rng.random((n_sims, len(away_xg))) < away_xg).sum(axis=1)
    return float(np.mean(hg > ag)), float(np.mean(hg == ag)), float(np.mean(hg < ag))


def match_xpts(shots: pd.DataFrame, cfg: XPtsSettings) -> pd.DataFrame:
    """Two rows per match (one per team) with P(W/D/L) and expected points.

    Args:
        shots: Columns ``match_id, side, team_id, xg`` (own goals already excluded).
        cfg: Simulation settings.
    """
    rng = np.random.default_rng(cfg.random_seed)
    rows = []
    for match_id, g in shots.groupby("match_id", sort=True):
        h = g.loc[g["side"] == "h", "xg"].to_numpy(float)
        a = g.loc[g["side"] == "a", "xg"].to_numpy(float)
        ph, pd_, pa = simulate_match(h, a, cfg.n_sims, rng)
        for side, w, l_, xg_for, xg_against in (("h", ph, pa, h.sum(), a.sum()), ("a", pa, ph, a.sum(), h.sum())):
            rows.append(
                {
                    "match_id": match_id,
                    "side": side,
                    "p_win": w,
                    "p_draw": pd_,
                    "p_loss": l_,
                    "xpts": WIN_POINTS * w + DRAW_POINTS * pd_,
                    "xg_for": xg_for,
                    "xg_against": xg_against,
                    "n_sims": cfg.n_sims,
                }
            )
    return pd.DataFrame(rows)


def season_table(matches: pd.DataFrame, xpts: pd.DataFrame) -> pd.DataFrame:
    """Actual league table next to the xPts table, per league-season-team."""
    fin = matches[matches["status"] == "finished"]
    rows = []
    for side in ("h", "a"):
        team = fin["home_team_id"] if side == "h" else fin["away_team_id"]
        gf = fin["home_goals"] if side == "h" else fin["away_goals"]
        ga = fin["away_goals"] if side == "h" else fin["home_goals"]
        rows.append(
            pd.DataFrame(
                {
                    "match_id": fin["match_id"],
                    "league_id": fin["league_id"],
                    "season_id": fin["season_id"],
                    "team_id": team,
                    "side": side,
                    "gf": gf.astype(int),
                    "ga": ga.astype(int),
                }
            )
        )
    long = pd.concat(rows, ignore_index=True).merge(xpts, on=["match_id", "side"], how="left")
    long["w"] = (long["gf"] > long["ga"]).astype(int)
    long["d"] = (long["gf"] == long["ga"]).astype(int)
    long["l"] = (long["gf"] < long["ga"]).astype(int)
    long["pts"] = WIN_POINTS * long["w"] + DRAW_POINTS * long["d"]
    t = (
        long.groupby(["league_id", "season_id", "team_id"])
        .agg(
            played=("match_id", "size"),
            w=("w", "sum"),
            d=("d", "sum"),
            l=("l", "sum"),
            gf=("gf", "sum"),
            ga=("ga", "sum"),
            pts=("pts", "sum"),
            xg_for=("xg_for", "sum"),
            xg_against=("xg_against", "sum"),
            xpts=("xpts", "sum"),
            matches_with_xg=("xpts", "count"),
        )
        .reset_index()
    )
    t["gd"] = t["gf"] - t["ga"]
    t["pts_minus_xpts"] = t["pts"] - t["xpts"]
    t = t.sort_values(["league_id", "season_id", "pts", "gd", "gf"], ascending=[True, True, False, False, False])
    t["position"] = t.groupby(["league_id", "season_id"]).cumcount() + 1
    t = t.sort_values(["league_id", "season_id", "xpts"], ascending=[True, True, False])
    t["xpts_position"] = t.groupby(["league_id", "season_id"]).cumcount() + 1
    return t.sort_values(["league_id", "season_id", "position"]).reset_index(drop=True)


def run(store: Store, cfg: XPtsSettings, seasons: list[str]) -> pd.DataFrame:
    """Compute match xPts for ``seasons`` and the season tables; writes ``xpts_match`` and ``season_table``."""
    shots = store.read("shots").merge(store.read("shots_xg"), on="shot_id")
    matches = store.read("matches")
    shots = shots.merge(matches[["match_id", "season_id"]], on="match_id")
    shots = shots[shots["season_id"].isin(seasons) & shots["xg"].notna()]
    xp = match_xpts(shots, cfg)
    m = matches[matches["season_id"].isin(seasons)]
    side_team = pd.concat(
        [m[["match_id"]].assign(side="h", team_id=m["home_team_id"]), m[["match_id"]].assign(side="a", team_id=m["away_team_id"])]
    )
    xp = xp.merge(side_team, on=["match_id", "side"])
    store.write("xpts_match", xp)
    table = season_table(m, xp.drop(columns=["team_id"]))
    store.write("season_table", table)
    return table
