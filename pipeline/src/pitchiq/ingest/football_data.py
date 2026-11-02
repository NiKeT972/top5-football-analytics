"""football-data.co.uk: results and betting odds (historical CSVs + upcoming fixtures).

Odds columns we keep (all decimal):

* Closing odds: Pinnacle ``PSCH/PSCD/PSCA``, market average ``AvgCH/AvgCD/AvgCA``.
* Pre-match odds: Pinnacle ``PSH/PSD/PSA``, market average ``AvgH/AvgD/AvgA``.

Older seasons name the market average ``BbAvH`` etc.; we normalise those to ``Avg*``.
"""

from __future__ import annotations

import io

import pandas as pd

from pitchiq.http import PoliteClient

BASE_URL = "https://www.football-data.co.uk"
SECONDS_PER_HOUR = 3600

# (canonical bookmaker key, kind) -> (home, draw, away) column names
ODDS_COLUMNS: dict[tuple[str, str], tuple[str, str, str]] = {
    ("pinnacle", "closing"): ("PSCH", "PSCD", "PSCA"),
    ("market_avg", "closing"): ("AvgCH", "AvgCD", "AvgCA"),
    ("pinnacle", "pre"): ("PSH", "PSD", "PSA"),
    ("market_avg", "pre"): ("AvgH", "AvgD", "AvgA"),
}
LEGACY_RENAMES = {"BbAvH": "AvgH", "BbAvD": "AvgD", "BbAvA": "AvgA"}


def season_url(season_id: str, fd_code: str) -> str:
    """URL of a season CSV, e.g. ``/mmz4281/2526/E0.csv``."""
    return f"{BASE_URL}/mmz4281/{season_id}/{fd_code}.csv"


def fetch_season(
    http: PoliteClient, season_id: str, fd_code: str, *, is_current: bool, max_age_hours: float
) -> bytes:
    """Download (or read from cache) one season CSV. Finished seasons are cached forever."""
    return http.get(
        season_url(season_id, fd_code),
        max_age_s=max_age_hours * SECONDS_PER_HOUR if is_current else None,
        suffix=".csv",
    )


def fetch_fixtures(http: PoliteClient, max_age_hours: float) -> bytes:
    """Download the upcoming-fixtures CSV (all leagues, pre-match odds)."""
    return http.get(
        f"{BASE_URL}/fixtures.csv", max_age_s=max_age_hours * SECONDS_PER_HOUR, suffix=".csv"
    )


def _read_csv(raw: bytes) -> pd.DataFrame:
    # Files are latin-1 and occasionally carry trailing empty columns/rows.
    text = (
        raw.decode("utf-8-sig", errors="replace")
        if raw[:3] == b"\xef\xbb\xbf"
        else raw.decode("latin-1")
    )
    df = pd.read_csv(io.StringIO(text), on_bad_lines="skip")
    df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]
    return df.dropna(how="all")


def _parse_dates(df: pd.DataFrame) -> pd.Series:
    dates = pd.to_datetime(df["Date"], format="%d/%m/%Y", errors="coerce")
    two_digit = pd.to_datetime(df["Date"], format="%d/%m/%y", errors="coerce")
    return dates.fillna(two_digit)


def parse_csv(raw: bytes, league_code: str | None = None) -> pd.DataFrame:
    """Parse a season or fixtures CSV into a tidy frame.

    Args:
        raw: CSV bytes.
        league_code: If given, keep only rows whose ``Div`` equals it (fixtures file).

    """
    df = _read_csv(raw).rename(columns=LEGACY_RENAMES)
    if league_code is not None:
        df = df[df["Div"] == league_code]
    if df.empty:
        return pd.DataFrame()
    out = pd.DataFrame(
        {
            "fd_div": df["Div"].astype(str),
            "date": _parse_dates(df).dt.date,
            "home_team_name": df["HomeTeam"].astype(str).str.strip(),
            "away_team_name": df["AwayTeam"].astype(str).str.strip(),
            "home_goals": pd.to_numeric(df.get("FTHG"), errors="coerce").astype("Int16")
            if "FTHG" in df
            else pd.Series(pd.NA, index=df.index, dtype="Int16"),
            "away_goals": pd.to_numeric(df.get("FTAG"), errors="coerce").astype("Int16")
            if "FTAG" in df
            else pd.Series(pd.NA, index=df.index, dtype="Int16"),
        }
    )
    for (book, kind), cols in ODDS_COLUMNS.items():
        for outcome, col in zip(("h", "d", "a"), cols, strict=True):
            values = (
                pd.to_numeric(df[col], errors="coerce")
                if col in df
                else pd.Series(float("nan"), index=df.index)
            )
            out[f"odds_{book}_{kind}_{outcome}"] = values.astype("Float64")
    return out.dropna(subset=["date"]).reset_index(drop=True)
