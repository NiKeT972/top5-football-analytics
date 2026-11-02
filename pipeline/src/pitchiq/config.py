"""Load and validate the YAML configuration in ``pipeline/config``.

All tunable numbers live in config files; code reads them through these typed models
so a typo or missing value fails loudly at start-up instead of mid-run.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

PIPELINE_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = PIPELINE_DIR.parent
CONFIG_DIR = PIPELINE_DIR / "config"
SEASON_PATTERN = r"^\d{4}$"


class LeagueSources(BaseModel):
    """Identifiers for one league in each data source."""

    soccerdata: str
    football_data: str
    understat: str
    clubelo_country: str
    fbref_comp_id: int


class League(BaseModel):
    """A canonical league definition."""

    league_id: str = Field(pattern=r"^[A-Z]{3}\d$")
    name: str
    country: str
    n_teams: int = Field(gt=1)
    n_teams_history: dict[str, int] = Field(default_factory=dict)
    sources: LeagueSources

    def teams_in_season(self, season_id: str) -> int:
        """Return the number of teams in this league for a given season."""
        return self.n_teams_history.get(season_id, self.n_teams)


class LeaguesConfig(BaseModel):
    """The full ``leagues.yaml`` file."""

    leagues: list[League]

    @field_validator("leagues")
    @classmethod
    def _unique_ids(cls, leagues: list[League]) -> list[League]:
        ids = [lg.league_id for lg in leagues]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate league_id in {ids}")
        return leagues

    def get(self, league_id: str) -> League:
        """Return one league by id."""
        for lg in self.leagues:
            if lg.league_id == league_id:
                return lg
        raise KeyError(league_id)


class SeasonsConfig(BaseModel):
    """Season range and windows."""

    first: str = Field(pattern=SEASON_PATTERN)
    current: str = Field(pattern=SEASON_PATTERN)
    db_window: int = Field(ge=1)
    backtest: list[str]
    shots_first: str = Field(pattern=SEASON_PATTERN)


class ScrapingSettings(BaseModel):
    """Politeness and retry settings for every source."""

    rate_limits_per_min: dict[str, float]
    max_retries: int = Field(ge=0)
    backoff_seconds: float = Field(gt=0)
    timeout_s: float = Field(gt=0)
    user_agent: str
    current_season_max_age_hours: float = Field(gt=0)
    fixtures_max_age_hours: float = Field(gt=0)
    fbref_refresh_days: int = Field(ge=1)
    fbref_enabled: bool
    max_match_requests_per_run: int = Field(ge=1)


class ValidationSettings(BaseModel):
    """Thresholds for data-quality checks."""

    max_goals_per_team: int
    max_xg_per_shot: float
    max_shots_per_team: int
    fixture_date_tolerance_days: int
    min_team_match_score: float
    max_score_mismatches: int


class XGSettings(BaseModel):
    """xG model settings."""

    pitch_length_m: float
    pitch_width_m: float
    goal_width_m: float
    holdout_seasons: list[str]
    backtest_train_last_season: str
    min_category_count: int
    random_seed: int
    calibration_bins: int
    lgbm: dict


class DixonColesSettings(BaseModel):
    """Dixon-Coles settings."""

    time_decay_xi_per_day: float
    max_goals: int
    history_days: int
    ridge: float
    refit_every_days: int


class GBMSettings(BaseModel):
    """LightGBM match-model settings."""

    rolling_window_matches: int
    form_window_matches: int
    random_seed: int
    params: dict


class PredictorSettings(BaseModel):
    """Match predictor settings."""

    dixon_coles: DixonColesSettings
    gbm: GBMSettings
    ensemble_weight_grid: list[float]
    horizon_days: int
    calibration_bins: int


class XPtsSettings(BaseModel):
    """Expected-points simulation settings."""

    n_sims: int = Field(gt=0)
    random_seed: int


class SimilaritySettings(BaseModel):
    """Player similarity settings."""

    min_minutes: int
    pca_variance_kept: float = Field(gt=0, le=1)
    n_neighbours: int
    player_match_score_cutoff: float
    features: list[str]
    embedding_dim: int


class DatabaseSettings(BaseModel):
    """Supabase limits."""

    max_size_mb: int
    upsert_batch_rows: int


class Settings(BaseModel):
    """The full ``settings.yaml`` file."""

    seasons: SeasonsConfig
    timezone: dict[str, str]
    scraping: ScrapingSettings
    validation: ValidationSettings
    xg: XGSettings
    predictor: PredictorSettings
    xpts: XPtsSettings
    similarity: SimilaritySettings
    database: DatabaseSettings


def _read_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@lru_cache(maxsize=4)
def load_leagues(config_dir: Path = CONFIG_DIR) -> LeaguesConfig:
    """Load and validate ``leagues.yaml``."""
    return LeaguesConfig.model_validate(_read_yaml(config_dir / "leagues.yaml"))


@lru_cache(maxsize=4)
def load_settings(config_dir: Path = CONFIG_DIR) -> Settings:
    """Load and validate ``settings.yaml``."""
    return Settings.model_validate(_read_yaml(config_dir / "settings.yaml"))


def data_dir() -> Path:
    """Root of local pipeline data (``PITCHIQ_DATA_DIR`` or ``pipeline/data``)."""
    env = os.environ.get("PITCHIQ_DATA_DIR")
    return Path(env).resolve() if env else PIPELINE_DIR / "data"


def season_range(first: str, last: str) -> list[str]:
    """Return season ids from ``first`` to ``last`` inclusive, e.g. ``1415`` .. ``2627``."""
    start, end = int(first[:2]), int(last[:2])
    if end < start:
        raise ValueError(f"last season {last} is before first season {first}")
    return [f"{y:02d}{y + 1:02d}" for y in range(start, end + 1)]


def season_start_year(season_id: str) -> int:
    """Return the calendar year a season starts in (``2526`` -> ``2025``)."""
    return 2000 + int(season_id[:2])


def season_label(season_id: str) -> str:
    """Return the display label (``2526`` -> ``2025/26``)."""
    return f"{season_start_year(season_id)}/{season_id[2:]}"


def previous_season(season_id: str) -> str:
    """Return the season before ``season_id``."""
    y = int(season_id[:2]) - 1
    return f"{y:02d}{y + 1:02d}"
