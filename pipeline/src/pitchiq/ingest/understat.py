"""Understat: fixtures/results, player season stats, shots and player match stats.

Understat serves JSON from ``/getLeagueData/<league>/<year>`` and ``/getMatchData/<id>``
(the same endpoints soccerdata uses). We call them directly because soccerdata's shot
parser drops ``lastAction`` and the ``Penalty`` situation, which the xG model needs.

Fetching is separated from parsing: ``parse_*`` functions are pure and unit-tested on
small JSON fixtures.
"""

from __future__ import annotations

import json
from html import unescape
from typing import Any

import pandas as pd

from pitchiq.config import ScrapingSettings, season_start_year
from pitchiq.http import PoliteClient

BASE_URL = "https://understat.com"
API_HEADERS = {"X-Requested-With": "XMLHttpRequest"}
SECONDS_PER_HOUR = 3600


class UnderstatClient:
    """Thin wrapper over :class:`PoliteClient` for Understat's JSON endpoints."""

    def __init__(self, http: PoliteClient, scraping: ScrapingSettings) -> None:
        """Wrap an HTTP client configured for the ``understat`` source."""
        self.http = http
        self.scraping = scraping
        self._has_cookies = False

    def _ensure_cookies(self) -> None:
        if not self._has_cookies:
            # Understat's API expects the session cookie set by the homepage.
            self.http.get(BASE_URL + "/", use_cache=False)
            self._has_cookies = True

    def league_season(self, understat_league: str, season_id: str, *, is_current: bool) -> dict:
        """Return the raw league-season payload (matches, teams, players)."""
        url = f"{BASE_URL}/getLeagueData/{understat_league}/{season_start_year(season_id)}"
        max_age = self.scraping.current_season_max_age_hours * SECONDS_PER_HOUR
        path = self.http.cache_path(url, ".json")
        if not (path.exists() and (not is_current or self.http._is_fresh(path, max_age))):
            self._ensure_cookies()
        body = self.http.get(
            url, headers=API_HEADERS, max_age_s=max_age if is_current else None, suffix=".json"
        )
        return json.loads(body)

    def match(self, match_id: int) -> dict:
        """Return the raw payload of one finished match (immutable, so never re-fetched)."""
        self._ensure_cookies()
        # Not cached on disk: the parsed Parquet is our cache of record for matches.
        body = self.http.get(
            f"{BASE_URL}/getMatchData/{match_id}", headers=API_HEADERS, use_cache=False
        )
        return json.loads(body)


# --------------------------------------------------------------------------- parsing


def _s(value: Any) -> str | None:
    return None if value is None else unescape(str(value))


def _f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _i(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_matches(payload: dict, league_id: str, season_id: str) -> pd.DataFrame:
    """Parse the ``dates`` block into one row per match (scheduled and finished)."""
    rows = []
    for m in payload["dates"]:
        rows.append(
            {
                "us_match_id": _i(m["id"]),
                "league_id": league_id,
                "season_id": season_id,
                # Understat datetimes are UTC.
                "kickoff_utc": pd.Timestamp(m["datetime"], tz="UTC"),
                "us_home_team_id": _i(m["h"]["id"]),
                "us_away_team_id": _i(m["a"]["id"]),
                "home_team_name": _s(m["h"]["title"]),
                "away_team_name": _s(m["a"]["title"]),
                "is_result": bool(m["isResult"]),
                "home_goals": _i(m["goals"]["h"]) if m["isResult"] else None,
                "away_goals": _i(m["goals"]["a"]) if m["isResult"] else None,
                "home_xg_us": _f(m["xG"]["h"]) if m["isResult"] else None,
                "away_xg_us": _f(m["xG"]["a"]) if m["isResult"] else None,
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.astype(
        {
            "home_goals": "Int16",
            "away_goals": "Int16",
            "home_xg_us": "Float64",
            "away_xg_us": "Float64",
        }
    )


def parse_teams(payload: dict, league_id: str, season_id: str) -> pd.DataFrame:
    """Parse the ``teams`` block into (understat team id, name) per league-season."""
    rows = [
        {
            "us_team_id": _i(t["id"]),
            "name": _s(t["title"]),
            "league_id": league_id,
            "season_id": season_id,
        }
        for t in payload["teams"].values()
    ]
    return pd.DataFrame(rows)


def parse_player_season(payload: dict, league_id: str, season_id: str) -> pd.DataFrame:
    """Parse the ``players`` block (season totals in this league)."""
    rows = []
    for p in payload["players"]:
        rows.append(
            {
                "us_player_id": _i(p["id"]),
                "player_name": _s(p["player_name"]),
                "league_id": league_id,
                "season_id": season_id,
                # Comma-separated when a player played for several teams in the league.
                "team_names": _s(p["team_title"]),
                "us_position": _s(p["position"]),
                "games": _i(p["games"]),
                "minutes": _i(p["time"]),
                "goals": _i(p["goals"]),
                "np_goals": _i(p["npg"]),
                "assists": _i(p["assists"]),
                "shots": _i(p["shots"]),
                "key_passes": _i(p["key_passes"]),
                "yellow_cards": _i(p["yellow_cards"]),
                "red_cards": _i(p["red_cards"]),
                "xg": _f(p["xG"]),
                "npxg": _f(p["npxG"]),
                "xa": _f(p["xA"]),
                "xg_chain": _f(p["xGChain"]),
                "xg_buildup": _f(p["xGBuildup"]),
            }
        )
    return pd.DataFrame(rows)


def parse_match_shots(payload: dict, us_match_id: int) -> pd.DataFrame:
    """Parse ``shots`` into one row per shot, keeping every raw attribute we need."""
    rows = []
    for side in ("h", "a"):
        for s in payload["shots"].get(side, []):
            rows.append(
                {
                    "shot_id": _i(s["id"]),
                    "us_match_id": us_match_id,
                    "side": side,
                    "minute": _i(s["minute"]),
                    "us_player_id": _i(s["player_id"]),
                    "player_name": _s(s["player"]),
                    "assist_player_name": _s(s.get("player_assisted")),
                    "x": _f(s["X"]),
                    "y": _f(s["Y"]),
                    "xg_us": _f(s["xG"]),
                    "result": _s(s["result"]),
                    "situation": _s(s["situation"]),
                    "shot_type": _s(s["shotType"]),
                    "last_action": _s(s.get("lastAction")) or "None",
                }
            )
    return pd.DataFrame(rows)


def parse_match_players(payload: dict, us_match_id: int) -> pd.DataFrame:
    """Parse ``rosters`` into one row per player appearance."""
    rows = []
    for side in ("h", "a"):
        for p in payload["rosters"].get(side, {}).values():
            rows.append(
                {
                    "us_match_id": us_match_id,
                    "side": side,
                    "us_player_id": _i(p["player_id"]),
                    "player_name": _s(p["player"]),
                    "us_team_id": _i(p["team_id"]),
                    "position": _s(p["position"]),
                    "position_order": _i(p.get("positionOrder")),
                    "minutes": _i(p["time"]),
                    "goals": _i(p["goals"]),
                    "own_goals": _i(p["own_goals"]),
                    "shots": _i(p["shots"]),
                    "assists": _i(p["assists"]),
                    "key_passes": _i(p["key_passes"]),
                    "yellow_cards": _i(p["yellow_card"]),
                    "red_cards": _i(p["red_card"]),
                    "xg": _f(p["xG"]),
                    "xa": _f(p["xA"]),
                    "xg_chain": _f(p["xGChain"]),
                    "xg_buildup": _f(p["xGBuildup"]),
                }
            )
    return pd.DataFrame(rows)
