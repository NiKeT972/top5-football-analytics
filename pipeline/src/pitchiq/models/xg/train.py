"""Train, evaluate and apply the xG model.

* Baseline: logistic regression on geometry + one-hot categories.
* Main model: LightGBM with native categorical features, early-stopped on the last
  training season.
* Penalties are not modelled: they get a constant, the empirical conversion rate of
  penalties in the training seasons. Own goals are not shots and get no xG.
* Evaluation on held-out seasons (never seen in training) against Understat's own xG.
* Two fitted copies are kept: ``production`` (all seasons, used for the site) and
  ``backtest`` (seasons up to ``backtest_train_last_season`` only, used to build
  leak-free features for the match-predictor backtest).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from pitchiq.config import Settings, XGSettings
from pitchiq.evaluation import metrics as M
from pitchiq.models.xg.features import (
    CATEGORICAL,
    GOAL,
    NUMERIC,
    OWN_GOAL,
    PENALTY,
    build_features,
    frequent_categories,
)
from pitchiq.storage.parquet import Store

log = logging.getLogger(__name__)
LR_NUMERIC = [c for c in NUMERIC if c != "minute"]
SHAP_SAMPLE = 20000
LR_MAX_ITER = 2000


@dataclass
class XGModel:
    """A fitted xG model plus everything needed to apply it to new shots."""

    kind: str
    estimator: object
    last_actions: list[str]
    penalty_xg: float
    cfg: XGSettings
    trained_seasons: list[str] = field(default_factory=list)

    def predict(self, shots: pd.DataFrame) -> np.ndarray:
        """XG per shot (penalties get the constant; own goals get NaN)."""
        out = np.full(len(shots), np.nan)
        pen = (shots["situation"] == PENALTY).to_numpy()
        own = (shots["result"] == OWN_GOAL).to_numpy()
        np_mask = ~pen & ~own
        out[pen] = self.penalty_xg
        if np_mask.any():
            X = build_features(shots[np_mask], self.cfg, self.last_actions)
            cols = LR_NUMERIC + CATEGORICAL if self.kind == "logreg" else NUMERIC + CATEGORICAL
            out[np_mask] = self.estimator.predict_proba(X[cols])[:, 1]
        return out

    def save(self, path: Path) -> None:
        """Persist with joblib."""
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @staticmethod
    def load(path: Path) -> XGModel:
        """Load a saved model."""
        return joblib.load(path)


def _logreg(seed: int) -> Pipeline:
    pre = ColumnTransformer(
        [
            ("num", StandardScaler(), LR_NUMERIC),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
        ]
    )
    return Pipeline(
        [("pre", pre), ("lr", LogisticRegression(max_iter=LR_MAX_ITER, random_state=seed))]
    )


def _lgbm(cfg: XGSettings, n_estimators: int | None = None) -> lgb.LGBMClassifier:
    params = {k: v for k, v in cfg.lgbm.items() if k != "early_stopping_rounds"}
    if n_estimators is not None:
        params["n_estimators"] = n_estimators
    return lgb.LGBMClassifier(
        objective="binary", random_state=cfg.random_seed, verbose=-1, **params
    )


def load_shots(store: Store) -> pd.DataFrame:
    """Shots joined to their season, excluding own goals (not shots)."""
    shots = store.read("shots")
    seasons = store.read("matches")[["match_id", "season_id", "league_id"]]
    return shots.merge(seasons, on="match_id", how="left")


def fit(
    shots: pd.DataFrame,
    cfg: XGSettings,
    kind: str,
    n_estimators: int | None = None,
    val: pd.DataFrame | None = None,
) -> tuple[XGModel, int | None]:
    """Fit one model on ``shots`` (penalties/own goals are handled outside the estimator)."""
    real = shots[shots["result"] != OWN_GOAL]
    pen = real[real["situation"] == PENALTY]
    penalty_xg = float((pen["result"] == GOAL).mean()) if len(pen) else 0.0
    np_shots = real[real["situation"] != PENALTY]
    last_actions = frequent_categories(
        np_shots["last_action"].fillna("None"), cfg.min_category_count
    )
    X = build_features(np_shots, cfg, last_actions)
    y = (np_shots["result"] == GOAL).astype(int).to_numpy()
    best_iter = None
    if kind == "logreg":
        est = _logreg(cfg.random_seed).fit(X[LR_NUMERIC + CATEGORICAL], y)
    else:
        est = _lgbm(cfg, n_estimators)
        fit_kwargs = {}
        if val is not None:
            v = val[(val["result"] != OWN_GOAL) & (val["situation"] != PENALTY)]
            Xv = build_features(v, cfg, last_actions)
            fit_kwargs = {
                "eval_set": [(Xv[NUMERIC + CATEGORICAL], (v["result"] == GOAL).astype(int))],
                "callbacks": [lgb.early_stopping(cfg.lgbm["early_stopping_rounds"], verbose=False)],
            }
        est.fit(X[NUMERIC + CATEGORICAL], y, **fit_kwargs)
        best_iter = (
            int(est.best_iteration_) if val is not None and est.best_iteration_ else n_estimators
        )
    seasons = sorted(shots["season_id"].dropna().unique().tolist())
    return XGModel(kind, est, last_actions, penalty_xg, cfg, seasons), best_iter


def _score_block(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    return {
        "n": len(y),
        "log_loss": M.binary_log_loss(y, p),
        "brier": M.binary_brier(y, p),
        "auc": M.auc(y, p),
        "mean_pred": float(np.mean(p)),
        "goal_rate": float(np.mean(y)),
    }


def evaluate(settings: Settings, store: Store, report_dir: Path) -> dict:
    """Train on early seasons, evaluate on held-out seasons, then fit production + backtest models."""
    cfg = settings.xg
    shots = load_shots(store)
    holdout = cfg.holdout_seasons
    train = shots[shots["season_id"] < min(holdout)]
    test = shots[shots["season_id"].isin(holdout) & (shots["result"] != OWN_GOAL)]
    val_season = train["season_id"].max()
    log.info("xG: %d train shots, %d test shots, val season %s", len(train), len(test), val_season)

    lr, _ = fit(train, cfg, "logreg")
    _, best_iter = fit(
        train[train["season_id"] < val_season],
        cfg,
        "lgbm",
        val=train[train["season_id"] == val_season],
    )
    gbm, _ = fit(train, cfg, "lgbm", n_estimators=best_iter)

    y = (test["result"] == GOAL).astype(int).to_numpy()
    is_np = (test["situation"] != PENALTY).to_numpy()
    preds = {
        "Logistic regression": lr.predict(test),
        "LightGBM": gbm.predict(test),
        "Understat xG": test["xg_us"].to_numpy(float),
    }
    results = {
        name: {"all_shots": _score_block(y, p), "non_penalty": _score_block(y[is_np], p[is_np])}
        for name, p in preds.items()
    }

    by_situation = []
    for sit, idx in test.groupby("situation").indices.items():
        row = {"situation": sit, "n": len(idx), "goal_rate": float(y[idx].mean())}
        for name, p in preds.items():
            row[name] = M.binary_log_loss(y[idx], p[idx])
        by_situation.append(row)

    calib = {name: M.calibration_table(y, p, cfg.calibration_bins) for name, p in preds.items()}
    shap_importance = _shap(gbm, test[is_np], report_dir)
    _plot_calibration(calib, report_dir / "figures" / "xg_calibration.png")

    best_name = min(
        ("Logistic regression", "LightGBM"), key=lambda n: results[n]["all_shots"]["log_loss"]
    )
    best_kind = "lgbm" if best_name == "LightGBM" else "logreg"
    production, _ = fit(shots, cfg, best_kind, n_estimators=best_iter)
    backtest, _ = fit(
        shots[shots["season_id"] <= cfg.backtest_train_last_season],
        cfg,
        best_kind,
        n_estimators=best_iter,
    )
    production.save(store.artifacts / "xg" / "production.joblib")
    backtest.save(store.artifacts / "xg" / "backtest.joblib")

    summary = {
        "holdout_seasons": holdout,
        "train_seasons": sorted(train["season_id"].unique().tolist()),
        "n_train": len(train),
        "n_test": len(test),
        "lgbm_best_iteration": best_iter,
        "penalty_xg": production.penalty_xg,
        "chosen_model": best_name,
        "results": results,
        "by_situation": by_situation,
        "shap_mean_abs": shap_importance,
        "calibration": {k: v.to_dict("records") for k, v in calib.items()},
    }
    store.write_json("xg/metrics.json", summary)
    (report_dir / "xg_report.md").write_text(render_report(summary), encoding="utf-8")
    return summary


def score_all(store: Store) -> pd.DataFrame:
    """Apply the saved production and backtest models to every shot; writes ``shots_xg``."""
    prod = XGModel.load(store.artifacts / "xg" / "production.joblib")
    bt = XGModel.load(store.artifacts / "xg" / "backtest.joblib")
    shots = load_shots(store)
    out = pd.DataFrame(
        {"shot_id": shots["shot_id"], "xg": prod.predict(shots), "xg_bt": bt.predict(shots)}
    )
    store.write("shots_xg", out)
    return out


def _shap(model: XGModel, shots: pd.DataFrame, report_dir: Path) -> dict[str, float]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import shap

    sample = shots.sample(min(SHAP_SAMPLE, len(shots)), random_state=model.cfg.random_seed)
    X = build_features(sample, model.cfg, model.last_actions)[NUMERIC + CATEGORICAL]
    if model.kind != "lgbm":
        return {}
    values = shap.TreeExplainer(model.estimator).shap_values(X)
    values = values[1] if isinstance(values, list) else values
    importance = dict(
        sorted(
            zip(X.columns, np.abs(values).mean(axis=0).round(4).tolist(), strict=True),
            key=lambda kv: -kv[1],
        )
    )
    fig_dir = report_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    plt.figure()
    shap.summary_plot(values, X, show=False, max_display=len(X.columns))
    plt.title("xG model: SHAP values (held-out non-penalty shots)")
    plt.tight_layout()
    plt.savefig(fig_dir / "xg_shap.png", dpi=130)
    plt.close("all")
    return importance


def _plot_calibration(calib: dict[str, pd.DataFrame], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(5.5, 5))
    ax.plot([0, 1], [0, 1], ls="--", c="grey", lw=1, label="perfect")
    for name, df in calib.items():
        ax.plot(df["mean_pred"], df["obs_freq"], marker="o", ms=3, label=name)
    ax.set(
        xlabel="Predicted xG",
        ylabel="Observed goal rate",
        title="xG calibration (held-out seasons)",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def render_report(s: dict) -> str:
    """Markdown report for the repo."""
    lines = [
        "# xG model report",
        "",
        f"Trained on seasons {', '.join(s['train_seasons'])} ({s['n_train']:,} shots); "
        f"evaluated on held-out seasons {', '.join(s['holdout_seasons'])} ({s['n_test']:,} shots, own goals excluded).",
        f"Chosen model: **{s['chosen_model']}** (LightGBM best iteration {s['lgbm_best_iteration']}). "
        f"Penalty xG (empirical conversion): **{s['penalty_xg']:.3f}**.",
        "",
        "## Held-out performance",
        "",
        "| model | shots | log loss | Brier | ROC-AUC | mean xG | goal rate |",
        "|---|---|---|---|---|---|---|",
    ]
    for scope in ("all_shots", "non_penalty"):
        for name, r in s["results"].items():
            b = r[scope]
            lines.append(
                f"| {name} ({scope.replace('_', ' ')}) | {b['n']:,} | {b['log_loss']:.4f} | {b['brier']:.4f} | "
                f"{b['auc']:.4f} | {b['mean_pred']:.4f} | {b['goal_rate']:.4f} |"
            )
    lines += [
        "",
        "## Log loss by situation",
        "",
        "| situation | shots | goal rate | " + " | ".join(s["results"]) + " |",
        "|---" * (3 + len(s["results"])) + "|",
    ]
    for row in s["by_situation"]:
        lines.append(
            f"| {row['situation']} | {row['n']:,} | {row['goal_rate']:.3f} | "
            + " | ".join(f"{row[n]:.4f}" for n in s["results"])
            + " |"
        )
    if s["shap_mean_abs"]:
        lines += [
            "",
            "## Feature importance (mean |SHAP|, log-odds)",
            "",
            "| feature | mean abs SHAP |",
            "|---|---|",
        ]
        lines += [f"| {k} | {v:.4f} |" for k, v in s["shap_mean_abs"].items()]
    lines += [
        "",
        "![calibration](figures/xg_calibration.png)",
        "",
        "![shap](figures/xg_shap.png)",
        "",
    ]
    return "\n".join(lines)
