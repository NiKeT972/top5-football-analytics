"""Canonical team identity across Understat, football-data.co.uk and ClubElo.

Understat's numeric team id is the spine. Each Understat team gets a stable slug
``team_id`` (e.g. ``eng-manchester-united``). Other sources are mapped *per league-season*:
inside one league-season both sources list the same closed set of ~20 clubs, so we solve
an optimal assignment over fuzzy name similarity (plus a manual alias file) instead of
matching each name greedily. The football-data mapping is then verified independently by
requiring the two sources' fixture lists to be identical.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from rapidfuzz import fuzz
from scipy.optimize import linear_sum_assignment

from pitchiq.config import CONFIG_DIR

# Tokens that carry no identity ("FC Barcelona" vs "Barcelona").
_NOISE_TOKENS = frozenset(
    [
        "fc",
        "cf",
        "ac",
        "as",
        "ss",
        "ssc",
        "sc",
        "afc",
        "ud",
        "cd",
        "rcd",
        "sd",
        "club",
        "de",
        "calcio",
        "vfb",
        "vfl",
        "tsg",
        "sv",
        "rc",
        "ogc",
        "osc",
        "losc",
        "stade",
        "olympique",
        "hellas",
        "1913",
        "2013",
        "1899",
        "1904",
        "1846",
        "1848",
        "1907",
        "1909",
        "the",
    ]
)


def normalise(name: str) -> str:
    """Lower-case, strip accents and punctuation, drop noise tokens."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    tokens = re.sub(r"[^a-z0-9 ]+", " ", ascii_name.lower()).split()
    kept = [t for t in tokens if t not in _NOISE_TOKENS]
    return " ".join(kept or tokens)


def slugify(name: str) -> str:
    """URL-safe slug of a name."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


def make_team_id(country: str, understat_name: str) -> str:
    """Canonical team id, e.g. ``eng-manchester-united``."""
    return f"{country[:3].lower()}-{slugify(understat_name)}"


def load_aliases(path: Path = CONFIG_DIR / "team_aliases.yaml") -> dict[str, list[str]]:
    """Return ``{understat_name: [aliases]}`` from the alias file."""
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return {k: list(v) for k, v in (data.get("aliases") or {}).items()}


def similarity(source_name: str, target_name: str, aliases: dict[str, list[str]]) -> float:
    """Similarity in [0, 1] between a source name and an Understat (target) name."""
    for alias in aliases.get(target_name, []):
        if normalise(alias) == normalise(source_name):
            return 1.0
    a, b = normalise(source_name), normalise(target_name)
    if a == b:
        return 1.0
    return max(fuzz.token_set_ratio(a, b), fuzz.partial_ratio(a, b) * 0.9, fuzz.ratio(a, b)) / 100.0


@dataclass(frozen=True)
class NameMatch:
    """One source name assigned to one canonical team."""

    source_name: str
    team_id: str
    target_name: str
    score: float


def assign_names(
    source_names: list[str],
    targets: dict[str, str],
    aliases: dict[str, list[str]],
) -> list[NameMatch]:
    """Optimally assign source names to canonical teams.

    Args:
        source_names: Club names as written by the other source (one league-season).
        targets: ``{team_id: understat_name}`` for the same league-season.
        aliases: Alias table from :func:`load_aliases`.

    Returns:
        One :class:`NameMatch` per source name that could be assigned.

    """
    src = sorted(set(source_names))
    tgt_ids = sorted(targets)
    if not src or not tgt_ids:
        return []
    scores = np.array([[similarity(s, targets[t], aliases) for t in tgt_ids] for s in src])
    rows, cols = linear_sum_assignment(-scores)
    return [
        NameMatch(src[r], tgt_ids[c], targets[tgt_ids[c]], float(scores[r, c]))
        for r, c in zip(rows, cols, strict=True)
    ]


def mapping_frame(
    matches: list[NameMatch], source: str, league_id: str, season_id: str
) -> pd.DataFrame:
    """Turn matches into rows of the ``team_source_names`` table."""
    return pd.DataFrame(
        [
            {
                "source": source,
                "league_id": league_id,
                "season_id": season_id,
                "source_name": m.source_name,
                "team_id": m.team_id,
                "match_score": m.score,
            }
            for m in matches
        ],
        columns=["source", "league_id", "season_id", "source_name", "team_id", "match_score"],
    )
