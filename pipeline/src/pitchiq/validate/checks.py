"""Data-quality gate: schemas per table plus cross-table checks.

``validate_all`` returns a report and raises :class:`ValidationFailed` when any *hard*
check fails, so the pipeline stops before publishing bad data. *Soft* checks are logged
and surfaced in the report without failing the run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd
import pandera.pandas as pa

from pitchiq.config import LeaguesConfig, Settings
from pitchiq.storage.parquet import Store

log = logging.getLogger(__name__)

SHOT_RESULTS = ["Goal", "OwnGoal", "SavedShot", "MissedShots", "BlockedShot", "ShotOnPost"]
SITUATIONS = ["OpenPlay", "FromCorner", "SetPiece", "DirectFreekick", "Penalty"]
SHOT_TYPES = ["RightFoot", "LeftFoot", "Head", "OtherBodyParts"]
MAX_MINUTE = 130


class ValidationFailed(RuntimeError):
    """At least one hard data-quality check failed."""


@dataclass
class Check:
    """A single check outcome."""

    name: str
    passed: bool
    hard: bool
    detail: str = ""


@dataclass
class Report:
    """All checks of a validation run."""

    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, passed: bool, *, hard: bool = True, detail: str = "") -> None:
        """Record a check."""
        self.checks.append(Check(name, bool(passed), hard, detail))
        level = logging.INFO if passed else (logging.ERROR if hard else logging.WARNING)
        log.log(level, "check %-45s %s %s", name, "PASS" if passed else "FAIL", detail)

    @property
    def failed_hard(self) -> list[Check]:
        """Hard checks that failed."""
        return [c for c in self.checks if c.hard and not c.passed]

    def to_markdown(self) -> str:
        """Render as a markdown table."""
        lines = ["| check | result | detail |", "|---|---|---|"]
        for c in self.checks:
            mark = "pass" if c.passed else ("**FAIL**" if c.hard else "warn")
            lines.append(f"| {c.name} | {mark} | {c.detail} |")
        return "\n".join(lines)


def schemas(settings: Settings) -> dict[str, pa.DataFrameSchema]:
    """Pandera schemas for the core tables."""
    v = settings.validation
    return {
        "matches": pa.DataFrameSchema(
            {
                "match_id": pa.Column("int64", unique=True),
                "league_id": pa.Column(str),
                "season_id": pa.Column(str, pa.Check.str_matches(r"^\d{4}$")),
                "kickoff_utc": pa.Column("datetime64[ns, UTC]", coerce=True),
                "home_team_id": pa.Column(str, nullable=False),
                "away_team_id": pa.Column(str, nullable=False),
                "status": pa.Column(str, pa.Check.isin(["scheduled", "finished", "pending"])),
                "home_goals": pa.Column(
                    "Int16", pa.Check.in_range(0, v.max_goals_per_team), nullable=True
                ),
                "away_goals": pa.Column(
                    "Int16", pa.Check.in_range(0, v.max_goals_per_team), nullable=True
                ),
            },
            checks=pa.Check(
                lambda d: (d["home_team_id"] != d["away_team_id"]).all(), error="team plays itself"
            ),
        ),
        "shots": pa.DataFrameSchema(
            {
                "shot_id": pa.Column("int64", unique=True),
                "match_id": pa.Column("int64"),
                "team_id": pa.Column(str, nullable=False),
                "player_id": pa.Column("int64"),
                "minute": pa.Column(int, pa.Check.in_range(0, MAX_MINUTE)),
                "x": pa.Column(float, pa.Check.in_range(0, 1)),
                "y": pa.Column(float, pa.Check.in_range(0, 1)),
                "xg_us": pa.Column(float, pa.Check.in_range(0, v.max_xg_per_shot)),
                "result": pa.Column(str, pa.Check.isin(SHOT_RESULTS)),
                "situation": pa.Column(str, pa.Check.isin(SITUATIONS)),
                "shot_type": pa.Column(str, pa.Check.isin(SHOT_TYPES)),
            }
        ),
        "player_match": pa.DataFrameSchema(
            {
                "match_id": pa.Column("int64"),
                "player_id": pa.Column("int64"),
                "team_id": pa.Column(str, nullable=False),
                "minutes": pa.Column(int, pa.Check.in_range(0, MAX_MINUTE)),
                "goals": pa.Column(int, pa.Check.ge(0)),
                "xg": pa.Column(float, pa.Check.ge(0)),
            },
            unique=["match_id", "player_id"],
        ),
        "odds": pa.DataFrameSchema(
            {
                "match_id": pa.Column("int64"),
                "odds_h": pa.Column(float, pa.Check.gt(1)),
                "odds_d": pa.Column(float, pa.Check.gt(1)),
                "odds_a": pa.Column(float, pa.Check.gt(1)),
            },
            unique=["match_id", "bookmaker", "kind"],
        ),
        "elo": pa.DataFrameSchema(
            {"team_id": pa.Column(str), "elo": pa.Column(float, pa.Check.in_range(500, 2500))},
            unique=["team_id", "valid_from"],
        ),
    }


def _schema_checks(store: Store, settings: Settings, report: Report) -> None:
    for table, schema in schemas(settings).items():
        df = store.read(table)
        if df.empty:
            report.add(
                f"schema:{table}", False, hard=table in {"matches"}, detail="table empty / missing"
            )
            continue
        try:
            schema.validate(df, lazy=True)
            report.add(f"schema:{table}", True, detail=f"{len(df):,} rows")
        except pa.errors.SchemaErrors as exc:
            cases = exc.failure_cases.head(5).to_dict("records")
            report.add(
                f"schema:{table}", False, detail=f"{len(exc.failure_cases)} failures, e.g. {cases}"
            )


def _league_shape_checks(
    store: Store, leagues: LeaguesConfig, settings: Settings, report: Report
) -> None:
    m = store.read("matches")
    bad = []
    for (league_id, season_id), g in m.groupby(["league_id", "season_id"]):
        n = leagues.get(league_id).teams_in_season(season_id)
        teams = set(g["home_team_id"]) | set(g["away_team_id"])
        if len(teams) != n or len(g) != n * (n - 1):
            bad.append(f"{league_id} {season_id}: {len(teams)} teams, {len(g)} matches")
        if g.duplicated(["home_team_id", "away_team_id"]).any():
            bad.append(f"{league_id} {season_id}: duplicate fixture")
    report.add(
        "league-seasons have n teams and n(n-1) fixtures",
        not bad,
        detail="; ".join(bad[:5])
        or f"{m.groupby(['league_id', 'season_id']).ngroups} league-seasons",
    )
    current = m[m["season_id"] == settings.seasons.current]
    report.add(
        "current season present for all leagues",
        current["league_id"].nunique() == len(leagues.leagues),
    )


def _shots_vs_score(store: Store, report: Report) -> None:
    """Goals recorded as shots must add up to the final score (own goals handled separately)."""
    shots, m = store.read("shots"), store.read("matches")
    if shots.empty:
        return
    fin = m[m["status"] == "finished"].set_index("match_id")
    goals = (
        shots[shots["result"] == "Goal"].groupby(["match_id", "side"]).size().unstack(fill_value=0)
    )
    own = (
        shots[shots["result"] == "OwnGoal"]
        .groupby(["match_id", "side"])
        .size()
        .unstack(fill_value=0)
    )
    goals = goals.reindex(columns=["h", "a"], fill_value=0)
    own = own.reindex(index=goals.index.union(own.index), columns=["h", "a"], fill_value=0)
    goals = goals.reindex(own.index, fill_value=0)
    covered = fin.index.intersection(shots["match_id"].unique())
    # Understat lists an own goal under the side that benefits from it.
    h = (goals["h"] + own["h"]).reindex(covered)
    a = (goals["a"] + own["a"]).reindex(covered)
    ok = (h == fin.loc[covered, "home_goals"].astype(int)) & (
        a == fin.loc[covered, "away_goals"].astype(int)
    )
    rate = float(ok.mean()) if len(ok) else 1.0
    report.add(
        "shot goals + own goals == final score",
        rate >= 0.995,
        hard=False,
        detail=f"{rate:.2%} of {len(ok):,} matches",
    )


def validate_all(store: Store, settings: Settings, leagues: LeaguesConfig) -> Report:
    """Run every check; raise :class:`ValidationFailed` if a hard check failed."""
    report = Report()
    _schema_checks(store, settings, report)
    _league_shape_checks(store, leagues, settings, report)
    _shots_vs_score(store, report)
    xc = store.read_json("fd_crosscheck.json", {})
    if xc:
        report.add(
            "football-data scores agree with Understat",
            xc["score_mismatches"] <= settings.validation.max_score_mismatches,
            detail=f"{xc['matches_compared']:,} compared, {xc['score_mismatches']} mismatches",
        )
    teams = store.read("teams")
    m = store.read("matches")
    unknown = set(m["home_team_id"]) - set(teams["team_id"]) if not m.empty else set()
    report.add("every match team has a canonical id", not unknown, detail=str(sorted(unknown)[:5]))
    store.write_json("validation_report.json", [c.__dict__ for c in report.checks])
    if report.failed_hard:
        raise ValidationFailed("; ".join(c.name for c in report.failed_hard))
    return report


def frame_summary(df: pd.DataFrame) -> str:
    """One-line summary used in logs."""
    return f"{len(df):,} rows x {df.shape[1]} cols"
