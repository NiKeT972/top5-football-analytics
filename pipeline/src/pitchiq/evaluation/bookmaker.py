"""Convert bookmaker odds to probabilities with the margin (overround) removed.

* Proportional: divide implied probabilities by their sum.
* Shin (1993): models the margin as protection against insiders; it shifts more of the
  margin onto longshots, which matches the favourite-longshot bias. Primary method.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import brentq

SHIN_Z_MAX = 0.5


def proportional(odds: np.ndarray) -> np.ndarray:
    """Normalised implied probabilities."""
    inv = 1.0 / np.asarray(odds, float)
    return inv / inv.sum()


def shin(odds: np.ndarray) -> np.ndarray:
    """Shin probabilities for one market (falls back to proportional if no root)."""
    pi = 1.0 / np.asarray(odds, float)
    book = pi.sum()
    if book <= 1.0:
        return pi / book

    def probs(z: float) -> np.ndarray:
        return (np.sqrt(z**2 + 4 * (1 - z) * pi**2 / book) - z) / (2 * (1 - z))

    try:
        z = brentq(lambda z: probs(z).sum() - 1.0, 0.0, SHIN_Z_MAX)
    except ValueError:
        return pi / book
    p = probs(z)
    return p / p.sum()


def implied_probs(odds: pd.DataFrame, method: str = "shin") -> pd.DataFrame:
    """Add ``p_h, p_d, p_a, overround`` to a frame with ``odds_h, odds_d, odds_a``."""
    fn = shin if method == "shin" else proportional
    arr = odds[["odds_h", "odds_d", "odds_a"]].to_numpy(float)
    probs = np.vstack([fn(row) for row in arr]) if len(arr) else np.empty((0, 3))
    out = odds.copy()
    out[["p_h", "p_d", "p_a"]] = probs
    out["overround"] = (1.0 / arr).sum(axis=1) - 1.0 if len(arr) else []
    return out


def best_closing(odds: pd.DataFrame) -> pd.DataFrame:
    """One closing line per match: Pinnacle if available, else market average."""
    c = odds[odds["kind"] == "closing"].copy()
    c["rank"] = c["bookmaker"].map({"pinnacle": 0, "market_avg": 1})
    return c.sort_values("rank").drop_duplicates("match_id").drop(columns="rank")


def best_pre(odds: pd.DataFrame) -> pd.DataFrame:
    """One pre-match line per match (market average preferred: it is the consensus price)."""
    c = odds[odds["kind"] == "pre"].copy()
    c["rank"] = c["bookmaker"].map({"market_avg": 0, "pinnacle": 1})
    return c.sort_values("rank").drop_duplicates("match_id").drop(columns="rank")
