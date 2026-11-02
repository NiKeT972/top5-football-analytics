"""Load and validate the YAML configuration in ``pipeline/config``.

All tunable numbers live in config files; code reads them through these models
so a typo or missing value fails loudly at start-up instead of mid-run.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
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


class SeasonsConfig(BaseModel):
    """Season range and windows."""

    first: str = Field(pattern=SEASON_PATTERN)
    current: str = Field(pattern=SEASON_PATTERN)
    db_window: int = Field(ge=1)
    backtest: list[str]


class Settings(BaseModel):
    """The full ``settings.yaml`` file.

    Sections other than ``seasons`` are kept as plain dicts for now; each later
    phase replaces its section with a typed model when it starts using it.
    """

    seasons: SeasonsConfig
    timezone: dict
    scraping: dict
    validation: dict
    xg: dict
    predictor: dict
    xpts: dict
    similarity: dict
    database: dict


def _read_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@lru_cache(maxsize=1)
def load_leagues(config_dir: Path = CONFIG_DIR) -> LeaguesConfig:
    """Load and validate ``leagues.yaml``."""
    return LeaguesConfig.model_validate(_read_yaml(config_dir / "leagues.yaml"))


@lru_cache(maxsize=1)
def load_settings(config_dir: Path = CONFIG_DIR) -> Settings:
    """Load and validate ``settings.yaml``."""
    return Settings.model_validate(_read_yaml(config_dir / "settings.yaml"))


def season_range(first: str, last: str) -> list[str]:
    """Return season ids from ``first`` to ``last`` inclusive, e.g. ``1415`` .. ``2627``."""
    start, end = int(first[:2]), int(last[:2])
    if end < start:
        raise ValueError(f"last season {last} is before first season {first}")
    return [f"{y:02d}{y + 1:02d}" for y in range(start, end + 1)]
