import numpy as np
import pandas as pd
import pytest
from scipy.optimize import approx_fprime

from pitchiq.config import load_settings
from pitchiq.models.predictor import dixon_coles as dc


def simulate_league(n_teams=10, n_rounds=4, seed=1, home=0.3, rho=-0.08):
    rng = np.random.default_rng(seed)
    teams = [f"t{i}" for i in range(n_teams)]
    att = rng.normal(0, 0.3, n_teams)
    att -= att.mean()
    dfn = rng.normal(0, 0.3, n_teams)
    rows = []
    day = pd.Timestamp("2024-08-01", tz="UTC")
    for r in range(n_rounds):
        for i in range(n_teams):
            for j in range(n_teams):
                if i == j:
                    continue
                lam, mu = np.exp(home + att[i] + dfn[j]), np.exp(att[j] + dfn[i])
                g = dc.score_grid(lam, mu, rho, 10).ravel()
                k = rng.choice(len(g), p=g)
                rows.append({"kickoff_utc": day, "home_team_id": teams[i], "away_team_id": teams[j],
                             "home_goals": k // 11, "away_goals": k % 11})
                day += pd.Timedelta(hours=7)
    return pd.DataFrame(rows), teams, att, dfn


def test_gradient_is_correct():
    rng = np.random.default_rng(0)
    n, m = 5, 60
    hi, ai = rng.integers(0, n, m), rng.integers(0, n, m)
    x, y = rng.integers(0, 3, m), rng.integers(0, 3, m)
    w = rng.uniform(0.5, 1, m)
    p = np.concatenate([rng.normal(0, 0.2, 2 * n), [0.2, -0.1]])
    args = (hi, ai, x, y, w, np.zeros(n), np.zeros(n), 0.05)
    f = lambda q: dc._nll_and_grad(q, *args)[0]  # noqa: E731
    num = approx_fprime(p, f, 1e-6)
    ana = dc._nll_and_grad(p, *args)[1]
    assert np.allclose(num, ana, rtol=1e-4, atol=1e-4)


def test_fit_recovers_home_advantage_and_ranks_teams():
    cfg = load_settings().predictor.dixon_coles.model_copy(update={"time_decay_xi_per_day": 0.0, "ridge": 0.01})
    df, teams, att, _ = simulate_league(n_rounds=6)
    f = dc.fit(df, df["kickoff_utc"].max() + pd.Timedelta(days=1), cfg)
    assert f.home == pytest.approx(0.3, abs=0.1)
    est = np.array([f.strengths(t)[0] for t in teams])
    assert np.corrcoef(est, att)[0, 1] > 0.8


def test_grid_and_outcomes_sum_to_one():
    g = dc.score_grid(1.6, 1.1, -0.1, 10)
    assert g.sum() == pytest.approx(1.0)
    probs = dc.outcome_probs(g)
    assert probs.sum() == pytest.approx(1.0) and probs[0] > probs[2]


def test_unseen_team_uses_prior():
    cfg = load_settings().predictor.dixon_coles
    df, _, _, _ = simulate_league(n_rounds=1)
    f = dc.fit(df, df["kickoff_utc"].max() + pd.Timedelta(days=1), cfg, priors={"new": (-0.3, 0.3)})
    assert f.strengths("new") == (-0.3, 0.3)
