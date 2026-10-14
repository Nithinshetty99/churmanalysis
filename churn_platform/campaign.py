"""Retention-campaign value model: who should we contact, given a budget?

Everything here rests on ASSUMPTIONS, not estimates from the data:
  save_rate    share of would-be churners a contact prevents
  cost         cost per contact
  horizon      months of future revenue protected when a customer is saved

The data is observational and has no campaign, so the true save rate (uplift) is unknowable here.
The model shows how targeting strategy changes value *given* a save rate, and how sensitive the
conclusion is to it. Treat output as a planning tool, not evidence that a campaign works.

Strategies are ranked by predicted risk or by expected revenue at risk (risk x MRR). Realized value
uses the actual test-period outcomes, which we have only because this is a backtest.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


DEFAULTS = {"save_rate": 0.15, "cost": 100.0, "horizon": 12}


def campaign_curves(scored: pd.DataFrame, save_rate: float = DEFAULTS["save_rate"], cost: float = DEFAULTS["cost"],
                    horizon: int = DEFAULTS["horizon"], seed: int = 0, points: int = 50) -> pd.DataFrame:
    """scored needs columns: risk, label, mrr. Returns net value for k contacted customers."""
    df = scored.reset_index(drop=True)
    n = len(df)
    value = df["mrr"].to_numpy() * horizon
    y = df["label"].to_numpy()
    order = {
        "by risk": np.argsort(-df["risk"].to_numpy()),
        "by expected revenue at risk": np.argsort(-(df["risk"] * value).to_numpy()),
        "random": np.random.default_rng(seed).permutation(n),
    }
    ks = np.unique(np.linspace(0, n, points).astype(int))
    rows = []
    for name, o in order.items():
        saved_value = np.concatenate([[0.0], np.cumsum(value[o] * y[o] * save_rate)])
        expected_value = np.concatenate([[0.0], np.cumsum(df["risk"].to_numpy()[o] * value[o] * save_rate)])
        for k in ks:
            rows.append({"strategy": name, "contacted": int(k), "pct_contacted": 100 * k / n,
                         "realized_net": saved_value[k] - cost * k,
                         "model_expected_net": expected_value[k] - cost * k})
    return pd.DataFrame(rows)


def best_point(curves: pd.DataFrame) -> pd.DataFrame:
    idx = curves.groupby("strategy")["realized_net"].idxmax()
    return curves.loc[idx, ["strategy", "contacted", "pct_contacted", "realized_net"]].reset_index(drop=True)


def sensitivity_grid(scored: pd.DataFrame, save_rates=(0.05, 0.10, 0.20, 0.30), costs=(50, 100, 200),
                     horizon: int = DEFAULTS["horizon"]) -> pd.DataFrame:
    """How the best targeting depth and value change with the (unknown) save rate and cost."""
    rows = []
    for s in save_rates:
        for c in costs:
            cu = campaign_curves(scored, save_rate=s, cost=c, horizon=horizon, points=101)
            ev = cu[cu["strategy"] == "by expected revenue at risk"].reset_index(drop=True)
            best = ev.loc[ev["realized_net"].idxmax()]
            rows.append({"save_rate": s, "cost": c,
                         "best_pct_contacted": round(best["pct_contacted"], 1),
                         "net_at_best": round(best["realized_net"]),
                         "net_contact_everyone": round(ev["realized_net"].iloc[-1])})
    return pd.DataFrame(rows)


def breakeven_save_rate(mrr_at_risk_per_contact: float, cost: float, horizon: int) -> float:
    """Save rate at which contacting a customer with this expected MRR-at-risk breaks even."""
    return cost / (mrr_at_risk_per_contact * horizon)
