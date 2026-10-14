"""Did the 2025-07 price increase raise churn? A difference-in-differences (DiD) estimate.

Design: Standard and Premium customers (treated) got +10%; Basic customers (control) did not.
Outcome: monthly churn rate. Compare the change from the pre-period to the post-period between
the groups.  DiD = (post_T - pre_T) - (post_C - pre_C), in percentage points of monthly churn.

Identification relies on PARALLEL TRENDS: without the hike, both groups would have moved together.
That is untestable after the fact; we check pre-period trends as a plausibility test only.
Plan was not randomized, so customers who chose Basic may differ from those who chose Standard or
Premium in ways that change how their churn moves over time. A DiD estimate is therefore evidence
about the hike, not proof, and the CI covers sampling error only, not violations of the assumption.

Because the data are simulated, the true effect is known (ground_truth.json) and we compare to it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import END_IDX, PRICE_HIKE_IDX


def _customer_level(months: pd.DataFrame, plan: pd.Series, pre, post) -> pd.DataFrame:
    m = months.merge(plan.rename("plan"), left_on="customer_id", right_index=True)
    m["treated"] = (m["plan"] != "Basic").astype(int)
    m = m[m["month_idx"].between(pre[0], post[1])]
    m["period"] = np.where(m["month_idx"] <= pre[1], "pre", "post")
    g = m.groupby(["customer_id", "treated", "period"]).agg(events=("churned_this_month", "sum"),
                                                           exposure=("churned_this_month", "size")).reset_index()
    return g


def did_estimate(months: pd.DataFrame, customers: pd.DataFrame, window: int = 6, n_boot: int = 400, seed: int = 0) -> dict:
    pre = (PRICE_HIKE_IDX - window, PRICE_HIKE_IDX - 1)
    post = (PRICE_HIKE_IDX, min(PRICE_HIKE_IDX + window - 1, END_IDX))
    g = _customer_level(months, customers.set_index("customer_id")["plan"], pre, (post[0], post[1]))
    cust_ids = g["customer_id"].unique()
    pos = {c: i for i, c in enumerate(cust_ids)}
    g["i"] = g["customer_id"].map(pos)
    # arrays [customer, 4] = events/exposure for (control_pre, control_post, treated_pre, treated_post)
    col = (g["treated"] * 2 + (g["period"] == "post").astype(int)).to_numpy()
    ev = np.zeros((len(cust_ids), 4)); ex = np.zeros((len(cust_ids), 4))
    np.add.at(ev, (g["i"].to_numpy(), col), g["events"].to_numpy())
    np.add.at(ex, (g["i"].to_numpy(), col), g["exposure"].to_numpy())

    def did(e, x):
        r = e.sum(0) / np.maximum(x.sum(0), 1)
        return 100 * ((r[3] - r[2]) - (r[1] - r[0])), 100 * r

    est, rates = did(ev, ex)
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    for b in range(n_boot):
        s = rng.integers(0, len(cust_ids), len(cust_ids))   # cluster bootstrap over customers
        boots[b] = did(ev[s], ex[s])[0]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {"did_pp": float(est), "ci_low": float(lo), "ci_high": float(hi),
            "rates_pct": {"control_pre": rates[0], "control_post": rates[1],
                          "treated_pre": rates[2], "treated_post": rates[3]},
            "pre_window": pre, "post_window": post}


def event_study(months: pd.DataFrame, customers: pd.DataFrame, first: int = 18) -> pd.DataFrame:
    """Monthly churn rate (%) for treated and control groups, with the gap between them."""
    m = months.merge(customers[["customer_id", "plan"]], on="customer_id")
    m = m[m["month_idx"] >= first]
    m["group"] = np.where(m["plan"] == "Basic", "control (Basic)", "treated (Standard/Premium)")
    t = m.groupby(["month_idx", "group"])["churned_this_month"].mean().mul(100).unstack("group")
    t["gap_pp"] = t["treated (Standard/Premium)"] - t["control (Basic)"]
    return t.reset_index()


def pretrend_slope_gap(es: pd.DataFrame, last_pre: int = PRICE_HIKE_IDX - 1) -> dict:
    """Linear trend of the treated-minus-control gap before the hike (pp per month)."""
    pre = es[es["month_idx"] <= last_pre]
    slope, intercept = np.polyfit(pre["month_idx"], pre["gap_pp"], 1)
    resid = pre["gap_pp"] - (slope * pre["month_idx"] + intercept)
    se = np.sqrt((resid**2).sum() / (len(pre) - 2) / ((pre["month_idx"] - pre["month_idx"].mean()) ** 2).sum())
    return {"slope_pp_per_month": float(slope), "se": float(se), "n_months": int(len(pre))}
