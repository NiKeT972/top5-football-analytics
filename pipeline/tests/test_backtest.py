import numpy as np
import pandas as pd

from pitchiq.config import LeaguesConfig, load_leagues, load_settings
from pitchiq.evaluation.bookmaker import proportional, shin
from pitchiq.models.predictor import backtest
from pitchiq.models.predictor import dixon_coles as dc
from pitchiq.models.predictor.predict import append_ledger, predict_upcoming
from pitchiq.storage.parquet import Store

SEASONS = ["1415", "1516", "1617", "1718"]


def build_world(store, seed=3, n_teams=8):
    rng = np.random.default_rng(seed)
    teams = [f"eng-t{i}" for i in range(n_teams)]
    strength = rng.normal(0, 0.35, n_teams)
    rows, shots, odds = [], [], []
    mid, sid = 0, 0
    for s in SEASONS:
        day = pd.Timestamp(f"20{s[:2]}-08-10", tz="UTC")
        for _round in range(2):
            for i in range(n_teams):
                for j in range(n_teams):
                    if i == j:
                        continue
                    mid += 1
                    lam, mu = (
                        np.exp(0.25 + strength[i] - strength[j] * 0.5),
                        np.exp(strength[j] - strength[i] * 0.5),
                    )
                    g = dc.score_grid(lam, mu, -0.05, 10)
                    k = rng.choice(g.size, p=g.ravel())
                    hg, ag = k // 11, k % 11
                    rows.append(
                        {
                            "match_id": mid,
                            "league_id": "ENG1",
                            "season_id": s,
                            "kickoff_utc": day,
                            "home_team_id": teams[i],
                            "away_team_id": teams[j],
                            "home_goals": hg,
                            "away_goals": ag,
                            "status": "finished",
                        }
                    )
                    for side, x in (("h", lam), ("a", mu)):
                        sid += 1
                        shots.append(
                            {
                                "shot_id": sid,
                                "match_id": mid,
                                "side": side,
                                "result": "MissedShots",
                                "xg": x,
                                "xg_bt": x,
                            }
                        )
                    p = dc.outcome_probs(g) * 0.95
                    odds.append(
                        {
                            "match_id": mid,
                            "bookmaker": "pinnacle",
                            "kind": "closing",
                            "odds_h": 1 / p[0],
                            "odds_d": 1 / p[1],
                            "odds_a": 1 / p[2],
                        }
                    )
                    day += pd.Timedelta(hours=20)
    m = pd.DataFrame(rows)
    # two upcoming fixtures
    future = pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=2)
    up = pd.DataFrame(
        [
            {
                "match_id": 999001,
                "league_id": "ENG1",
                "season_id": SEASONS[-1],
                "kickoff_utc": future,
                "home_team_id": teams[0],
                "away_team_id": teams[1],
                "home_goals": pd.NA,
                "away_goals": pd.NA,
                "status": "scheduled",
            }
        ]
    )
    m = pd.concat([m, up], ignore_index=True)
    store.write("matches", m)
    sh = pd.DataFrame(shots)
    store.write("shots", sh.drop(columns=["xg", "xg_bt"]))
    store.write("shots_xg", sh[["shot_id", "xg", "xg_bt"]])
    store.write("odds", pd.DataFrame(odds))
    store.write(
        "elo",
        pd.DataFrame(
            {
                "team_id": teams,
                "valid_from": pd.Timestamp("2014-01-01").date(),
                "valid_to": pd.Timestamp("2030-01-01").date(),
                "elo": 1600 + 200 * strength,
            }
        ),
    )


def test_shin_removes_margin_and_favours_longshot_shading():
    odds = np.array([1.5, 4.0, 7.0])
    s, p = shin(odds), proportional(odds)
    assert s.sum() == np.float64(1.0) or abs(s.sum() - 1) < 1e-9
    assert s[0] > p[0] and s[2] < p[2]


def test_walk_forward_backtest_and_live_predictions(tmp_path):
    settings = load_settings().model_copy(deep=True)
    settings.seasons.backtest = ["1617", "1718"]
    settings.seasons.current = "1718"
    settings.predictor.dixon_coles.refit_every_days = 30
    settings.predictor.gbm.params["n_estimators"] = 50
    leagues = LeaguesConfig(leagues=[load_leagues().get("ENG1")])
    store = Store(tmp_path / "data")
    build_world(store)
    out = backtest.run(store, settings, leagues, tmp_path / "reports")
    summary = {r["model"]: r for r in out["summary"]}
    assert set(summary) == {"dixon_coles", "gbm", "ensemble", "bookmaker"}
    # the "bookmaker" knows the true probabilities, so it must be hard to beat
    assert summary["bookmaker"]["rps"] <= summary["dixon_coles"]["rps"] + 0.01
    assert summary["dixon_coles"]["log_loss"] < np.log(3)
    assert (tmp_path / "reports" / "predictor_report.md").exists()

    preds = predict_upcoming(store, settings, leagues, pd.Timestamp.now(tz="UTC"))
    assert set(preds["model"]) == {"dixon_coles", "gbm", "ensemble"}
    ens = preds[preds["model"] == "ensemble"].iloc[0]
    assert abs(ens["p_home"] + ens["p_draw"] + ens["p_away"] - 1) < 1e-3
    assert append_ledger(preds, tmp_path / "ledger") == 3
    assert append_ledger(preds, tmp_path / "ledger") == 3  # appends, never rewrites
    assert len(next((tmp_path / "ledger").glob("*.csv")).read_text().strip().splitlines()) == 7
