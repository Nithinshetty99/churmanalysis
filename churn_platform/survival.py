"""Kaplan-Meier survival curves and a multi-group log-rank test, implemented from scratch.

Time is measured in whole months observed. A churned customer with observed_months = m has an
event at time m; an active customer is censored at m (still a customer when observation ended).
Censoring is why "% ever churned" is the wrong summary: a customer who joined last month has had
almost no chance to churn yet.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def kaplan_meier(durations, events, z: float = 1.96) -> pd.DataFrame:
    """Return DataFrame[time, at_risk, events, survival, ci_low, ci_high] for t = 0..max.

    The confidence band uses the log(-log S) transform with Greenwood's variance.
    """
    d = np.asarray(durations, dtype=int)
    e = np.asarray(events, dtype=int)
    tmax = int(d.max())
    ev = np.bincount(d[e == 1], minlength=tmax + 1).astype(float)
    ce = np.bincount(d[e == 0], minlength=tmax + 1).astype(float)
    # at_risk[t] = number with duration >= t
    at_risk = len(d) - np.concatenate([[0.0], np.cumsum(ev + ce)[:-1]])
    with np.errstate(divide="ignore", invalid="ignore"):
        step = np.where(at_risk > 0, 1 - ev / at_risk, 1.0)
        surv = np.cumprod(step)
        green = np.cumsum(np.where((at_risk > 0) & (at_risk > ev), ev / (at_risk * (at_risk - ev)), 0.0))
        loglog_se = np.where((surv > 0) & (surv < 1), np.sqrt(green) / np.abs(np.log(surv)), np.nan)
        lo = surv ** np.exp(z * loglog_se)
        hi = surv ** np.exp(-z * loglog_se)
    lo = np.where(np.isnan(lo), surv, lo)
    hi = np.where(np.isnan(hi), surv, hi)
    return pd.DataFrame({"time": np.arange(tmax + 1), "at_risk": at_risk.astype(int),
                         "events": ev.astype(int), "survival": surv, "ci_low": lo, "ci_high": hi})


def survival_at(km: pd.DataFrame, t: int) -> float:
    t = min(t, int(km["time"].max()))
    return float(km.loc[km["time"] == t, "survival"].iloc[0])


def logrank_test(durations, events, groups) -> dict:
    """Multi-group log-rank test. Returns chi-square statistic, df, p-value."""
    d = np.asarray(durations, dtype=int)
    e = np.asarray(events, dtype=int)
    g = pd.Categorical(np.asarray(groups))
    K = len(g.categories)
    codes = np.asarray(g.codes)
    tmax = int(d.max())
    ev = np.zeros((K, tmax + 1))
    n_ge = np.zeros((K, tmax + 1))
    for k in range(K):
        dk, ek = d[codes == k], e[codes == k]
        ev[k] = np.bincount(dk[ek == 1], minlength=tmax + 1)
        n_ge[k] = (len(dk) - np.concatenate([[0], np.cumsum(np.bincount(dk, minlength=tmax + 1))[:-1]]))
    n_tot = n_ge.sum(axis=0)
    d_tot = ev.sum(axis=0)
    mask = (n_tot > 1) & (d_tot > 0)
    O = ev[:, mask].sum(axis=1)
    E = (n_ge[:, mask] * (d_tot[mask] / n_tot[mask])).sum(axis=1)
    V = np.zeros((K, K))
    for t in np.flatnonzero(mask):
        nt, dt = n_tot[t], d_tot[t]
        f = dt * (nt - dt) / (nt**2 * (nt - 1))
        for i in range(K):
            for j in range(K):
                V[i, j] += f * n_ge[i, t] * ((nt if i == j else 0) - n_ge[j, t])
    diff = (O - E)[:-1]
    chi2 = float(diff @ np.linalg.solve(V[:-1, :-1], diff))
    return {"chi2": chi2, "df": K - 1, "p_value": float(stats.chi2.sf(chi2, K - 1)),
            "groups": list(g.categories), "observed": O.tolist(), "expected": E.tolist()}
