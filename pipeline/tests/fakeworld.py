"""A tiny synthetic football world served through a fake HTTP client.

One league (ENG1) with 4 teams over two seasons. Each source spells team names its own
way, so the canonical mapping is exercised end to end. Used only by tests.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

from pitchiq.config import LeaguesConfig, Settings, season_start_year

US_NAMES = {
    101: "Manchester United",
    102: "Manchester City",
    103: "Nottingham Forest",
    104: "Wolverhampton Wanderers",
}
FD_NAMES = {101: "Man United", 102: "Man City", 103: "Nott'm Forest", 104: "Wolves"}
ELO_NAMES = {101: "Man United", 102: "Man City", 103: "Forest", 104: "Wolves"}
SEASONS = ["2425", "2526"]
CURRENT = "2526"
TODAY = date(2025, 9, 20)


@dataclass
class World:
    """Synthetic payloads keyed by URL."""

    rng: np.random.Generator = field(default_factory=lambda: np.random.default_rng(7))
    league_pages: dict[str, dict] = field(default_factory=dict)
    match_pages: dict[int, dict] = field(default_factory=dict)
    fd_csv: dict[str, str] = field(default_factory=dict)
    fixtures_csv: str = ""
    next_shot_id: int = 1

    def build(self) -> World:
        """Generate every season."""
        fixtures_rows = []
        match_id = 1000
        for season in SEASONS:
            start = date(season_start_year(season), 8, 10)
            dates, rows = [], []
            pairs = list(itertools.permutations(US_NAMES, 2))
            for k, (h, a) in enumerate(pairs):
                match_id += 1
                kickoff = datetime.combine(
                    start + timedelta(days=7 * k), datetime.min.time()
                ) + timedelta(hours=15)
                finished = kickoff.date() < TODAY
                hg, ag = (
                    (int(self.rng.poisson(1.5)), int(self.rng.poisson(1.1)))
                    if finished
                    else (None, None)
                )
                dates.append(
                    {
                        "id": str(match_id),
                        "isResult": finished,
                        "h": {
                            "id": str(h),
                            "title": US_NAMES[h],
                            "short_title": US_NAMES[h][:3].upper(),
                        },
                        "a": {
                            "id": str(a),
                            "title": US_NAMES[a],
                            "short_title": US_NAMES[a][:3].upper(),
                        },
                        "goals": {
                            "h": str(hg) if finished else None,
                            "a": str(ag) if finished else None,
                        },
                        "xG": {"h": "1.4" if finished else None, "a": "0.9" if finished else None},
                        "datetime": kickoff.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )
                if finished:
                    self.match_pages[match_id] = self._match_page(match_id, h, a, hg, ag, season)
                    rows.append(self._fd_row(kickoff.date(), h, a, hg, ag))
                else:
                    fixtures_rows.append(self._fd_row(kickoff.date(), h, a, None, None))
            players = [
                {
                    "id": str(t * 10 + i),
                    "player_name": f"Player {t}-{i}",
                    "games": "10",
                    "time": str(900 + 30 * i),
                    "goals": "3",
                    "xG": "2.5",
                    "assists": "1",
                    "xA": "1.2",
                    "shots": "20",
                    "key_passes": "15",
                    "yellow_cards": "1",
                    "red_cards": "0",
                    "position": ["F S", "M S", "D", "GK"][i % 4],
                    "team_title": US_NAMES[t],
                    "npg": "3",
                    "npxG": "2.5",
                    "xGChain": "4.0",
                    "xGBuildup": "1.5",
                }
                for t in US_NAMES
                for i in range(4)
            ]
            teams = {str(t): {"id": str(t), "title": n, "history": []} for t, n in US_NAMES.items()}
            self.league_pages[season] = {"dates": dates, "teams": teams, "players": players}
            header = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,PSCH,PSCD,PSCA,AvgCH,AvgCD,AvgCA,PSH,PSD,PSA,AvgH,AvgD,AvgA"
            self.fd_csv[season] = "\n".join([header, *rows]) + "\n"
        header = "Div,Date,Time,HomeTeam,AwayTeam,PSH,PSD,PSA,AvgH,AvgD,AvgA"
        self.fixtures_csv = (
            "\n".join(
                [
                    header,
                    *[
                        ",".join(
                            r.split(",")[:2] + ["15:00"] + r.split(",")[2:4] + r.split(",")[12:]
                        )
                        for r in fixtures_rows
                    ],
                ]
            )
            + "\n"
        )
        return self

    def _fd_row(self, d: date, h: int, a: int, hg: int | None, ag: int | None) -> str:
        odds = "2.10,3.40,3.60,2.05,3.30,3.50,2.15,3.45,3.55,2.08,3.35,3.45"
        return f"E0,{d:%d/%m/%Y},{FD_NAMES[h]},{FD_NAMES[a]},{'' if hg is None else hg},{'' if ag is None else ag},{odds}"

    def _match_page(self, match_id: int, h: int, a: int, hg: int, ag: int, season: str) -> dict:
        shots = {"h": [], "a": []}
        for side, team, goals in (("h", h, hg), ("a", a, ag)):
            n_miss = int(self.rng.integers(3, 12))
            for k in range(goals + n_miss):
                is_goal = k < goals
                shots[side].append(
                    {
                        "id": str(self.next_shot_id),
                        "minute": str(int(self.rng.integers(1, 90))),
                        "result": "Goal" if is_goal else "MissedShots",
                        "X": f"{self.rng.uniform(0.7, 0.99):.3f}",
                        "Y": f"{self.rng.uniform(0.3, 0.7):.3f}",
                        "xG": f"{self.rng.uniform(0.02, 0.6):.4f}",
                        "player": f"Player {team}-0",
                        "h_a": side,
                        "player_id": str(team * 10),
                        "situation": "OpenPlay",
                        "season": season[:2],
                        "shotType": "RightFoot",
                        "match_id": str(match_id),
                        "player_assisted": None,
                        "lastAction": "Pass",
                    }
                )
                self.next_shot_id += 1
        rosters = {
            side: {
                str(team * 100 + i): {
                    "id": str(team * 100 + i),
                    "goals": str(goals if i == 0 else 0),
                    "own_goals": "0",
                    "shots": "2",
                    "xG": "0.3",
                    "time": "90",
                    "player_id": str(team * 10 + i),
                    "team_id": str(team),
                    "position": ["FW", "MC", "DC", "GK"][i],
                    "player": f"Player {team}-{i}",
                    "h_a": side,
                    "yellow_card": "0",
                    "red_card": "0",
                    "key_passes": "1",
                    "assists": "0",
                    "xA": "0.1",
                    "xGChain": "0.4",
                    "xGBuildup": "0.1",
                    "positionOrder": str(i + 1),
                }
                for i in range(4)
            }
            for side, team, goals in (("h", h, hg), ("a", a, ag))
        }
        return {"shots": shots, "rosters": rosters, "tmpl": {}}

    def elo_snapshot(self) -> str:
        """All clubs on any date, plus a second-division club that must be ignored."""
        rows = ["Rank,Club,Country,Level,Elo,From,To"]
        rows += [
            f"{i},{n},ENG,1,{1700 + 10 * i},2024-01-01,2024-01-02"
            for i, n in enumerate(ELO_NAMES.values(), 1)
        ]
        rows.append("99,Leeds,ENG,2,1600,2024-01-01,2024-01-02")
        return "\n".join(rows) + "\n"

    def elo_history(self, club: str) -> str:
        """A two-interval history for one club."""
        return (
            "Rank,Club,Country,Level,Elo,From,To\n"
            f"1,{club},ENG,1,1750,2024-07-01,2025-06-30\n"
            f"1,{club},ENG,1,1760,2025-07-01,2026-06-30\n"
        )


class FakeHTTP:
    """Duck-typed stand-in for :class:`pitchiq.http.PoliteClient`."""

    def __init__(self, source: str, world: World, cache_dir: Path) -> None:
        """Serve ``world`` for ``source``."""
        self.source = source
        self.world = world
        self.cache_dir = cache_dir
        self.n_requests = 0
        self.urls: list[str] = []

    def cache_path(self, url: str, suffix: str = "") -> Path:
        """Mirror PoliteClient.cache_path."""
        return self.cache_dir / self.source / (str(abs(hash(url))) + suffix)

    def _is_fresh(self, path: Path, max_age_s: float | None) -> bool:
        return False

    def get(self, url: str, **_: object) -> bytes:
        """Route a URL to synthetic content."""
        self.n_requests += 1
        self.urls.append(url)
        w = self.world
        if "getLeagueData" in url:
            year = int(url.rsplit("/", 1)[1])
            season = f"{year % 100:02d}{(year + 1) % 100:02d}"
            return json.dumps(w.league_pages[season]).encode()
        if "getMatchData" in url:
            return json.dumps(w.match_pages[int(url.rsplit("/", 1)[1])]).encode()
        if url.rstrip("/").endswith("understat.com"):
            return b"<html></html>"
        if "mmz4281" in url:
            season = url.split("/")[-2]
            return w.fd_csv.get(season, "").encode()
        if url.endswith("fixtures.csv"):
            return w.fixtures_csv.encode()
        if "clubelo" in url:
            tail = url.rsplit("/", 1)[1]
            if tail[:4].isdigit():
                return w.elo_snapshot().encode()
            return w.elo_history(tail).encode()
        raise AssertionError(f"unexpected URL {url}")


def shrink_config(settings: Settings, leagues: LeaguesConfig) -> tuple[Settings, LeaguesConfig]:
    """Shrink real config to the synthetic world (1 league, 4 teams, 2 seasons)."""
    s = settings.model_copy(deep=True)
    s.seasons.first, s.seasons.current, s.seasons.shots_first = SEASONS[0], CURRENT, SEASONS[0]
    lg = leagues.get("ENG1").model_copy(update={"n_teams": 4, "n_teams_history": {}})
    return s, LeaguesConfig(leagues=[lg])
