"""Orchestrates ingestion: backfill and incremental daily updates.

Every source is fetched independently. A failing source is logged and recorded in the
freshness report, the other sources still update, previously stored data for the failing
source is left untouched (keep-last-good), and the run exits non-zero at the end so the
GitHub Action fails and emails the owner.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from pitchiq.canonical.teams import assign_names, load_aliases, make_team_id, mapping_frame
from pitchiq.config import (
    League,
    LeaguesConfig,
    Settings,
    season_range,
    season_start_year,
)
from pitchiq.http import PoliteClient, SourceError
from pitchiq.ingest import clubelo, football_data, understat
from pitchiq.storage.parquet import Store

log = logging.getLogger(__name__)

CHECKPOINT_EVERY = 250
ELO_SNAPSHOT_MONTH, ELO_SNAPSHOT_DAY = 11, 1
HOURS_PER_DAY = 24


@dataclass
class SourceStatus:
    """Outcome of one source in one run."""

    source: str
    ok: bool = True
    hard: bool = True  # a failing hard source fails the run
    message: str = "ok"
    rows: int = 0
    seconds: float = 0.0
    extra: dict = field(default_factory=dict)


@dataclass
class IngestResult:
    """Everything a run produced, for logging and the freshness file."""

    statuses: list[SourceStatus]
    requests: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """True unless a hard source failed."""
        return all(s.ok or not s.hard for s in self.statuses)


def _timed(status: SourceStatus, fn: Callable[[], None]) -> SourceStatus:
    t0 = time.monotonic()
    try:
        fn()
    except (SourceError, ValueError, KeyError) as exc:
        status.ok = False
        status.message = f"{type(exc).__name__}: {exc}"
        log.error("source %s failed: %s", status.source, status.message)
    status.seconds = round(time.monotonic() - t0, 1)
    return status


class Ingestor:
    """Runs the ingestion steps against a :class:`Store`."""

    def __init__(
        self,
        store: Store,
        settings: Settings,
        leagues: LeaguesConfig,
        clients: dict[str, PoliteClient] | None = None,
        now: pd.Timestamp | None = None,
    ) -> None:
        """Create an ingestor. ``clients`` maps source name to an HTTP client (injectable for tests)."""
        self.store = store
        self.settings = settings
        self.leagues = leagues
        self.now = now if now is not None else pd.Timestamp(datetime.now(UTC))
        self.today = self.now.date()
        if clients is None:
            clients = {
                src: PoliteClient(src, settings.scraping, store.raw)
                for src in ("understat", "football_data", "clubelo")
            }
        self.clients = clients
        self.aliases = load_aliases()

    # ------------------------------------------------------------------ helpers
    def seasons(self) -> list[str]:
        """All seasons from the configured first to current."""
        return season_range(self.settings.seasons.first, self.settings.seasons.current)

    def is_current(self, season_id: str) -> bool:
        """Whether ``season_id`` is the current (still changing) season."""
        return season_id == self.settings.seasons.current

    # ------------------------------------------------------------------ run
    def run(self, *, details: bool = True, max_match_requests: int | None = None) -> IngestResult:
        """Run all sources. ``details`` fetches per-match shots/lineups (the slow part)."""
        statuses = [_timed(SourceStatus("understat_league"), self.ingest_understat_leagues)]
        have_matches = self.store.exists("matches")
        dependent: list[tuple[SourceStatus, Callable[[], None]]] = []
        if details:
            budget = max_match_requests or self.settings.scraping.max_match_requests_per_run
            st = SourceStatus("understat_matches")
            dependent.append((st, lambda: self.ingest_understat_matches(budget, st)))
        dependent.append((SourceStatus("football_data"), self.ingest_football_data))
        dependent.append((SourceStatus("clubelo"), self.ingest_clubelo))
        for status, fn in dependent:
            if not have_matches:
                status.ok = False
                status.message = (
                    "skipped: no Understat fixtures stored yet (team mapping needs them)"
                )
                statuses.append(status)
            else:
                statuses.append(_timed(status, fn))
        requests = {name: client.n_requests for name, client in self.clients.items()}
        log.info("HTTP requests this run: %s", requests)
        return IngestResult(statuses, requests)

    # ------------------------------------------------------------------ Understat
    def ingest_understat_leagues(self) -> None:
        """Fixtures/results, teams and player season stats for every league-season."""
        client = understat.UnderstatClient(self.clients["understat"], self.settings.scraping)
        matches, teams, players = [], [], []
        for lg in self.leagues.leagues:
            for season_id in self.seasons():
                payload = client.league_season(
                    lg.sources.understat, season_id, is_current=self.is_current(season_id)
                )
                matches.append(understat.parse_matches(payload, lg.league_id, season_id))
                teams.append(understat.parse_teams(payload, lg.league_id, season_id))
                players.append(understat.parse_player_season(payload, lg.league_id, season_id))

        team_seasons = pd.concat(teams, ignore_index=True)
        team_table = self._build_team_table(team_seasons)
        id_map = dict(zip(team_table["us_team_id"], team_table["team_id"], strict=True))

        m = pd.concat(matches, ignore_index=True)
        m["match_id"] = m["us_match_id"].astype("int64")
        m["home_team_id"] = m["us_home_team_id"].map(id_map)
        m["away_team_id"] = m["us_away_team_id"].map(id_map)
        now = self.now
        m["status"] = "scheduled"
        m.loc[m["is_result"], "status"] = "finished"
        m.loc[~m["is_result"] & (m["kickoff_utc"] < now - pd.Timedelta(hours=6)), "status"] = (
            "pending"
        )
        self.store.write("matches", m.drop(columns=["us_match_id"]))

        team_seasons["team_id"] = team_seasons["us_team_id"].map(id_map)
        self.store.write("team_seasons", team_seasons)
        self.store.write("teams", team_table)

        ps = pd.concat(players, ignore_index=True)
        first_team = ps["team_names"].str.split(",").str[0]
        name_map = team_seasons.set_index(["league_id", "season_id", "name"])["team_id"]
        keys = pd.MultiIndex.from_arrays([ps["league_id"], ps["season_id"], first_team])
        ps["team_id"] = name_map.reindex(keys).to_numpy()
        ps["player_id"] = ps["us_player_id"].astype("int64")
        self.store.write("player_season_us", ps)

    def _build_team_table(self, team_seasons: pd.DataFrame) -> pd.DataFrame:
        """One row per Understat team; keeps previously assigned ids stable."""
        country = {lg.league_id: lg.country for lg in self.leagues.leagues}
        latest = team_seasons.sort_values("season_id").groupby("us_team_id").last().reset_index()
        latest["country"] = latest["league_id"].map(country)
        existing = self.store.read("teams")
        old_ids = (
            dict(zip(existing["us_team_id"], existing["team_id"], strict=True))
            if not existing.empty
            else {}
        )
        latest["team_id"] = [
            old_ids.get(us_id) or make_team_id(c, n)
            for us_id, c, n in zip(
                latest["us_team_id"], latest["country"], latest["name"], strict=True
            )
        ]
        dupes = latest["team_id"].duplicated(keep=False)
        latest.loc[dupes, "team_id"] = (
            latest.loc[dupes, "team_id"] + "-" + latest.loc[dupes, "us_team_id"].astype(str)
        )
        return latest[["team_id", "us_team_id", "name", "league_id", "country"]]

    def ingest_understat_matches(self, budget: int, status: SourceStatus) -> None:
        """Shots and player match stats for finished matches we do not have yet (newest first)."""
        client = understat.UnderstatClient(self.clients["understat"], self.settings.scraping)
        matches = self.store.read("matches")
        first_shots = self.settings.seasons.shots_first
        fetched = self.store.read("match_details_fetched")
        have = set(fetched["match_id"]) if not fetched.empty else set()
        todo = matches[
            (matches["status"] == "finished")
            & (matches["season_id"] >= first_shots)
            & ~matches["match_id"].isin(have)
        ]
        todo = todo.sort_values("kickoff_utc", ascending=False)
        status.extra["missing_before"] = len(todo)
        todo = todo.head(budget)
        log.info("understat: %d matches to fetch (budget %d)", len(todo), budget)

        shots_buf, players_buf, done_buf = [], [], []

        def flush() -> None:
            if not done_buf:
                return
            if shots_buf:
                self.store.upsert("shots_raw", pd.concat(shots_buf, ignore_index=True), ["shot_id"])
            if players_buf:
                self.store.upsert(
                    "player_match_raw",
                    pd.concat(players_buf, ignore_index=True),
                    ["match_id", "player_id"],
                )
            self.store.upsert("match_details_fetched", pd.DataFrame(done_buf), ["match_id"])
            status.rows += len(done_buf)
            shots_buf.clear()
            players_buf.clear()
            done_buf.clear()

        for row in todo.itertuples():
            side_team = {"h": row.home_team_id, "a": row.away_team_id}
            payload = client.match(int(row.match_id))
            shots = understat.parse_match_shots(payload, int(row.match_id))
            players = understat.parse_match_players(payload, int(row.match_id))
            for df in (shots, players):
                if not df.empty:
                    df.insert(0, "match_id", df.pop("us_match_id").astype("int64"))
                    df["team_id"] = df["side"].map(side_team)
                    df["player_id"] = df.pop("us_player_id").astype("int64")
            shots_buf.append(shots)
            players_buf.append(players)
            done_buf.append(
                {
                    "match_id": int(row.match_id),
                    "n_shots": len(shots),
                    "fetched_at": pd.Timestamp.now(tz="UTC"),
                }
            )
            if len(done_buf) >= CHECKPOINT_EVERY:
                flush()
                log.info("understat: checkpoint, %d matches fetched so far", status.rows)
        flush()
        status.extra["missing_after"] = status.extra["missing_before"] - status.rows

    # ------------------------------------------------------------------ football-data
    def _targets(self, league_id: str, season_id: str) -> dict[str, str]:
        ts = self.store.read("team_seasons")
        sub = ts[(ts["league_id"] == league_id) & (ts["season_id"] == season_id)]
        return dict(zip(sub["team_id"], sub["name"], strict=True))

    def ingest_football_data(self) -> None:
        """Season CSVs (results + closing odds) and the upcoming fixtures CSV (pre-match odds)."""
        http = self.clients["football_data"]
        max_age = self.settings.scraping.current_season_max_age_hours
        matches = self.store.read("matches")
        key = matches.set_index(["league_id", "season_id", "home_team_id", "away_team_id"])
        mappings, odds_rows, checks = [], [], []

        for lg in self.leagues.leagues:
            for season_id in self.seasons():
                raw = football_data.fetch_season(
                    http,
                    season_id,
                    lg.sources.football_data,
                    is_current=self.is_current(season_id),
                    max_age_hours=max_age,
                )
                fd = football_data.parse_csv(raw)
                if fd.empty:
                    continue
                fd_mapped, mp = self._map_fd(fd, lg, season_id)
                mappings.append(mp)
                joined = fd_mapped.merge(
                    key[["match_id", "kickoff_utc", "home_goals", "away_goals"]].reset_index(),
                    on=["league_id", "season_id", "home_team_id", "away_team_id"],
                    how="left",
                    suffixes=("", "_us"),
                )
                unmatched = joined["match_id"].isna()
                if unmatched.any():
                    bad = (
                        joined.loc[unmatched, ["date", "home_team_name", "away_team_name"]]
                        .head(5)
                        .to_dict("records")
                    )
                    raise ValueError(
                        f"{lg.league_id} {season_id}: {unmatched.sum()} football-data rows not in Understat, e.g. {bad}"
                    )
                checks.append(joined)
                odds_rows.append(joined)

        self.store.write("team_source_names_fd", pd.concat(mappings, ignore_index=True))
        fd_all = pd.concat(checks, ignore_index=True)
        self._check_fd_against_understat(fd_all)
        odds_closing = _odds_long(fd_all, kinds=("closing", "pre"))

        fixtures_raw = football_data.fetch_fixtures(
            http, self.settings.scraping.fixtures_max_age_hours
        )
        upcoming = []
        current = self.settings.seasons.current
        for lg in self.leagues.leagues:
            fx = football_data.parse_csv(fixtures_raw, league_code=lg.sources.football_data)
            if fx.empty:
                continue
            fx_mapped, _ = self._map_fd(fx, lg, current)
            j = fx_mapped.join(
                key[["match_id"]], on=["league_id", "season_id", "home_team_id", "away_team_id"]
            )
            upcoming.append(j.dropna(subset=["match_id"]))
        odds_pre = (
            _odds_long(pd.concat(upcoming, ignore_index=True), kinds=("pre",))
            if upcoming
            else pd.DataFrame()
        )
        odds = pd.concat([odds_closing, odds_pre], ignore_index=True).drop_duplicates(
            ["match_id", "bookmaker", "kind"], keep="last"
        )
        odds["captured_at"] = pd.Timestamp.now(tz="UTC")
        old = self.store.read("odds")
        if not old.empty:
            # Keep previously captured pre-match odds for matches no longer in fixtures.csv.
            odds = pd.concat([old, odds], ignore_index=True).drop_duplicates(
                ["match_id", "bookmaker", "kind"], keep="last"
            )
        self.store.write("odds", odds)

    def _map_fd(
        self, fd: pd.DataFrame, lg: League, season_id: str
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        targets = self._targets(lg.league_id, season_id)
        names = sorted(set(fd["home_team_name"]) | set(fd["away_team_name"]))
        matched = assign_names(names, targets, self.aliases)
        weak = [m for m in matched if m.score < self.settings.validation.min_team_match_score]
        if weak or len(matched) != len(names):
            raise ValueError(
                f"{lg.league_id} {season_id}: weak/missing team matches {weak or names}"
            )
        name_to_id = {m.source_name: m.team_id for m in matched}
        out = fd.assign(
            league_id=lg.league_id,
            season_id=season_id,
            home_team_id=fd["home_team_name"].map(name_to_id),
            away_team_id=fd["away_team_name"].map(name_to_id),
        )
        return out, mapping_frame(matched, "football_data", lg.league_id, season_id)

    def _check_fd_against_understat(self, fd: pd.DataFrame) -> None:
        both = fd.dropna(subset=["home_goals", "away_goals", "home_goals_us", "away_goals_us"])
        mismatch = both[
            (both["home_goals"] != both["home_goals_us"])
            | (both["away_goals"] != both["away_goals_us"])
        ]
        kickoff_date = pd.to_datetime(both["kickoff_utc"]).dt.tz_convert(None).dt.normalize()
        day_gap = (kickoff_date - pd.to_datetime(both["date"])).abs().dt.days
        tol = self.settings.validation.fixture_date_tolerance_days
        far = int((day_gap > tol).sum())
        log.info(
            "football-data cross-check: %d matches, %d score mismatches, %d date gaps > %dd",
            len(both),
            len(mismatch),
            far,
            tol,
        )
        self.store.write_json(
            "fd_crosscheck.json",
            {
                "matches_compared": len(both),
                "score_mismatches": len(mismatch),
                "date_gaps": far,
                "examples": mismatch[
                    ["match_id", "home_goals", "away_goals", "home_goals_us", "away_goals_us"]
                ]
                .head(10)
                .to_dict("records"),
            },
        )
        if len(mismatch) > self.settings.validation.max_score_mismatches:
            raise ValueError(
                f"{len(mismatch)} finished matches have different scores in football-data and Understat"
            )

    # ------------------------------------------------------------------ ClubElo
    def ingest_clubelo(self) -> None:
        """Map ClubElo club names to teams per league-season, then pull each club's history.

        Individual failed requests do not discard the rest: whatever was fetched is merged
        with the previously stored ratings, and the step still fails at the end so the run
        is flagged.
        """
        http = self.clients["clubelo"]
        errors: list[str] = []
        mappings = [self.store.read("team_source_names_elo")]
        for lg in self.leagues.leagues:
            for season_id in self.seasons():
                snap_day = min(
                    date(season_start_year(season_id), ELO_SNAPSHOT_MONTH, ELO_SNAPSHOT_DAY),
                    self.today - timedelta(days=1),
                )
                try:
                    clubs = clubelo.parse_snapshot(
                        clubelo.fetch_snapshot(http, snap_day), lg.sources.clubelo_country
                    )
                except SourceError as exc:
                    errors.append(str(exc))
                    continue
                targets = self._targets(lg.league_id, season_id)
                if clubs.empty or not targets:
                    continue
                matched = assign_names(clubs["club"].tolist(), targets, self.aliases)
                # A snapshot can include clubs the assignment had to pair with a leftover team;
                # keep only confident pairs.
                matched = [
                    m for m in matched if m.score >= self.settings.validation.min_team_match_score
                ]
                mappings.append(mapping_frame(matched, "clubelo", lg.league_id, season_id))
        mp = pd.concat([m for m in mappings if not m.empty], ignore_index=True).drop_duplicates(
            ["league_id", "season_id", "source_name"], keep="last"
        )
        self.store.write("team_source_names_elo", mp)

        current_teams = set(mp.loc[mp["season_id"] == self.settings.seasons.current, "team_id"])
        first_day = date(season_start_year(self.settings.seasons.first), 7, 1)
        frames = [self.store.read("elo")]
        for (club, team_id), _ in mp.groupby(["source_name", "team_id"]):
            max_age = HOURS_PER_DAY - 4 if team_id in current_teams else 24 * 365 * 10
            try:
                hist = clubelo.parse_history(clubelo.fetch_history(http, club, max_age))
            except SourceError as exc:
                errors.append(str(exc))
                continue
            hist = hist[hist["valid_to"] >= first_day]
            frames.append(hist.assign(team_id=team_id))
        frames = [f for f in frames if not f.empty]
        if frames:
            elo = pd.concat(frames, ignore_index=True).drop_duplicates(
                ["team_id", "valid_from"], keep="last"
            )
            self.store.write("elo", elo[["team_id", "club", "valid_from", "valid_to", "elo"]])
        if errors:
            raise SourceError("clubelo", f"{len(errors)} requests", "; ".join(errors[:3]))


def _odds_long(df: pd.DataFrame, kinds: tuple[str, ...]) -> pd.DataFrame:
    """Wide odds columns -> one row per (match, bookmaker, kind)."""
    rows = []
    for book, kind in football_data.ODDS_COLUMNS:
        if kind not in kinds:
            continue
        cols = [f"odds_{book}_{kind}_{o}" for o in ("h", "d", "a")]
        sub = df[["match_id", *cols]].dropna()
        sub = sub[(sub[cols] > 1.0).all(axis=1)]
        sub.columns = ["match_id", "odds_h", "odds_d", "odds_a"]
        rows.append(sub.assign(bookmaker=book, kind=kind))
    if not rows:
        return pd.DataFrame(columns=["match_id", "odds_h", "odds_d", "odds_a", "bookmaker", "kind"])
    out = pd.concat(rows, ignore_index=True)
    out["match_id"] = out["match_id"].astype("int64")
    for c in ("odds_h", "odds_d", "odds_a"):
        out[c] = out[c].astype(float)
    return out
