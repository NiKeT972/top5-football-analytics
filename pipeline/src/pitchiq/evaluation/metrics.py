"""Probabilistic scoring rules and calibration tables.

Match outcome arrays are ordered ``[home, draw, away]``; RPS uses that order, which is the
natural ordinal order of the result.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

EPS = 1e-12


def binary_log_loss(y: np.ndarray, p: np.ndarray) -> float:
    """Mean negative log-likelihood of binary outcomes."""
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def binary_brier(y: np.ndarray, p: np.ndarray) -> float:
    """Mean squared error of binary probabilities."""
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


def auc(y: np.ndarray, p: np.ndarray) -> float:
    """ROC-AUC."""
    return float(roc_auc_score(y, p))


def one_hot(outcome: np.ndarray, k: int = 3) -> np.ndarray:
    """Outcome indices -> one-hot matrix."""
    out = np.zeros((len(outcome), k))
    out[np.arange(len(outcome)), np.asarray(outcome, int)] = 1.0
    return out


def multi_log_loss(outcome: np.ndarray, probs: np.ndarray) -> float:
    """Mean negative log probability of the observed outcome."""
    p = np.clip(np.asarray(probs, float)[np.arange(len(outcome)), np.asarray(outcome, int)], EPS, 1)
    return float(-np.mean(np.log(p)))


def multi_brier(outcome: np.ndarray, probs: np.ndarray) -> float:
    """Multi-class Brier score (sum over classes, mean over matches; 0 is perfect, 2 worst)."""
    return float(np.mean(np.sum((np.asarray(probs, float) - one_hot(outcome, probs.shape[1])) ** 2, axis=1)))


def rps(outcome: np.ndarray, probs: np.ndarray) -> float:
    """Ranked probability score for ordered outcomes (mean over matches)."""
    probs = np.asarray(probs, float)
    k = probs.shape[1]
    cum_p = np.cumsum(probs, axis=1)[:, :-1]
    cum_o = np.cumsum(one_hot(outcome, k), axis=1)[:, :-1]
    return float(np.mean(np.sum((cum_p - cum_o) ** 2, axis=1) / (k - 1)))


def calibration_table(y: np.ndarray, p: np.ndarray, n_bins: int) -> pd.DataFrame:
    """Equal-width calibration bins: mean predicted vs observed frequency."""
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    bins = np.clip((p * n_bins).astype(int), 0, n_bins - 1)
    df = pd.DataFrame({"bin": bins, "p": p, "y": y})
    g = df.groupby("bin").agg(mean_pred=("p", "mean"), obs_freq=("y", "mean"), n=("y", "size")).reset_index()
    return g


def outcome_index(home_goals: pd.Series, away_goals: pd.Series) -> np.ndarray:
    """0 = home win, 1 = draw, 2 = away win."""
    h, a = np.asarray(home_goals, int), np.asarray(away_goals, int)
    return np.where(h > a, 0, np.where(h == a, 1, 2))
