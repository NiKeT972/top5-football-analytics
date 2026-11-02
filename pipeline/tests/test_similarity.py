import numpy as np
import pandas as pd

from pitchiq.config import load_settings
from pitchiq.models import similarity
from pitchiq.storage.parquet import Store


def synthetic_player_season(n=60, seed=0):
    rng = np.random.default_rng(seed)
    groups = np.array(["FW", "CM", "DEF", "GK"])[rng.integers(0, 4, n)]
    minutes = rng.integers(500, 3000, n)
    base = {"FW": 0.5, "CM": 0.15, "DEF": 0.05, "GK": 0.0}
    rows = []
    for i in range(n):
        scale = minutes[i] / 90
        lvl = base[groups[i]] * rng.uniform(0.5, 1.5)
        rows.append(
            {
                "player_id": i,
                "season_id": "2526",
                "league_id": "ENG1",
                "team_id": "t",
                "position_group": groups[i],
                "minutes": int(minutes[i]),
                "npxg": lvl * scale,
                "xa": lvl / 2 * scale,
                "shots": 4 * lvl * scale + 1,
                "key_passes": rng.uniform(0.3, 2) * scale,
                "xg_chain": rng.uniform(0.1, 0.8) * scale,
                "xg_buildup": rng.uniform(0.05, 0.4) * scale,
                "np_goals": int(lvl * scale),
                "assists": int(lvl / 3 * scale),
                "xg": lvl * scale * 1.1,
                "goals": int(lvl * scale * 1.1),
                "age": 25.0,
            }
        )
    return pd.DataFrame(rows)


def test_similarity_within_group_only(tmp_path):
    cfg = load_settings().similarity
    store = Store(tmp_path)
    ps = synthetic_player_season()
    store.write("player_season", ps)
    stats = similarity.run(store, cfg, ["2526"])
    assert stats["players"] > 0
    emb = store.read("player_embeddings")
    assert "GK" not in set(emb["position_group"]) and (emb["minutes"] >= cfg.min_minutes).all()
    assert np.allclose([np.linalg.norm(e) for e in emb["embedding"]], 1.0)
    sim = store.read("player_similar")
    group = emb.set_index("player_id")["position_group"]
    assert (sim["player_id"].map(group) == sim["other_player_id"].map(group)).all()
    assert (sim["player_id"] != sim["other_player_id"]).all()
    pct = store.read("player_percentiles")
    assert pct["percentile"].between(0, 100).all()


def test_nearest_finds_identical_vector():
    emb = np.array([[1.0, 0, 0], [0.99, 0.141, 0], [0, 1.0, 0]])
    emb = emb / np.linalg.norm(emb, axis=1, keepdims=True)
    idx, sim = similarity.nearest(emb, 1)
    assert idx[0, 0] == 1 and idx[1, 0] == 0
