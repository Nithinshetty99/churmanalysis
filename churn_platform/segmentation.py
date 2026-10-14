"""Segment the current customer base with k-means on behavior and value features.

Segments are descriptive groupings, not causal types. Cluster count is chosen by silhouette score
within 3..6 and the profile table reports each cluster's mean features and mean model risk.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.impute import SimpleImputer
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

SEG_FEATURES = ["tenure_months", "usage_3m_avg", "mrr", "tickets_3m", "usage_vs_lifetime"]


def segment(df: pd.DataFrame, k_range=range(3, 7), seed: int = 0):
    """Return (df with 'segment' column, profile table, silhouette scores by k)."""
    X = SimpleImputer(strategy="median").fit_transform(df[SEG_FEATURES])
    X = StandardScaler().fit_transform(X)
    rng = np.random.default_rng(seed)
    sample = rng.choice(len(X), size=min(3000, len(X)), replace=False)
    scores = {}
    for k in k_range:
        labels = KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(X[sample])
        scores[k] = float(silhouette_score(X[sample], labels))
    best_k = max(scores, key=scores.get)
    out = df.copy()
    out["segment"] = KMeans(n_clusters=best_k, n_init=10, random_state=seed).fit_predict(X)
    prof = out.groupby("segment").agg(
        customers=("customer_id", "size"),
        tenure_months=("tenure_months", "mean"),
        usage_3m_avg=("usage_3m_avg", "mean"),
        mrr=("mrr", "mean"),
        tickets_3m=("tickets_3m", "mean"),
        usage_vs_lifetime=("usage_vs_lifetime", "mean"),
        **({"mean_risk": ("risk", "mean")} if "risk" in out else {}),
    ).round(3).reset_index()
    prof["share_pct"] = (100 * prof["customers"] / prof["customers"].sum()).round(1)
    return out, prof, scores
