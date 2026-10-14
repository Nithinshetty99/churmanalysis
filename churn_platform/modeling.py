"""Churn prediction with a strict temporal split.

Task: for each customer active at the end of a snapshot month, predict whether they churn within
the next 3 months, using only information available at that snapshot (built in sql/06_features.sql).

Split (see config.py): train on earlier snapshots, choose hyperparameters on VAL_SNAP, report once
on TEST_SNAP. No random splitting: random splits would leak a customer's future into training.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .db import run

NUM = ["tenure_months", "age", "mrr", "price_vs_base", "usage_3m_avg", "usage_trend",
       "usage_vs_lifetime", "sessions_3m", "tickets_3m", "failed_3m"]
CAT = ["plan", "contract", "channel", "location"]
BASELINE_NUM, BASELINE_CAT = ["tenure_months"], ["contract"]


def build_snapshots(con, queries, snaps) -> pd.DataFrame:
    return pd.concat([run(con, queries, "snapshot_features", snap=s) for s in snaps], ignore_index=True)


def make_model(kind: str, num=None, cat=None, **gbm_kwargs) -> Pipeline:
    num = NUM if num is None else num
    cat = CAT if cat is None else cat
    pre = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median", add_indicator=True)),
                          ("sc", StandardScaler())]), num),
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat),
    ])
    if kind == "logit":
        clf = LogisticRegression(max_iter=1000, C=1.0)
    elif kind == "gbm":
        params = dict(max_depth=3, learning_rate=0.05, max_iter=250, l2_regularization=1.0,
                      early_stopping=False, random_state=0)
        params.update(gbm_kwargs)
        clf = HistGradientBoostingClassifier(**params)
    else:
        raise ValueError(kind)
    return Pipeline([("pre", pre), ("clf", clf)])


def features_of(df: pd.DataFrame, num, cat) -> pd.DataFrame:
    return df[list(num) + list(cat)]


def evaluate(y, p) -> dict:
    y, p = np.asarray(y), np.asarray(p)
    order = np.argsort(-p)
    k10 = max(int(round(0.10 * len(y))), 1)
    k20 = max(int(round(0.20 * len(y))), 1)
    base = y.mean()
    return {
        "roc_auc": roc_auc_score(y, p),
        "pr_auc": average_precision_score(y, p),
        "brier": brier_score_loss(y, p),
        "brier_skill": 1 - brier_score_loss(y, p) / (base * (1 - base)),  # vs predicting the base rate
        "log_loss": log_loss(y, np.clip(p, 1e-6, 1 - 1e-6)),
        "lift_top10": y[order[:k10]].mean() / base,
        "recall_top10": y[order[:k10]].sum() / y.sum(),
        "recall_top20": y[order[:k20]].sum() / y.sum(),
        "base_rate": base,
        "n": len(y),
    }


def calibration_table(y, p, bins: int = 10) -> pd.DataFrame:
    df = pd.DataFrame({"y": np.asarray(y), "p": np.asarray(p)})
    df["bin"] = pd.qcut(df["p"], bins, labels=False, duplicates="drop")
    out = df.groupby("bin").agg(customers=("y", "size"), mean_predicted=("p", "mean"), observed_rate=("y", "mean")).reset_index()
    return out


def lift_table(y, p, bins: int = 10) -> pd.DataFrame:
    df = pd.DataFrame({"y": np.asarray(y), "p": np.asarray(p)}).sort_values("p", ascending=False).reset_index(drop=True)
    df["decile"] = (np.arange(len(df)) * bins // len(df)) + 1
    g = df.groupby("decile").agg(customers=("y", "size"), churners=("y", "sum"), mean_risk=("p", "mean")).reset_index()
    g["churn_rate"] = g["churners"] / g["customers"]
    g["lift"] = g["churn_rate"] / df["y"].mean()
    g["cum_capture"] = g["churners"].cumsum() / df["y"].sum()
    return g


@dataclass
class ModelRun:
    name: str
    model: Pipeline
    val_metrics: dict
    test_metrics: dict


def fit_and_compare(train: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame):
    """Fit baseline, logistic regression, and a small GBM grid; select GBM config on validation."""
    runs: list[ModelRun] = []

    def fit(name, kind, num, cat, **kw):
        m = make_model(kind, num, cat, **kw)
        m.fit(features_of(train, num, cat), train["label"])
        pv = m.predict_proba(features_of(val, num, cat))[:, 1]
        pt = m.predict_proba(features_of(test, num, cat))[:, 1]
        return ModelRun(name, m, evaluate(val["label"], pv), evaluate(test["label"], pt))

    runs.append(fit("baseline (tenure + contract)", "logit", BASELINE_NUM, BASELINE_CAT))
    runs.append(fit("logistic regression (all features)", "logit", NUM, CAT))

    grid = [dict(max_depth=d, learning_rate=lr) for d in (2, 3, 4) for lr in (0.03, 0.08)]
    gbm_runs = [fit("gbm", "gbm", NUM, CAT, **g) for g in grid]
    best_i = int(np.argmax([r.val_metrics["roc_auc"] for r in gbm_runs]))
    best = gbm_runs[best_i]
    best.name = f"gradient boosting (depth={grid[best_i]['max_depth']}, lr={grid[best_i]['learning_rate']})"
    runs.append(best)
    return runs, grid[best_i]


def importance_table(model: Pipeline, test: pd.DataFrame, num=NUM, cat=CAT, n_repeats: int = 8) -> pd.DataFrame:
    X, y = features_of(test, num, cat), test["label"]
    r = permutation_importance(model, X, y, scoring="roc_auc", n_repeats=n_repeats, random_state=0)
    return (pd.DataFrame({"feature": X.columns, "auc_drop": r.importances_mean, "std": r.importances_std})
            .sort_values("auc_drop", ascending=False).reset_index(drop=True))


def logit_coefficients(model: Pipeline) -> pd.DataFrame:
    names = model.named_steps["pre"].get_feature_names_out()
    coef = model.named_steps["clf"].coef_[0]
    return pd.DataFrame({"feature": names, "coefficient": coef}).sort_values("coefficient", key=abs, ascending=False)
