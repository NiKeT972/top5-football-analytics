import numpy as np
import pandas as pd
import pytest

from pitchiq.config import load_settings
from pitchiq.models.xpts import exact_outcome_probs, match_xpts, season_table, simulate_match


def test_simulation_matches_exact():
    h = np.array([0.4, 0.1, 0.05, 0.76])
    a = np.array([0.2, 0.3])
    exact = exact_outcome_probs(h, a)
    sim = simulate_match(h, a, 200_000, np.random.default_rng(0))
    assert sum(exact) == pytest.approx(1.0)
    assert np.allclose(sim, exact, atol=0.005)


def test_no_shots_is_a_certain_draw():
    assert exact_outcome_probs(np.array([]), np.array([])) == (0.0, 1.0, 0.0)


def test_match_xpts_and_table():
    cfg = load_settings().xpts
    shots = pd.DataFrame(
        {"match_id": [1, 1, 1], "side": ["h", "h", "a"], "team_id": ["a", "a", "b"], "xg": [0.9, 0.9, 0.05]}
    )
    xp = match_xpts(shots, cfg)
    home = xp[xp["side"] == "h"].iloc[0]
    assert home["xpts"] > 2.4 and home["p_win"] + home["p_draw"] + home["p_loss"] == pytest.approx(1)
    matches = pd.DataFrame(
        {"match_id": [1], "league_id": ["ENG1"], "season_id": ["2526"], "home_team_id": ["a"],
         "away_team_id": ["b"], "home_goals": [0], "away_goals": [1], "status": ["finished"]}
    )
    t = season_table(matches, xp).set_index("team_id")
    assert t.loc["b", "pts"] == 3 and t.loc["b", "pts_minus_xpts"] > 2.5
    assert t.loc["a", "position"] == 2 and t.loc["a", "xpts_position"] == 1
