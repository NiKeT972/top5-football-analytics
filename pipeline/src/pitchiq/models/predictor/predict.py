"""Predictions for upcoming fixtures, plus the append-only prediction ledger.

Every daily run predicts the fixtures in the next ``horizon_days`` and appends the
predictions to ``ledger/predictions/YYYY-MM.csv`` (committed to git). A prediction is only
ever written for a match that has not kicked off, so the git history is a timestamped,
tamper-evident record of the live track record.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from pitchiq.config import REPO_DIR, LeaguesConfig, Settings
from pitchiq.features.match_features import build_match_features, match_xg_from_shots
from pitchiq.models.predictor import dixon_coles as dc
from pitchiq.models.predictor import gbm
from pitchiq.models.predictor.backtest import season_priors
from pitchiq.storage.parquet import Store

log = logging.getLogger(__name__)
LEDGER_DIR = REPO_DIR / "ledger" / "predictions"
LEDGER_COLUMNS = [
    "created_utc",
    "match_id",
    "league_id",
    "kickoff_utc",
    "home_team_id",
    "away_team_id",
    "model",
    "p_home",
    "p_draw",
    "p_away",
    "exp_home_goals",
    "exp_away_goals",
    "top_score",
]


def top_score(grid: np.ndarray) -> str:
    """Most likely scoreline, e.g. ``1-0``."""
    i, j = np.unravel_index(np.argmax(grid), grid.shape)
    return f"{i}-{j}"


def predict_upcoming(
    store: Store, settings: Settings, leagues: LeaguesConfig, now: pd.Timestamp
) -> pd.DataFrame:
    """Predict fixtures kicking off between ``now`` and ``now + horizon``."""
    cfg = settings.predictor
    meta = store.read_json("predictor/meta.json", {"ensemble_weight": 0.5, "promoted_priors": {}})
    w = float(meta["ensemble_weight"])
    matches = store.read("matches")
    matches["kickoff_utc"] = pd.to_datetime(matches["kickoff_utc"], utc=True)
    upcoming = matches[
        (matches["status"] == "scheduled")
        & (matches["kickoff_utc"] > now)
        & (matches["kickoff_utc"] <= now + pd.Timedelta(days=cfg.horizon_days))
    ]
    if upcoming.empty:
        return pd.DataFrame()

    shots = store.read("shots").merge(store.read("shots_xg"), on="shot_id")
    feats = build_match_features(
        matches, match_xg_from_shots(shots, "xg"), store.read("elo"), cfg.gbm
    )
    model = gbm.fit(feats[feats["status"] == "finished"], cfg.gbm)
    up_feats = feats[feats["match_id"].isin(upcoming["match_id"])].set_index("match_id")
    gbm_p = pd.DataFrame(
        gbm.predict(model, up_feats), index=up_feats.index, columns=["h", "d", "a"]
    )

    rows = []
    created = pd.Timestamp.now(tz="UTC").floor("s")
    for lg in leagues.leagues:
        lm = matches[matches["league_id"] == lg.league_id]
        lu = upcoming[upcoming["league_id"] == lg.league_id]
        if lu.empty:
            continue
        prior = tuple(meta["promoted_priors"].get(lg.league_id, (0.0, 0.0)))
        teams, priors = season_priors(lm, settings.seasons.current, prior)
        fit = dc.fit(lm, now, cfg.dixon_coles, priors=priors, teams=teams)
        for r in lu.itertuples():
            lam, mu = fit.rates(r.home_team_id, r.away_team_id)
            grid = dc.score_grid(lam, mu, fit.rho, cfg.dixon_coles.max_goals)
            p_dc = dc.outcome_probs(grid)
            p_gbm = gbm_p.loc[r.match_id].to_numpy() if r.match_id in gbm_p.index else p_dc
            p_ens = w * p_dc + (1 - w) * p_gbm
            base = {
                "created_utc": created,
                "match_id": r.match_id,
                "league_id": r.league_id,
                "kickoff_utc": r.kickoff_utc,
                "home_team_id": r.home_team_id,
                "away_team_id": r.away_team_id,
                "exp_home_goals": round(lam, 4),
                "exp_away_goals": round(mu, 4),
                "top_score": top_score(grid),
            }
            for name, p in (("dixon_coles", p_dc), ("gbm", p_gbm), ("ensemble", p_ens)):
                rows.append(
                    {
                        **base,
                        "model": name,
                        "p_home": round(float(p[0]), 5),
                        "p_draw": round(float(p[1]), 5),
                        "p_away": round(float(p[2]), 5),
                        "score_grid": json.dumps(np.round(grid, 5).tolist())
                        if name == "ensemble"
                        else None,
                    }
                )
    preds = pd.DataFrame(rows)
    store.upsert("predictions", preds, ["match_id", "model", "created_utc"])
    return preds


def append_ledger(preds: pd.DataFrame, ledger_dir: Path = LEDGER_DIR) -> int:
    """Append pre-kickoff predictions to the monthly ledger CSV; returns rows written."""
    if preds.empty:
        return 0
    ok = preds[
        pd.to_datetime(preds["kickoff_utc"], utc=True)
        > pd.to_datetime(preds["created_utc"], utc=True)
    ]
    ledger_dir.mkdir(parents=True, exist_ok=True)
    month = pd.Timestamp(ok["created_utc"].iloc[0]).strftime("%Y-%m")
    path = ledger_dir / f"{month}.csv"
    ok[LEDGER_COLUMNS].to_csv(path, mode="a", header=not path.exists(), index=False)
    return len(ok)
