"""LightGBM multiclass model on pre-match features (classes: home win, draw, away win)."""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd

from pitchiq.config import GBMSettings
from pitchiq.evaluation.metrics import outcome_index
from pitchiq.features.match_features import FEATURES


def fit(train: pd.DataFrame, cfg: GBMSettings) -> lgb.LGBMClassifier:
    """Fit on finished matches with features."""
    t = train[train["status"] == "finished"].dropna(subset=["elo_diff"])
    y = outcome_index(t["home_goals"], t["away_goals"])
    model = lgb.LGBMClassifier(objective="multiclass", num_class=3, random_state=cfg.random_seed, verbose=-1, **cfg.params)
    model.fit(t[FEATURES], y)
    return model


def predict(model: lgb.LGBMClassifier, rows: pd.DataFrame) -> np.ndarray:
    """Probabilities [home, draw, away] per row."""
    return model.predict_proba(rows[FEATURES])
