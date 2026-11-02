"""ClubElo: daily Elo ratings via the public CSV API (http://api.clubelo.com).

* ``/<YYYY-MM-DD>`` returns every club's rating on that date (used to discover which ClubElo
  club names belong to a league-season).
* ``/<ClubName>`` returns a club's full rating history as ``From``/``To`` intervals, which is
  exactly how we store it (~40 rows per team-season instead of 365).
"""

from __future__ import annotations

import io
from datetime import date

import pandas as pd

from pitchiq.http import PoliteClient

BASE_URL = "http://api.clubelo.com"
SECONDS_PER_HOUR = 3600
TOP_LEVEL = 1


def fetch_snapshot(http: PoliteClient, on: date) -> bytes:
    """All clubs' ratings on a date. Past dates never change, so they are cached forever."""
    is_past = on < date.today()
    return http.get(
        f"{BASE_URL}/{on.isoformat()}",
        max_age_s=None if is_past else 12 * SECONDS_PER_HOUR,
        suffix=".csv",
    )


def fetch_history(http: PoliteClient, club: str, max_age_hours: float) -> bytes:
    """Return a club's full history (refreshed after ``max_age_hours``)."""
    return http.get(
        f"{BASE_URL}/{club.replace(' ', '')}",
        max_age_s=max_age_hours * SECONDS_PER_HOUR,
        suffix=".csv",
    )


def parse_snapshot(raw: bytes, country: str) -> pd.DataFrame:
    """Return top-flight clubs of ``country`` from a date snapshot."""
    df = pd.read_csv(io.BytesIO(raw))
    df = df[(df["Country"] == country) & (df["Level"] == TOP_LEVEL)]
    return df[["Club", "Country", "Elo"]].rename(
        columns={"Club": "club", "Country": "country", "Elo": "elo"}
    )


def parse_history(raw: bytes) -> pd.DataFrame:
    """Return ``club, valid_from, valid_to, elo`` intervals."""
    df = pd.read_csv(io.BytesIO(raw))
    if df.empty:
        return pd.DataFrame(columns=["club", "valid_from", "valid_to", "elo"])
    return pd.DataFrame(
        {
            "club": df["Club"].astype(str),
            "valid_from": pd.to_datetime(df["From"]).dt.date,
            "valid_to": pd.to_datetime(df["To"]).dt.date,
            "elo": df["Elo"].astype(float),
        }
    )
