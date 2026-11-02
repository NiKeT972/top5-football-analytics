"""Pre-match features for the LightGBM match model.

Every feature uses only information available before kickoff: rolling statistics are
shifted by one match, and Elo is the rating valid the day before kickoff.

Limitation (documented on the Methodology page): rest days count league matches only,
because cup and European fixtures are not in our sources.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pitchiq.config import GBMSettings

WIN, DRAW = 3, 1
MIN_PERIODS = 3
FEATURES = [
    "elo_home",
    "elo_away",
    "elo_diff",
    "h_xg_for",
    "h_xg_against",
    "a_xg_for",
    "a_xg_against",
    "h_goals_for",
    "h_goals_against",
    "a_goals_for",
    "a_goals_against",
    "h_form",
    "a_form",
    "h_rest_days",
    "a_rest_days",
    "xg_diff_form",
]


def team_match_long(matches: pd.DataFrame, match_xg: pd.DataFrame) -> pd.DataFrame:
    """One row per (team, finished match) with goals, xG and points from that team's view."""
    m = matches[matches["status"] == "finished"].merge(match_xg, on="match_id", how="left")
    parts = []
    for team, gf, ga, xf, xa in (
        ("home_team_id", "home_goals", "away_goals", "home_xg", "away_xg"),
        ("away_team_id", "away_goals", "home_goals", "away_xg", "home_xg"),
    ):
        parts.append(
            pd.DataFrame(
                {
                    "match_id": m["match_id"],
                    "kickoff_utc": m["kickoff_utc"],
                    "team_id": m[team],
                    "gf": m[gf].astype(float),
                    "ga": m[ga].astype(float),
                    "xg_for": m[xf].astype(float),
                    "xg_against": m[xa].astype(float),
                }
            )
        )
    long = pd.concat(parts, ignore_index=True)
    long["pts"] = np.where(
        long["gf"] > long["ga"], WIN, np.where(long["gf"] == long["ga"], DRAW, 0)
    )
    return long.sort_values(["team_id", "kickoff_utc"]).reset_index(drop=True)


def _rolling_state(long: pd.DataFrame, cfg: GBMSettings) -> pd.DataFrame:
    """Per team, the rolling state *after* each match (to be used for the team's next match)."""
    g = long.groupby("team_id")
    n, f = cfg.rolling_window_matches, cfg.form_window_matches
    state = pd.DataFrame(
        {
            "team_id": long["team_id"],
            "kickoff_utc": long["kickoff_utc"],
            "xg_for": g["xg_for"].transform(lambda s: s.rolling(n, min_periods=MIN_PERIODS).mean()),
            "xg_against": g["xg_against"].transform(
                lambda s: s.rolling(n, min_periods=MIN_PERIODS).mean()
            ),
            "goals_for": g["gf"].transform(lambda s: s.rolling(n, min_periods=MIN_PERIODS).mean()),
            "goals_against": g["ga"].transform(
                lambda s: s.rolling(n, min_periods=MIN_PERIODS).mean()
            ),
            "form": g["pts"].transform(lambda s: s.rolling(f, min_periods=1).mean()),
        }
    )
    return state.sort_values("kickoff_utc")


def elo_asof(elo: pd.DataFrame, team: pd.Series, when: pd.Series) -> np.ndarray:
    """Elo of each team valid on the day before ``when`` (NaN if unknown)."""
    if elo.empty:
        return np.full(len(team), np.nan)
    e = elo.assign(
        valid_from=pd.to_datetime(elo["valid_from"]).astype("datetime64[ns]"),
        valid_to=pd.to_datetime(elo["valid_to"]).astype("datetime64[ns]"),
    )
    q = pd.DataFrame(
        {
            "team_id": team.to_numpy(),
            "day": (pd.to_datetime(when).dt.tz_convert(None) - pd.Timedelta(days=1))
            .dt.normalize()
            .astype("datetime64[ns]")
            .to_numpy(),
        }
    )
    q["_i"] = np.arange(len(q))
    merged = pd.merge_asof(
        q.sort_values("day"),
        e.sort_values("valid_from"),
        left_on="day",
        right_on="valid_from",
        by="team_id",
        direction="backward",
    )
    merged.loc[merged["day"] > merged["valid_to"], "elo"] = np.nan
    return merged.sort_values("_i")["elo"].to_numpy()


def build_match_features(
    matches: pd.DataFrame, match_xg: pd.DataFrame, elo: pd.DataFrame, cfg: GBMSettings
) -> pd.DataFrame:
    """Feature rows for every match (finished and upcoming).

    Args:
        matches: The matches table.
        match_xg: ``match_id, home_xg, away_xg`` (the xG model to use for rolling form).
        elo: ``team_id, valid_from, valid_to, elo``.
        cfg: Window settings.

    """
    matches = matches.assign(
        kickoff_utc=pd.to_datetime(matches["kickoff_utc"], utc=True).astype("datetime64[ns, UTC]")
    )
    long = team_match_long(matches, match_xg)
    state = _rolling_state(long, cfg)
    target = matches.sort_values("kickoff_utc").reset_index(drop=True)
    out = target[
        [
            "match_id",
            "league_id",
            "season_id",
            "kickoff_utc",
            "home_team_id",
            "away_team_id",
            "home_goals",
            "away_goals",
            "status",
        ]
    ].copy()
    for prefix, col in (("h", "home_team_id"), ("a", "away_team_id")):
        q = out[["kickoff_utc", col]].rename(columns={col: "team_id"}).reset_index()
        # allow_exact_matches=False: a match never sees its own result.
        j = pd.merge_asof(
            q.sort_values("kickoff_utc"),
            state,
            on="kickoff_utc",
            by="team_id",
            direction="backward",
            allow_exact_matches=False,
        )
        j = j.set_index("index").sort_index()
        last = (
            pd.merge_asof(
                q.sort_values("kickoff_utc"),
                long[["team_id", "kickoff_utc"]]
                .assign(prev=long["kickoff_utc"])
                .sort_values("kickoff_utc"),
                on="kickoff_utc",
                by="team_id",
                direction="backward",
                allow_exact_matches=False,
            )
            .set_index("index")
            .sort_index()
        )
        for c in ("xg_for", "xg_against", "goals_for", "goals_against", "form"):
            out[f"{prefix}_{c}"] = j[c].to_numpy()
        out[f"{prefix}_rest_days"] = (
            ((out["kickoff_utc"] - last["prev"]).dt.total_seconds() / 86400)
            .clip(upper=30)
            .to_numpy()
        )
    out["elo_home"] = elo_asof(elo, out["home_team_id"], out["kickoff_utc"])
    out["elo_away"] = elo_asof(elo, out["away_team_id"], out["kickoff_utc"])
    out["elo_diff"] = out["elo_home"] - out["elo_away"]
    out["xg_diff_form"] = (out["h_xg_for"] - out["h_xg_against"]) - (
        out["a_xg_for"] - out["a_xg_against"]
    )
    return out


def match_xg_from_shots(shots: pd.DataFrame, xg_col: str) -> pd.DataFrame:
    """Sum shot xG per match and side (own goals carry NaN xG and are skipped)."""
    s = shots.groupby(["match_id", "side"])[xg_col].sum().unstack(fill_value=0.0)
    s = s.reindex(columns=["h", "a"], fill_value=0.0)
    return s.rename(columns={"h": "home_xg", "a": "away_xg"}).reset_index()
