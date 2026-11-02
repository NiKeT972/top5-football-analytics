"""Player similarity and percentile ranks.

* Per-90 vectors from Understat season stats for outfield players with at least
  ``min_minutes`` (goalkeepers are excluded: free data has no meaningful GK metrics).
* Players are only compared within the same season and position group (FW, AMW, CM, DEF).
* Features are standardised within each (season, group), reduced with PCA keeping
  ``pca_variance_kept`` of the variance, and compared with cosine similarity.
* Percentiles are computed within the same (season, group) and drive the radars.

Honesty note shown in the UI: the free data is attacking-heavy (xG, xA, chains), so
defensive profiles are poorly separated.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from pitchiq.config import SimilaritySettings
from pitchiq.storage.parquet import Store

MINUTES_PER_MATCH = 90.0
OUTFIELD_GROUPS = ["FW", "AMW", "CM", "DEF"]
PER90_SOURCE = [
    "npxg",
    "xa",
    "shots",
    "key_passes",
    "xg_chain",
    "xg_buildup",
    "np_goals",
    "assists",
    "xg",
    "goals",
]


def per90_table(player_season: pd.DataFrame, cfg: SimilaritySettings) -> pd.DataFrame:
    """Eligible outfield player-seasons with per-90 metrics."""
    ps = player_season[
        (player_season["minutes"] >= cfg.min_minutes)
        & player_season["position_group"].isin(OUTFIELD_GROUPS)
    ].copy()
    factor = MINUTES_PER_MATCH / ps["minutes"].astype(float)
    for c in PER90_SOURCE:
        ps[c] = ps[c].astype(float) * factor
    ps["npxg_per_shot"] = np.where(
        ps["shots"] > 0, ps["npxg"] / ps["shots"].where(ps["shots"] > 0), 0.0
    )
    return ps.reset_index(drop=True)


def embed_group(group: pd.DataFrame, cfg: SimilaritySettings) -> np.ndarray:
    """Standardise + PCA; returns unit-length vectors zero-padded to ``embedding_dim``."""
    X = StandardScaler().fit_transform(group[cfg.features].to_numpy(float))
    n_comp = min(len(cfg.features), len(group))
    pca = PCA(n_components=n_comp, random_state=0).fit(X)
    keep = int(np.searchsorted(np.cumsum(pca.explained_variance_ratio_), cfg.pca_variance_kept) + 1)
    Z = pca.transform(X)[:, :keep]
    Z = Z / np.clip(np.linalg.norm(Z, axis=1, keepdims=True), 1e-12, None)
    out = np.zeros((len(group), cfg.embedding_dim))
    out[:, : min(keep, cfg.embedding_dim)] = Z[:, : cfg.embedding_dim]
    return out


def nearest(emb: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """Top-k neighbours by cosine similarity (excluding self)."""
    sim = emb @ emb.T
    np.fill_diagonal(sim, -np.inf)
    k = min(k, len(emb) - 1)
    idx = np.argsort(-sim, axis=1)[:, :k]
    return idx, np.take_along_axis(sim, idx, axis=1)


def run(store: Store, cfg: SimilaritySettings, seasons: list[str]) -> dict[str, int]:
    """Build ``player_embeddings``, ``player_similar`` and ``player_percentiles`` for ``seasons``."""
    ps = store.read("player_season")
    p90 = per90_table(ps[ps["season_id"].isin(seasons)], cfg)
    emb_rows, sim_rows, pct_rows = [], [], []
    metrics = [*cfg.features, "xg", "goals"]
    for (season, group), g in p90.groupby(["season_id", "position_group"]):
        g = g.reset_index(drop=True)
        if len(g) < 2:
            continue
        emb = embed_group(g, cfg)
        idx, sim = nearest(emb, cfg.n_neighbours)
        for i, r in g.iterrows():
            emb_rows.append(
                {
                    "player_id": r["player_id"],
                    "season_id": season,
                    "league_id": r["league_id"],
                    "team_id": r["team_id"],
                    "position_group": group,
                    "minutes": int(r["minutes"]),
                    "age": r.get("age"),
                    "embedding": emb[i].round(6).tolist(),
                }
            )
            for rank, (j, s) in enumerate(zip(idx[i], sim[i], strict=True), start=1):
                sim_rows.append(
                    {
                        "player_id": r["player_id"],
                        "season_id": season,
                        "league_id": r["league_id"],
                        "rank": rank,
                        "other_player_id": g.loc[j, "player_id"],
                        "other_league_id": g.loc[j, "league_id"],
                        "similarity": round(float(s), 4),
                    }
                )
        pct = g[metrics].rank(pct=True) * 100
        for m in metrics:
            pct_rows.append(
                pd.DataFrame(
                    {
                        "player_id": g["player_id"],
                        "season_id": season,
                        "league_id": g["league_id"],
                        "position_group": group,
                        "metric": m,
                        "per90": g[m].round(4),
                        "percentile": pct[m].round(1),
                    }
                )
            )
    store.write("player_embeddings", pd.DataFrame(emb_rows))
    store.write("player_similar", pd.DataFrame(sim_rows))
    pct_df = pd.concat(pct_rows, ignore_index=True) if pct_rows else pd.DataFrame()
    store.write("player_percentiles", pct_df)
    return {"players": len(emb_rows), "similar_rows": len(sim_rows), "percentile_rows": len(pct_df)}
