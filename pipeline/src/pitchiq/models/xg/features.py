"""Shot features for the xG model.

Understat coordinates are fractions of the pitch: ``X`` runs along its length towards the
attacked goal at ``X = 1`` and ``Y`` across its width with the goal centred at ``Y = 0.5``.
We convert to metres on a ``pitch_length_m x pitch_width_m`` pitch.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pitchiq.config import XGSettings

NUMERIC = ["distance_m", "angle_rad", "log_distance", "distance_x_angle", "game_state", "minute"]
CATEGORICAL = ["situation", "body_part", "last_action"]
GAME_STATE_CLIP = 3
PENALTY = "Penalty"
OWN_GOAL = "OwnGoal"
GOAL = "Goal"
NON_PENALTY_SITUATIONS = ["DirectFreekick", "FromCorner", "OpenPlay", "SetPiece"]
BODY_PARTS = ["Foot", "Head", "Other"]


def geometry(x: pd.Series, y: pd.Series, cfg: XGSettings) -> pd.DataFrame:
    """Distance to goal centre (m) and the angle subtended by the goal mouth (radians)."""
    dx = (1.0 - x.astype(float)) * cfg.pitch_length_m
    dy = (y.astype(float) - 0.5) * cfg.pitch_width_m
    dist = np.hypot(dx, dy)
    half = cfg.goal_width_m / 2.0
    # Angle between the lines to the two posts: atan2 keeps it in (0, pi) everywhere.
    angle = np.arctan2(cfg.goal_width_m * dx, dx**2 + dy**2 - half**2)
    angle = np.where(angle < 0, angle + np.pi, angle)
    return pd.DataFrame({"distance_m": dist, "angle_rad": angle}, index=x.index)


def body_part(shot_type: pd.Series) -> pd.Series:
    """Collapse left/right foot into ``Foot``."""
    return shot_type.map({"RightFoot": "Foot", "LeftFoot": "Foot", "Head": "Head"}).fillna("Other")


def game_state(shots: pd.DataFrame) -> pd.Series:
    """Goal difference (shooting team minus opponent) just before each shot, clipped to +-3.

    Goals are counted from ``Goal`` rows of each side plus ``OwnGoal`` rows, which Understat
    lists under the side that benefits (verified against final scores in validation).
    """
    s = shots.sort_values(["match_id", "minute", "shot_id"])
    is_goal = s["result"].isin([GOAL, OWN_GOAL]).astype(int)
    home_goal = is_goal * (s["side"] == "h")
    away_goal = is_goal * (s["side"] == "a")
    g = s.assign(hg=home_goal, ag=away_goal).groupby("match_id")
    # Goals *before* this shot: cumulative sum minus the shot itself.
    h_before = g["hg"].cumsum() - home_goal
    a_before = g["ag"].cumsum() - away_goal
    diff = np.where(s["side"] == "h", h_before - a_before, a_before - h_before)
    return pd.Series(np.clip(diff, -GAME_STATE_CLIP, GAME_STATE_CLIP), index=s.index).reindex(
        shots.index
    )


def frequent_categories(values: pd.Series, min_count: int) -> list[str]:
    """Categories seen at least ``min_count`` times (others become ``Other``)."""
    counts = values.value_counts()
    return sorted(counts[counts >= min_count].index.tolist())


def build_features(shots: pd.DataFrame, cfg: XGSettings, last_actions: list[str]) -> pd.DataFrame:
    """Model matrix for non-penalty shots.

    Args:
        shots: Shots with ``x, y, minute, situation, shot_type, last_action, result, side, match_id, shot_id``.
        cfg: xG settings.
        last_actions: Allowed ``last_action`` categories (from training data).

    """
    geo = geometry(shots["x"], shots["y"], cfg)
    feats = pd.DataFrame(index=shots.index)
    feats["distance_m"] = geo["distance_m"]
    feats["angle_rad"] = geo["angle_rad"]
    feats["log_distance"] = np.log1p(geo["distance_m"])
    feats["distance_x_angle"] = geo["distance_m"] * geo["angle_rad"]
    feats["game_state"] = game_state(shots).astype(float)
    feats["minute"] = shots["minute"].astype(float)
    feats["situation"] = shots["situation"].astype(str)
    feats["body_part"] = body_part(shots["shot_type"])
    la = shots["last_action"].fillna("None").astype(str)
    feats["last_action"] = la.where(la.isin(last_actions), "Other")
    # Fixed category sets keep train and inference encodings identical.
    cats = {
        "situation": NON_PENALTY_SITUATIONS,
        "body_part": BODY_PARTS,
        "last_action": sorted({*last_actions, "Other"}),
    }
    for c, values in cats.items():
        feats[c] = pd.Categorical(feats[c], categories=values)
    return feats
