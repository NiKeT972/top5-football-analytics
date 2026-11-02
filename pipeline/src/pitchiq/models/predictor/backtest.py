"""Walk-forward backtest of the match predictor against bookmaker closing odds.

Protocol (no information from the future is ever used):

* Dixon-Coles: one model per league, refitted every ``refit_every_days`` on matches
  strictly before the refit date, then used for the matches in that window.
* LightGBM: refitted at the start of each season on all earlier seasons. Its rolling-xG
  features come from the *backtest* xG model, trained only on seasons up to
  ``xg.backtest_train_last_season`` (before every backtest season).
* Ensemble: ``w * DC + (1 - w) * GBM``. The weight used for season S is the one that
  minimised log loss over the walk-forward seasons *before* S. The season before the
  first backtest season is walked forward only to seed that choice and is not reported.
* Bookmakers: closing odds (Pinnacle, else market average), margin removed with Shin's
  method. All models are scored on the same matches (those with closing odds).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from pitchiq.config import LeaguesConfig, Settings, previous_season
from pitchiq.evaluation import metrics as M
from pitchiq.evaluation.bookmaker import best_closing, implied_probs
from pitchiq.features.match_features import build_match_features, match_xg_from_shots
from pitchiq.models.predictor import dixon_coles as dc
from pitchiq.models.predictor import gbm
from pitchiq.storage.parquet import Store

log = logging.getLogger(__name__)
MODELS = ["dixon_coles", "gbm", "ensemble", "bookmaker"]
OUTCOMES = ["home", "draw", "away"]


def season_priors(lm: pd.DataFrame, season: str, prior: tuple[float, float]) -> tuple[list[str], dict]:
    """Teams of a league-season and priors for those promoted into it."""
    teams = sorted(set(lm.loc[lm["season_id"] == season, "home_team_id"]))
    prev_teams = set(lm.loc[lm["season_id"] == previous_season(season), "home_team_id"])
    return teams, {t: prior for t in teams if prev_teams and t not in prev_teams}


def dc_walk_forward(lm: pd.DataFrame, season: str, settings: Settings, prior: tuple[float, float]) -> pd.DataFrame:
    """Dixon-Coles predictions for every match of one league-season."""
    cfg = settings.predictor.dixon_coles
    teams, priors = season_priors(lm, season, prior)
    sm = lm[lm["season_id"] == season].sort_values("kickoff_utc")
    start = sm["kickoff_utc"].min().normalize()
    rows = []
    while start <= sm["kickoff_utc"].max():
        end = start + pd.Timedelta(days=cfg.refit_every_days)
        block = sm[(sm["kickoff_utc"] >= start) & (sm["kickoff_utc"] < end)]
        if not block.empty:
            f = dc.fit(lm, start, cfg, priors=priors, teams=teams)
            for r in block.itertuples():
                lam, mu = f.rates(r.home_team_id, r.away_team_id)
                p = dc.outcome_probs(dc.score_grid(lam, mu, f.rho, cfg.max_goals))
                rows.append({"match_id": r.match_id, "dc_h": p[0], "dc_d": p[1], "dc_a": p[2], "exp_home_goals": lam, "exp_away_goals": mu})
        start = end
    return pd.DataFrame(rows)


def _best_weight(df: pd.DataFrame, grid: list[float]) -> float:
    y = df["outcome"].to_numpy()
    dcp = df[["dc_h", "dc_d", "dc_a"]].to_numpy()
    gp = df[["gbm_h", "gbm_d", "gbm_a"]].to_numpy()
    return min(grid, key=lambda w: M.multi_log_loss(y, w * dcp + (1 - w) * gp))


def _scores(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    return {"n": len(y), "log_loss": M.multi_log_loss(y, p), "brier": M.multi_brier(y, p), "rps": M.rps(y, p)}


def run(store: Store, settings: Settings, leagues: LeaguesConfig, report_dir: Path) -> dict:
    """Run the full walk-forward backtest and write tables, artefacts and the report."""
    backtest = settings.seasons.backtest
    wf_seasons = [previous_season(backtest[0]), *backtest]
    matches = store.read("matches")
    matches["kickoff_utc"] = pd.to_datetime(matches["kickoff_utc"], utc=True)
    shots = store.read("shots").merge(store.read("shots_xg"), on="shot_id")
    feats = build_match_features(matches, match_xg_from_shots(shots, "xg_bt"), store.read("elo"), settings.predictor.gbm)

    dc_parts, priors_out = [], {}
    for lg in leagues.leagues:
        lm = matches[matches["league_id"] == lg.league_id]
        prior = dc.promoted_prior(lm[lm["season_id"] < wf_seasons[0]], settings.predictor.dixon_coles)
        priors_out[lg.league_id] = prior
        for season in wf_seasons:
            log.info("DC walk-forward %s %s", lg.league_id, season)
            dc_parts.append(dc_walk_forward(lm, season, settings, prior))
    dcp = pd.concat(dc_parts, ignore_index=True)

    gbm_parts = []
    for season in wf_seasons:
        model = gbm.fit(feats[feats["season_id"] < season], settings.predictor.gbm)
        rows = feats[(feats["season_id"] == season) & (feats["status"] == "finished")]
        p = gbm.predict(model, rows)
        gbm_parts.append(pd.DataFrame({"match_id": rows["match_id"].to_numpy(), "gbm_h": p[:, 0], "gbm_d": p[:, 1], "gbm_a": p[:, 2]}))
    gbp = pd.concat(gbm_parts, ignore_index=True)

    fin = matches[(matches["status"] == "finished") & matches["season_id"].isin(wf_seasons)]
    df = fin[["match_id", "league_id", "season_id", "kickoff_utc", "home_goals", "away_goals"]].merge(dcp, on="match_id").merge(gbp, on="match_id")
    df["outcome"] = M.outcome_index(df["home_goals"], df["away_goals"])
    book = implied_probs(best_closing(store.read("odds")))[["match_id", "bookmaker", "p_h", "p_d", "p_a", "overround"]]
    df = df.merge(book.rename(columns={"p_h": "bk_h", "p_d": "bk_d", "p_a": "bk_a", "bookmaker": "bk_source"}), on="match_id", how="left")

    grid = settings.predictor.ensemble_weight_grid
    weights = {}
    for i, season in enumerate(wf_seasons[1:], start=1):
        weights[season] = _best_weight(df[df["season_id"].isin(wf_seasons[:i])], grid)
        mask = df["season_id"] == season
        w = weights[season]
        for o in ("h", "d", "a"):
            df.loc[mask, f"ens_{o}"] = w * df.loc[mask, f"dc_{o}"] + (1 - w) * df.loc[mask, f"gbm_{o}"]
    production_weight = _best_weight(df, grid)

    ev = df[df["season_id"].isin(backtest) & df["bk_h"].notna()].copy()
    cols = {"dixon_coles": "dc", "gbm": "gbm", "ensemble": "ens", "bookmaker": "bk"}
    summary_rows, calib_rows = [], []
    for scope_name, groups in (("all", [("all", "all", ev)]), ("league_season", [(lg, s, g) for (lg, s), g in ev.groupby(["league_id", "season_id"])])):
        for lg, s, g in groups:
            y = g["outcome"].to_numpy()
            for model, c in cols.items():
                p = g[[f"{c}_h", f"{c}_d", f"{c}_a"]].to_numpy()
                summary_rows.append({"scope": scope_name, "league_id": lg, "season_id": s, "model": model, **_scores(y, p)})
    y = ev["outcome"].to_numpy()
    for model, c in cols.items():
        p = ev[[f"{c}_h", f"{c}_d", f"{c}_a"]].to_numpy()
        for k, name in enumerate(OUTCOMES):
            t = M.calibration_table((y == k).astype(int), p[:, k], settings.predictor.calibration_bins)
            calib_rows.append(t.assign(model=model, outcome=name))
    summary = pd.DataFrame(summary_rows)
    calib = pd.concat(calib_rows, ignore_index=True)

    store.write("backtest_predictions", df)
    store.write("backtest_summary", summary)
    store.write("backtest_calibration", calib)
    meta = {"ensemble_weight": production_weight, "season_weights": weights, "promoted_priors": priors_out,
            "backtest_seasons": backtest, "n_evaluated": len(ev), "n_without_odds": int(df[df["season_id"].isin(backtest)]["bk_h"].isna().sum())}
    store.write_json("predictor/meta.json", meta)
    _plot_calibration(calib, report_dir / "figures" / "predictor_calibration.png")
    (report_dir / "predictor_report.md").write_text(render_report(summary, meta), encoding="utf-8")
    return meta | {"summary": summary.query("scope == 'all'").to_dict("records")}


def _plot_calibration(calib: pd.DataFrame, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.3), sharey=True)
    for ax, outcome in zip(axes, OUTCOMES, strict=True):
        ax.plot([0, 1], [0, 1], ls="--", c="grey", lw=1)
        for model, g in calib[calib["outcome"] == outcome].groupby("model"):
            g = g[g["n"] >= 20]
            ax.plot(g["mean_pred"], g["obs_freq"], marker="o", ms=3, label=model)
        ax.set(title=f"P({outcome})", xlabel="predicted", xlim=(0, 1), ylim=(0, 1))
    axes[0].set_ylabel("observed")
    axes[0].legend()
    fig.suptitle("Match predictor calibration, walk-forward backtest")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def render_report(summary: pd.DataFrame, meta: dict) -> str:
    """Markdown report."""
    overall = summary[summary["scope"] == "all"].sort_values("log_loss")
    lines = [
        "# Match predictor: walk-forward backtest",
        "",
        f"Seasons {', '.join(meta['backtest_seasons'])}, all five leagues, {meta['n_evaluated']:,} matches with closing odds "
        f"({meta['n_without_odds']} matches without odds excluded from every model's score). Lower is better for all metrics.",
        "",
        "| model | matches | log loss | Brier | RPS |",
        "|---|---|---|---|---|",
    ]
    lines += [f"| {r.model} | {r.n:,} | {r.log_loss:.4f} | {r.brier:.4f} | {r.rps:.4f} |" for r in overall.itertuples()]
    lines += [
        "",
        f"Ensemble weight on Dixon-Coles (chosen on earlier seasons only): {meta['season_weights']}; production weight {meta['ensemble_weight']}.",
        "",
        "## By league and season (RPS)",
        "",
    ]
    piv = summary[summary["scope"] == "league_season"].pivot_table(index=["league_id", "season_id"], columns="model", values="rps")
    lines += [piv.round(4).to_markdown(), "", "![calibration](figures/predictor_calibration.png)", ""]
    return "\n".join(lines)
