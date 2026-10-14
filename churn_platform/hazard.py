"""Discrete-time hazard model (person-period logistic regression), fitted by Newton-Raphson.

One row per customer-month, outcome = churned this month. Because the data are simulated we know
the true coefficients and can check recovery. Two specifications:

  A. structural variables only (contract, plan, channel, location, age, failed payment, price hike)
  B. A plus behavioral proxies (usage vs plan norm, tickets)

The simulation has a LATENT dissatisfaction state that drives churn, usage, tickets and failed
payments together. In A it is omitted, so the failed-payment coefficient absorbs part of it
(omitted-variable bias). In B the proxies soak up some of it. This is the practical reason
behavioral signals predict well yet should not be read as causes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import PRICE_HIKE_IDX
from .simulate import TRUE_PARAMS


def design(months: pd.DataFrame, customers: pd.DataFrame, spec: str):
    """spec: 'A' structural only, 'B' = A + usage/tickets proxies, 'C' = A + the true latent state (oracle)."""
    df = months.merge(customers[["customer_id", "plan", "channel", "location", "age", "contract"]], on="customer_id")
    X = pd.DataFrame(index=df.index)
    annual = df["contract"] == "Annual"
    X["annual_contract"] = annual.astype(float)
    X["annual_renewal_month"] = (annual & (df["tenure_month"] > 0) & (df["tenure_month"] % 12 == 0)).astype(float)
    for lo, hi, name in [(0, 0, "tenure_0"), (1, 2, "tenure_1_2"), (3, 5, "tenure_3_5"), (6, 11, "tenure_6_11")]:
        X[name] = df["tenure_month"].between(lo, hi).astype(float)
    X["plan_Standard"] = (df["plan"] == "Standard").astype(float)
    X["plan_Premium"] = (df["plan"] == "Premium").astype(float)
    for c in ["Paid Search", "Referral", "Social"]:
        X[f"channel_{c}"] = (df["channel"] == c).astype(float)
    X["location_Urban"] = (df["location"] == "Urban").astype(float)
    X["location_Semi-Urban"] = (df["location"] == "Semi-Urban").astype(float)
    X["age_per_year"] = df["age"] - 38.0
    X["failed_payment"] = df["failed_payment"].astype(float)
    X["price_hike"] = ((df["plan"] != "Basic") & (df["month_idx"] >= PRICE_HIKE_IDX)).astype(float)
    if spec == "B":
        lu = np.log(df["usage_hours"])
        X["log_usage_vs_plan"] = lu - lu.groupby(df["plan"]).transform("mean")
        X["tickets"] = df["tickets"].astype(float)
    elif spec == "C":
        X["latent_dissatisfaction"] = df["latent_dissatisfaction"].astype(float)
    return X, df["churned_this_month"].to_numpy(float)


def fit_logit(X: pd.DataFrame, y: np.ndarray) -> pd.DataFrame:
    A = np.column_stack([np.ones(len(X)), X.to_numpy(float)])
    beta = np.zeros(A.shape[1])
    beta[0] = np.log(y.mean() / (1 - y.mean()))
    for _ in range(30):
        p = 1 / (1 + np.exp(-(A @ beta)))
        H = (A * (p * (1 - p))[:, None]).T @ A
        step = np.linalg.solve(H, A.T @ (y - p))
        beta += step
        if np.abs(step).max() < 1e-9:
            break
    p = 1 / (1 + np.exp(-(A @ beta)))
    cov = np.linalg.inv((A * (p * (1 - p))[:, None]).T @ A)
    return pd.DataFrame({"term": ["intercept"] + list(X.columns), "coef": beta, "se": np.sqrt(np.diag(cov))})


TRUE_BY_TERM = {
    "annual_contract": TRUE_PARAMS["annual_contract"],
    "annual_renewal_month": TRUE_PARAMS["annual_renewal_month"],
    "plan_Standard": TRUE_PARAMS["plan"]["Standard"],
    "plan_Premium": TRUE_PARAMS["plan"]["Premium"],
    "channel_Paid Search": TRUE_PARAMS["channel"]["Paid Search"],
    "channel_Referral": TRUE_PARAMS["channel"]["Referral"],
    "channel_Social": TRUE_PARAMS["channel"]["Social"],
    "location_Urban": TRUE_PARAMS["location"]["Urban"],
    "location_Semi-Urban": TRUE_PARAMS["location"]["Semi-Urban"],
    "age_per_year": TRUE_PARAMS["age_per_year"],
    "failed_payment": TRUE_PARAMS["failed_payment"],
    "price_hike": TRUE_PARAMS["price_hike"],
}


def recovery_table(months: pd.DataFrame, customers: pd.DataFrame) -> pd.DataFrame:
    """months must still contain the in-memory 'latent_dissatisfaction' column for spec C."""
    fits = {}
    for spec in "ABC":
        X, y = design(months, customers, spec)
        fits[spec] = fit_logit(X, y).set_index("term")
    rows = []
    for term, true in TRUE_BY_TERM.items():
        row = {"term": term, "true": true}
        for spec in "ABC":
            row[f"est_{spec}"] = fits[spec].loc[term, "coef"]
            row[f"se_{spec}"] = fits[spec].loc[term, "se"]
        rows.append(row)
    out = pd.DataFrame(rows)
    for spec in "ABC":
        out[f"{spec}_covers_truth"] = (out["true"] - out[f"est_{spec}"]).abs() <= 1.96 * out[f"se_{spec}"]
    return out
