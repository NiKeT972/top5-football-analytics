import numpy as np
import pandas as pd
import pytest

from pitchiq.config import load_settings
from pitchiq.models.xg.features import game_state, geometry
from pitchiq.storage.parquet import Store


@pytest.fixture(scope="module")
def xg_cfg():
    return load_settings().xg


def test_penalty_spot_geometry(xg_cfg):
    x = pd.Series([1 - 11 / xg_cfg.pitch_length_m])
    y = pd.Series([0.5])
    g = geometry(x, y, xg_cfg)
    assert g.loc[0, "distance_m"] == pytest.approx(11.0)
    assert g.loc[0, "angle_rad"] == pytest.approx(2 * np.arctan(xg_cfg.goal_width_m / 2 / 11))


def test_angle_is_positive_on_goal_line_inside_posts(xg_cfg):
    g = geometry(pd.Series([0.999]), pd.Series([0.5]), xg_cfg)
    assert np.pi * 0.9 < g.loc[0, "angle_rad"] < np.pi


def test_game_state_excludes_current_shot():
    shots = pd.DataFrame(
        {
            "match_id": [1, 1, 1, 1],
            "shot_id": [1, 2, 3, 4],
            "minute": [10, 20, 30, 40],
            "side": ["h", "h", "a", "a"],
            "result": ["Goal", "MissedShots", "OwnGoal", "Goal"],
        }
    )
    # shot1: 0-0 -> 0 ; shot2: home leads 1-0 -> +1 ; own goal listed under 'a' (benefits away)
    # shot3: away trails 0-1 -> -1 ; shot4: 1-1 -> 0
    assert game_state(shots).tolist() == [0, 1, -1, 0]


def synthetic_shots(n_per_season=6000, seasons=("1415", "1516", "1617"), seed=0):
    rng = np.random.default_rng(seed)
    rows, mrows = [], []
    sid = 0
    for k, season in enumerate(seasons):
        n_matches = n_per_season // 20
        for m in range(n_matches):
            mid = k * 10_000 + m
            mrows.append({"match_id": mid, "season_id": season, "league_id": "ENG1"})
            for _ in range(20):
                sid += 1
                x = rng.uniform(0.65, 0.99)
                y = rng.uniform(0.25, 0.75)
                pen = rng.random() < 0.02
                if pen:
                    x, y = 1 - 11 / 105, 0.5
                dist = np.hypot((1 - x) * 105, (y - 0.5) * 68)
                head = rng.random() < 0.15
                p = 0.76 if pen else 1 / (1 + np.exp(-(1.2 - 0.17 * dist - 0.8 * head)))
                rows.append(
                    {
                        "shot_id": sid, "match_id": mid, "side": "h" if rng.random() < 0.5 else "a",
                        "minute": int(rng.integers(1, 90)), "x": x, "y": y,
                        "xg_us": float(np.clip(p + rng.normal(0, 0.02), 0.001, 0.99)),
                        "result": "Goal" if rng.random() < p else "MissedShots",
                        "situation": "Penalty" if pen else "OpenPlay",
                        "shot_type": "Head" if head else "RightFoot",
                        "last_action": rng.choice(["Pass", "Cross", "Rebound"]),
                    }
                )
    return pd.DataFrame(rows), pd.DataFrame(mrows)


def test_train_evaluate_and_score(tmp_path):
    from pitchiq.models.xg.train import evaluate, score_all

    settings = load_settings().model_copy(deep=True)
    settings.xg.holdout_seasons = ["1617"]
    settings.xg.backtest_train_last_season = "1415"
    settings.xg.lgbm["n_estimators"] = 200
    store = Store(tmp_path / "data")
    shots, matches = synthetic_shots()
    store.write("shots", shots)
    store.write("matches", matches)
    summary = evaluate(settings, store, tmp_path / "reports")
    lgbm = summary["results"]["LightGBM"]["non_penalty"]
    assert lgbm["auc"] > 0.7
    # the generating process is logistic in distance: models should be close to the truth proxy
    assert abs(lgbm["log_loss"] - summary["results"]["Understat xG"]["non_penalty"]["log_loss"]) < 0.02
    assert summary["penalty_xg"] == pytest.approx(0.76, abs=0.1)
    assert (tmp_path / "reports" / "xg_report.md").exists()
    scored = score_all(store)
    assert scored["xg"].between(0, 1).all() and len(scored) == len(shots)
