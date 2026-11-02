"""Match FBref players to Understat players (the canonical player spine).

Within each league-season, FBref team names are first mapped to canonical teams (the same
optimal-assignment approach as for football-data). Then, *within each team-season*, player
names are matched by optimal assignment on rapidfuzz similarity of normalised names. A
pair is accepted when its score clears ``player_match_score_cutoff``. Manual fixes go in
``config/player_overrides.csv``. The match rate is reported every run.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from rapidfuzz import fuzz
from scipy.optimize import linear_sum_assignment

from pitchiq.canonical.teams import assign_names, load_aliases
from pitchiq.config import CONFIG_DIR, Settings
from pitchiq.storage.parquet import Store


def _norm(name: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return " ".join(s.replace("-", " ").replace(".", " ").split())


def name_score(a: str, b: str) -> float:
    """Similarity of two player names in [0, 100] (handles reordered and missing names)."""
    a, b = _norm(a), _norm(b)
    return max(
        fuzz.token_sort_ratio(a, b), fuzz.token_set_ratio(a, b) * 0.95, fuzz.WRatio(a, b) * 0.9
    )


def match_team_players(
    us: pd.DataFrame, fb: pd.DataFrame, cutoff: float
) -> list[tuple[int, int, float]]:
    """Optimal assignment of Understat rows to FBref rows within one team-season."""
    if us.empty or fb.empty:
        return []
    scores = np.array([[name_score(u, f) for f in fb["fbref_player"]] for u in us["player_name"]])
    rows, cols = linear_sum_assignment(-scores)
    return [
        (int(us.index[r]), int(fb.index[c]), float(scores[r, c]))
        for r, c in zip(rows, cols, strict=True)
        if scores[r, c] >= cutoff
    ]


def link_players(store: Store, settings: Settings) -> dict[str, float]:
    """Attach FBref birth year / nation / position to ``player_season``; returns match stats."""
    fb = store.read("fbref_players")
    ps = store.read("player_season")
    if fb.empty or ps.empty:
        return {"match_rate": 0.0, "n_understat": len(ps), "n_matched": 0}
    ts = store.read("team_seasons")
    aliases = load_aliases()
    team_map = []
    for (lg, s), g in fb.groupby(["league_id", "season_id"]):
        sub = ts[(ts["league_id"] == lg) & (ts["season_id"] == s)]
        matches = assign_names(
            sorted(g["fbref_team"].unique()),
            dict(zip(sub["team_id"], sub["name"], strict=True)),
            aliases,
        )
        team_map += [
            {"league_id": lg, "season_id": s, "fbref_team": m.source_name, "team_id": m.team_id}
            for m in matches
        ]
    fb = fb.merge(
        pd.DataFrame(team_map), on=["league_id", "season_id", "fbref_team"], how="inner"
    ).reset_index(drop=True)

    cutoff = settings.similarity.player_match_score_cutoff
    links = []
    scope = ps[ps["season_id"].isin(fb["season_id"].unique())]
    for (s, team), us_g in scope.groupby(["season_id", "team_id"]):
        fb_g = fb[(fb["season_id"] == s) & (fb["team_id"] == team)]
        for ui, fi, score in match_team_players(us_g, fb_g, cutoff):
            links.append({"_ps_index": ui, "_fb_index": fi, "match_score": score})
    link = pd.DataFrame(links, columns=["_ps_index", "_fb_index", "match_score"])
    linked = link.merge(
        fb[["born", "nation", "fbref_pos", "fbref_player"]], left_on="_fb_index", right_index=True
    )
    linked = linked.set_index("_ps_index")

    overrides = pd.read_csv(CONFIG_DIR / "player_overrides.csv")
    ps = ps.drop(
        columns=[
            c for c in ("born", "nation", "fbref_pos", "fbref_player", "match_score") if c in ps
        ],
        errors="ignore",
    )
    ps = ps.join(linked[["born", "nation", "fbref_pos", "fbref_player", "match_score"]])
    if not overrides.empty:
        for r in overrides.itertuples():
            hit = (
                fb[fb["fbref_player"] == r.fbref_player_name]
                if hasattr(r, "fbref_player_name")
                else pd.DataFrame()
            )
            if not hit.empty:
                mask = ps["player_id"] == r.understat_player_id
                ps.loc[mask, ["born", "nation", "fbref_pos"]] = hit.iloc[0][
                    ["born", "nation", "fbref_pos"]
                ].to_numpy()
    start_year = 2000 + ps["season_id"].str[:2].astype(int)
    ps["age"] = (start_year - ps["born"].astype("Float64")).astype("Float64")
    store.write("player_season", ps)
    n = int((scope["minutes"] >= settings.similarity.min_minutes).sum())
    matched = int(
        ps.loc[scope.index][scope["minutes"] >= settings.similarity.min_minutes]["born"]
        .notna()
        .sum()
    )
    stats = {
        "n_understat_900": n,
        "n_matched_900": matched,
        "match_rate_900": matched / n if n else 0.0,
        "n_links": len(link),
    }
    store.write_json("player_link_stats.json", stats)
    return stats
