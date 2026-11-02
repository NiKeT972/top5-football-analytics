"""Dixon-Coles (1997) match model with exponential time decay.

Goals are Poisson with

    log(lambda_home) = home + attack[home] + defence[away]
    log(mu_away)     =        attack[away] + defence[home]

(``defence`` is defensive *weakness*: higher concedes more), multiplied by the Dixon-Coles
low-score correction ``tau(x, y)`` with parameter ``rho``. Each past match is weighted by
``exp(-xi * days_ago)``. A small ridge penalty pulls each team's attack/defence towards a
prior mean: 0 for established teams, the historical average of promoted teams for teams
that were not in the league the previous season. This makes the fit identifiable and gives
promoted teams sensible early-season ratings.

The negative log-likelihood has an analytic gradient, so a fit takes well under a second.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

from pitchiq.config import DixonColesSettings

RHO_BOUNDS = (-0.25, 0.25)
HOME_BOUNDS = (-1.0, 1.0)
STRENGTH_BOUNDS = (-3.0, 3.0)
EPS = 1e-10
SECONDS_PER_DAY = 86400.0


@dataclass
class DCFit:
    """Fitted parameters for one league as of a date."""

    teams: list[str]
    attack: np.ndarray
    defence: np.ndarray
    home: float
    rho: float
    as_of: pd.Timestamp
    priors: dict[str, tuple[float, float]]

    def strengths(self, team: str) -> tuple[float, float]:
        """(attack, defence) of a team; unseen teams get their prior."""
        if team in self.teams:
            i = self.teams.index(team)
            return float(self.attack[i]), float(self.defence[i])
        return self.priors.get(team, (0.0, 0.0))

    def rates(self, home_team: str, away_team: str) -> tuple[float, float]:
        """Expected goals (lambda, mu) for a fixture."""
        ah, dh = self.strengths(home_team)
        aa, da = self.strengths(away_team)
        return float(np.exp(self.home + ah + da)), float(np.exp(aa + dh))

    def score_grid(self, home_team: str, away_team: str, max_goals: int) -> np.ndarray:
        """P(home goals = i, away goals = j) for i, j in 0..max_goals (normalised)."""
        lam, mu = self.rates(home_team, away_team)
        return score_grid(lam, mu, self.rho, max_goals)


def tau_matrix(lam: float, mu: float, rho: float, max_goals: int) -> np.ndarray:
    """Dixon-Coles correction factors for the low-score cells."""
    t = np.ones((max_goals + 1, max_goals + 1))
    t[0, 0] = 1 - lam * mu * rho
    t[0, 1] = 1 + lam * rho
    t[1, 0] = 1 + mu * rho
    t[1, 1] = 1 - rho
    return np.clip(t, EPS, None)


def score_grid(lam: float, mu: float, rho: float, max_goals: int) -> np.ndarray:
    """Normalised score probability grid."""
    g = np.outer(poisson.pmf(np.arange(max_goals + 1), lam), poisson.pmf(np.arange(max_goals + 1), mu))
    g = g * tau_matrix(lam, mu, rho, max_goals)
    return g / g.sum()


def outcome_probs(grid: np.ndarray) -> np.ndarray:
    """[P(home win), P(draw), P(away win)] from a score grid (rows = home goals)."""
    return np.array([np.tril(grid, -1).sum(), np.trace(grid), np.triu(grid, 1).sum()])


def _nll_and_grad(
    params: np.ndarray,
    hi: np.ndarray,
    ai: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    w: np.ndarray,
    prior_att: np.ndarray,
    prior_def: np.ndarray,
    ridge: float,
) -> tuple[float, np.ndarray]:
    n = len(prior_att)
    att, dfn, home, rho = params[:n], params[n : 2 * n], params[2 * n], params[2 * n + 1]
    log_lam = home + att[hi] + dfn[ai]
    log_mu = att[ai] + dfn[hi]
    lam, mu = np.exp(log_lam), np.exp(log_mu)

    # tau and its partial derivatives for the four low-score cells
    tau = np.ones_like(lam)
    dt_dlam = np.zeros_like(lam)
    dt_dmu = np.zeros_like(lam)
    dt_drho = np.zeros_like(lam)
    c00 = (x == 0) & (y == 0)
    c01 = (x == 0) & (y == 1)
    c10 = (x == 1) & (y == 0)
    c11 = (x == 1) & (y == 1)
    tau[c00] = 1 - lam[c00] * mu[c00] * rho
    dt_dlam[c00], dt_dmu[c00], dt_drho[c00] = -mu[c00] * rho, -lam[c00] * rho, -lam[c00] * mu[c00]
    tau[c01] = 1 + lam[c01] * rho
    dt_dlam[c01], dt_drho[c01] = rho, lam[c01]
    tau[c10] = 1 + mu[c10] * rho
    dt_dmu[c10], dt_drho[c10] = rho, mu[c10]
    tau[c11] = 1 - rho
    dt_drho[c11] = -1.0
    tau = np.clip(tau, EPS, None)

    ll = w * (x * log_lam - lam + y * log_mu - mu + np.log(tau))
    pen_a, pen_d = att - prior_att, dfn - prior_def
    nll = -ll.sum() + ridge * (pen_a @ pen_a + pen_d @ pen_d)

    # d ll / d log_lam = w * (x - lam + lam * dtau/dlam / tau), same for mu
    g_lam = w * (x - lam + lam * dt_dlam / tau)
    g_mu = w * (y - mu + mu * dt_dmu / tau)
    g_att = np.bincount(hi, g_lam, n) + np.bincount(ai, g_mu, n)
    g_def = np.bincount(ai, g_lam, n) + np.bincount(hi, g_mu, n)
    grad = np.concatenate(
        [
            -g_att + 2 * ridge * pen_a,
            -g_def + 2 * ridge * pen_d,
            [-g_lam.sum()],
            [-(w * dt_drho / tau).sum()],
        ]
    )
    return float(nll), grad


def fit(
    matches: pd.DataFrame,
    as_of: pd.Timestamp,
    cfg: DixonColesSettings,
    priors: dict[str, tuple[float, float]] | None = None,
    teams: list[str] | None = None,
) -> DCFit:
    """Fit on finished matches strictly before ``as_of``.

    Args:
        matches: Columns ``kickoff_utc, home_team_id, away_team_id, home_goals, away_goals``.
        as_of: Only matches before this instant are used; decay is measured from it.
        cfg: Model settings.
        priors: ``{team_id: (attack, defence)}`` prior means (default 0).
        teams: Teams to include even without history in the window (e.g. promoted sides).
    """
    priors = priors or {}
    hist = matches[(matches["kickoff_utc"] < as_of) & matches["home_goals"].notna()]
    age_days = (as_of - hist["kickoff_utc"]).dt.total_seconds().to_numpy() / SECONDS_PER_DAY
    keep = age_days <= cfg.history_days
    hist, age_days = hist[keep], age_days[keep]
    names = sorted(set(hist["home_team_id"]) | set(hist["away_team_id"]) | set(teams or []))
    idx = {t: i for i, t in enumerate(names)}
    n = len(names)
    prior_att = np.array([priors.get(t, (0.0, 0.0))[0] for t in names])
    prior_def = np.array([priors.get(t, (0.0, 0.0))[1] for t in names])
    hi = hist["home_team_id"].map(idx).to_numpy()
    ai = hist["away_team_id"].map(idx).to_numpy()
    x = hist["home_goals"].astype(int).to_numpy()
    y = hist["away_goals"].astype(int).to_numpy()
    w = np.exp(-cfg.time_decay_xi_per_day * age_days)
    x0 = np.concatenate([prior_att, prior_def, [0.25, -0.05]])
    bounds = [STRENGTH_BOUNDS] * (2 * n) + [HOME_BOUNDS, RHO_BOUNDS]
    res = minimize(
        _nll_and_grad,
        x0,
        args=(hi, ai, x, y, w, prior_att, prior_def, cfg.ridge),
        jac=True,
        method="L-BFGS-B",
        bounds=bounds,
    )
    p = res.x
    return DCFit(names, p[:n], p[n : 2 * n], float(p[2 * n]), float(p[2 * n + 1]), as_of, priors)


def promoted_prior(matches: pd.DataFrame, cfg: DixonColesSettings) -> tuple[float, float]:
    """Average end-of-season (attack, defence) of newly promoted teams, from history.

    For every league-season with a previous season available, fit that season alone and
    average the parameters of teams absent from the previous season.
    """
    atts, defs = [], []
    seasons = sorted(matches["season_id"].unique())
    flat = cfg.model_copy(update={"time_decay_xi_per_day": 0.0, "history_days": 400})
    for prev, cur in zip(seasons[:-1], seasons[1:], strict=True):
        cur_m = matches[(matches["season_id"] == cur) & matches["home_goals"].notna()]
        if cur_m.empty:
            continue
        prev_teams = set(matches.loc[matches["season_id"] == prev, "home_team_id"])
        new = set(cur_m["home_team_id"]) - prev_teams
        f = fit(cur_m, cur_m["kickoff_utc"].max() + pd.Timedelta(days=1), flat)
        for t in new:
            a, d = f.strengths(t)
            atts.append(a)
            defs.append(d)
    if not atts:
        return 0.0, 0.0
    return float(np.mean(atts)), float(np.mean(defs))
