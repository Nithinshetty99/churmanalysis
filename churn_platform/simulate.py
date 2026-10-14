"""Simulate a subscription business with a documented, known churn mechanism.

WHY SIMULATE: the earlier notebook set churn with if-statements, so its "findings" were circular.
Here churn comes from a monthly hazard model with known coefficients (TRUE_PARAMS). That lets us
check whether the pipeline can recover real drivers, and measure estimation error against truth.
It does NOT tell us anything about real customers.

Mechanism (per customer, per active month):
  logit(P(churn this month)) = intercept
      + early_life * exp(-tenure/3)            new customers leave more often
      + annual_contract                        annual contracts are stickier ...
      + annual_renewal_month                   ... except in renewal months (tenure 12, 24, ...)
      + plan + channel + location + age effects
      + price_hike  (Standard/Premium after 2025-07)
      + dissatisfaction * s_t                  LATENT, never written to the data
      + failed_payment * failed_t

The latent dissatisfaction s_t (AR(1)) also lowers usage and raises tickets and failed payments,
so usage drops and tickets PREDICT churn but are symptoms, not causes. This mirrors real data
where behavior is a noisy proxy for an unobserved state.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DATA_DIR, END_IDX, LAST_SIGNUP_IDX, PRICE_HIKE_IDX, month_label

PLAN_PRICE = {"Basic": 299, "Standard": 599, "Premium": 999}
PLAN_USAGE = {"Basic": 25.0, "Standard": 40.0, "Premium": 60.0}   # mean monthly hours
LOCATIONS = ["Urban", "Semi-Urban", "Rural"]
CHANNELS = ["Organic", "Paid Search", "Referral", "Social"]
RHO = 0.85                      # persistence of dissatisfaction
SIG = float(np.sqrt(1 - RHO**2))  # keeps its variance at 1

TRUE_PARAMS = {
    "intercept": -4.0,
    "early_life": 1.2,
    "annual_contract": -1.3,
    "annual_renewal_month": 3.0,
    "plan": {"Basic": 0.0, "Standard": -0.1, "Premium": -0.2},
    "price_hike": 0.5,
    "dissatisfaction": 0.9,
    "failed_payment": 0.7,
    "channel": {"Organic": 0.0, "Paid Search": 0.2, "Referral": -0.3, "Social": 0.25},
    "location": {"Urban": 0.15, "Semi-Urban": 0.05, "Rural": 0.0},
    "age_per_year": -0.015,
}


@dataclass(frozen=True)
class SimConfig:
    n_customers: int = 10_000
    seed: int = 42


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def simulate(cfg: SimConfig | None = None):
    """Return (customers, customer_months, truth)."""
    cfg = cfg or SimConfig()
    P = TRUE_PARAMS
    rng = np.random.default_rng(cfg.seed)
    n, T = cfg.n_customers, END_IDX + 1

    # signups grow over time
    w = np.linspace(1.0, 2.2, LAST_SIGNUP_IDX + 1)
    signup = rng.choice(LAST_SIGNUP_IDX + 1, n, p=w / w.sum())
    age = np.clip(np.round(rng.normal(38, 12, n)), 18, 70).astype(int)
    location = rng.choice(LOCATIONS, n, p=[0.45, 0.30, 0.25])
    channel = rng.choice(CHANNELS, n, p=[0.35, 0.25, 0.20, 0.20])
    plan = rng.choice(list(PLAN_PRICE), n, p=[0.45, 0.35, 0.20])
    contract = rng.choice(["Monthly", "Annual"], n, p=[0.65, 0.35])

    base_price = np.array([PLAN_PRICE[p] for p in plan], dtype=float)
    usage_base = np.array([PLAN_USAGE[p] for p in plan]) * np.exp(rng.normal(0, 0.35, n))
    plan_eff = np.array([P["plan"][p] for p in plan])
    chan_eff = np.array([P["channel"][c] for c in channel])
    loc_eff = np.array([P["location"][l] for l in location])
    annual = contract == "Annual"
    treated = plan != "Basic"

    s = rng.normal(0, 1, n)           # latent dissatisfaction
    alive = np.zeros(n, dtype=bool)
    churn_idx = np.full(n, -1)
    chunks, eff_sum, eff_n = [], 0.0, 0

    for t in range(T):
        alive |= signup == t
        idx = np.flatnonzero(alive)
        if idx.size == 0:
            continue
        tenure = t - signup[idx]
        cont = tenure > 0
        s[idx[cont]] = RHO * s[idx[cont]] + SIG * rng.standard_normal(cont.sum())
        st = s[idx]

        hike = treated[idx] & (t >= PRICE_HIKE_IDX)
        mrr = base_price[idx] * np.where(hike, 1.10, 1.0)
        season = 1 + 0.10 * np.sin(2 * np.pi * (t % 12) / 12)
        usage = usage_base[idx] * np.exp(-0.25 * st) * season * np.exp(rng.normal(0, 0.15, idx.size))
        sessions = rng.poisson(np.maximum(usage / 1.5, 0.1))
        tickets = rng.poisson(0.15 * np.exp(0.5 * st))
        failed = (rng.random(idx.size) < sigmoid(-3.2 + 0.4 * st)).astype(int)

        renewal = annual[idx] & cont & (tenure % 12 == 0)
        logit0 = (
            P["intercept"]
            + P["early_life"] * np.exp(-tenure / 3.0)
            + P["annual_contract"] * annual[idx]
            + P["annual_renewal_month"] * renewal
            + plan_eff[idx] + chan_eff[idx] + loc_eff[idx]
            + P["age_per_year"] * (age[idx] - 38)
            + P["dissatisfaction"] * st
            + P["failed_payment"] * failed
        )
        p = sigmoid(logit0 + P["price_hike"] * hike)
        if hike.any():  # ground truth: average hazard increase caused by the hike
            eff_sum += (p[hike] - sigmoid(logit0[hike])).sum()
            eff_n += int(hike.sum())
        churn = rng.random(idx.size) < p

        chunks.append(pd.DataFrame({
            "customer_id": idx + 1,
            "month_idx": t,
            "month": month_label(t),
            "tenure_month": tenure,
            "usage_hours": np.round(usage, 2),
            "sessions": sessions,
            "tickets": tickets,
            "failed_payment": failed,
            "mrr": np.round(mrr, 2),
            "churned_this_month": churn.astype(int),
            "latent_dissatisfaction": np.round(st, 4),   # oracle column: kept in memory, never written to CSV/SQL
        }))
        alive[idx[churn]] = False
        churn_idx[idx[churn]] = t

    months = pd.concat(chunks, ignore_index=True)
    churned = churn_idx >= 0
    customers = pd.DataFrame({
        "customer_id": np.arange(1, n + 1),
        "signup_idx": signup,
        "signup_month": [month_label(i) for i in signup],
        "age": age,
        "location": location,
        "plan": plan,
        "contract": contract,
        "channel": channel,
        "base_price": base_price.astype(int),
        "churn_month_idx": pd.Series(churn_idx).where(churned).astype("Int64"),
        "churn_month": [month_label(i) if i >= 0 else None for i in churn_idx],
        "is_churned": churned.astype(int),
        "observed_months": np.where(churned, churn_idx - signup + 1, END_IDX - signup + 1),
    })
    truth = {
        "seed": cfg.seed,
        "n_customers": n,
        "share_churned": float(churned.mean()),
        "true_price_effect_pp_on_monthly_hazard": float(100 * eff_sum / max(eff_n, 1)),
        "params": P,
    }
    return customers, months, truth


def write_csvs(customers, months, truth, out_dir: Path = DATA_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    customers.to_csv(out_dir / "customers.csv", index=False)
    months.drop(columns=["latent_dissatisfaction"], errors="ignore").to_csv(out_dir / "customer_months.csv", index=False)
    (out_dir / "ground_truth.json").write_text(json.dumps(truth, indent=2))


if __name__ == "__main__":
    c, m, t = simulate()
    write_csvs(c, m, t)
    print(f"customers={len(c):,} customer_months={len(m):,} churned={t['share_churned']:.1%}")
    print(f"true price-hike effect: +{t['true_price_effect_pp_on_monthly_hazard']:.2f} pp monthly churn")
