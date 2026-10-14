"""Static figures (PNG) for the README and docs. The dashboard draws its own interactive charts."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .config import FIG_DIR, PRICE_HIKE_IDX, month_short

BLUE, ORANGE, GREY, RED, GREEN = "#2F6DB5", "#E07B39", "#8A8F98", "#C0392B", "#2E8B57"
plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
                     "axes.titleweight": "bold", "figure.dpi": 110})


def _save(fig, name):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG_DIR / name, dpi=150)
    plt.close(fig)


def fig_kpis(k: pd.DataFrame):
    fig, ax = plt.subplots(1, 2, figsize=(12, 4))
    ax[0].plot(k["month_idx"], k["active_customers"], color=BLUE, label="Active customers")
    ax[0].set_ylabel("Active customers", color=BLUE)
    a2 = ax[0].twinx()
    a2.plot(k["month_idx"], k["mrr"] / 1e6, color=ORANGE, label="MRR")
    a2.set_ylabel("MRR (millions)", color=ORANGE)
    a2.spines["right"].set_visible(True)
    ax[0].axvline(PRICE_HIKE_IDX, ls=":", color=GREY)
    ax[0].set_title("Customer base and MRR")
    ax[1].plot(k["month_idx"], k["logo_churn_pct"], color=GREY, alpha=.6, label="Monthly")
    ax[1].plot(k["month_idx"], k["logo_churn_3m_avg"], color=RED, label="3-month average")
    ax[1].axvline(PRICE_HIKE_IDX, ls=":", color=GREY)
    ax[1].text(PRICE_HIKE_IDX + .3, ax[1].get_ylim()[1] * .92, "price hike", color=GREY, fontsize=8)
    ax[1].set_ylabel("Logo churn (%)")
    ax[1].set_title("Monthly churn rate")
    ax[1].legend(frameon=False)
    for a in (ax[0], ax[1]):
        a.set_xticks(range(0, 42, 6))
        a.set_xticklabels([month_short(i) for i in range(0, 42, 6)], rotation=30)
    _save(fig, "kpis.png")


def fig_cohorts(c: pd.DataFrame):
    piv = c.pivot(index="cohort_q", columns="k", values="retention_pct")
    fig, ax = plt.subplots(figsize=(9, 5))
    im = ax.imshow(piv.values, cmap="Blues", vmin=30, vmax=100, aspect="auto")
    ax.set_xticks(range(len(piv.columns)), piv.columns)
    ax.set_yticks(range(len(piv.index)), [f"{2023 + q // 4}-Q{q % 4 + 1}" for q in piv.index])
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v = piv.values[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7, color="white" if v < 65 else "black")
    ax.set_xlabel("Months since signup")
    ax.set_ylabel("Signup cohort")
    ax.set_title("Retention by signup cohort (%), observable cells only")
    fig.colorbar(im, ax=ax, shrink=.8)
    _save(fig, "cohort_retention.png")


def fig_survival(km: pd.DataFrame, hazard: pd.DataFrame):
    fig, ax = plt.subplots(1, 3, figsize=(14, 4))
    cols = {"Monthly": ORANGE, "Annual": BLUE}
    for name, g in km[km["variable"] == "contract"].groupby("level"):
        ax[0].step(g["time"], g["survival"], where="post", color=cols[name], label=name)
        ax[0].fill_between(g["time"], g["ci_low"], g["ci_high"], step="post", color=cols[name], alpha=.15)
    ax[0].set_title("Survival by contract (Kaplan-Meier, 95% CI)")
    ax[0].set_xlabel("Months since signup")
    ax[0].set_ylabel("Share still subscribed")
    ax[0].legend(frameon=False)
    ax[0].set_ylim(0, 1.02)
    for name, g in km[km["variable"] == "channel"].groupby("level"):
        ax[1].step(g["time"], g["survival"], where="post", label=name)
    ax[1].set_title("Survival by acquisition channel")
    ax[1].set_xlabel("Months since signup")
    ax[1].legend(frameon=False)
    ax[1].set_ylim(0, 1.02)
    for name, g in hazard.groupby("contract"):
        ax[2].plot(g["tenure_month"], 100 * g["hazard"], marker="o", ms=3, color=cols[name], label=name)
    ax[2].set_title("Churn hazard by tenure")
    ax[2].set_xlabel("Tenure month")
    ax[2].set_ylabel("Monthly churn (%)")
    ax[2].legend(frameon=False)
    _save(fig, "survival_and_hazard.png")


def fig_model(cal: pd.DataFrame, lift: pd.DataFrame, imp: pd.DataFrame, metrics: pd.DataFrame):
    fig, ax = plt.subplots(1, 3, figsize=(14, 4.2))
    m = max(cal["mean_predicted"].max(), cal["observed_rate"].max()) * 1.1
    ax[0].plot([0, m], [0, m], ls="--", color=GREY)
    ax[0].plot(cal["mean_predicted"], cal["observed_rate"], marker="o", color=BLUE)
    ax[0].set_xlabel("Mean predicted risk")
    ax[0].set_ylabel("Observed churn rate")
    ax[0].set_title("Calibration (test snapshot)")
    ax[1].bar(lift["decile"], lift["lift"], color=BLUE)
    ax[1].axhline(1, color=GREY, ls="--")
    ax[1].set_xlabel("Risk decile (1 = highest)")
    ax[1].set_ylabel("Lift vs average")
    ax[1].set_title("Lift by risk decile (test)")
    top = imp.head(8).iloc[::-1]
    ax[2].barh(top["feature"], top["auc_drop"], xerr=top["std"], color=ORANGE)
    ax[2].set_xlabel("AUC drop when shuffled")
    ax[2].set_title("Permutation importance (test)")
    _save(fig, "model_diagnostics.png")


def fig_campaign(curves: pd.DataFrame, assumptions: str):
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    colors = {"by risk": BLUE, "by expected revenue at risk": GREEN, "random": GREY}
    for name, g in curves.groupby("strategy"):
        ax.plot(g["pct_contacted"], g["realized_net"] / 1e3, color=colors[name], label=name)
    ax.axhline(0, color="black", lw=.6)
    ax.set_xlabel("% of at-risk-ranked customers contacted")
    ax.set_ylabel("Net value (thousands)")
    ax.set_title("Campaign backtest, assumption-driven")
    ax.text(.02, .02, assumptions, transform=ax.transAxes, fontsize=8, color=GREY)
    ax.legend(frameon=False)
    _save(fig, "campaign_value.png")


def fig_did(es: pd.DataFrame, did: dict, true_pp: float):
    fig, ax = plt.subplots(1, 2, figsize=(12, 4))
    ax[0].plot(es["month_idx"], es["control (Basic)"], color=GREY, label="Control (Basic)")
    ax[0].plot(es["month_idx"], es["treated (Standard/Premium)"], color=ORANGE, label="Treated (Standard/Premium)")
    ax[0].axvline(PRICE_HIKE_IDX, ls=":", color="black")
    ax[0].set_ylabel("Monthly churn (%)")
    ax[0].set_title("Churn before and after the 2025-07 price increase")
    ax[0].legend(frameon=False)
    ax[1].errorbar([0], [did["did_pp"]], yerr=[[did["did_pp"] - did["ci_low"]], [did["ci_high"] - did["did_pp"]]],
                   fmt="o", color=BLUE, capsize=5, label="DiD estimate (95% bootstrap CI)")
    ax[1].axhline(true_pp, color=RED, ls="--", label=f"True effect in simulation (+{true_pp:.2f} pp)")
    ax[1].axhline(0, color="black", lw=.6)
    ax[1].set_xticks([])
    ax[1].set_ylabel("Change in monthly churn (pp)")
    ax[1].set_title("Difference-in-differences vs ground truth")
    ax[1].legend(frameon=False, loc="lower right")
    _save(fig, "price_change_did.png")


def fig_recovery(rec: pd.DataFrame):
    r = rec.iloc[::-1].reset_index(drop=True)
    y = np.arange(len(r))
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.errorbar(r["est_A"], y + .22, xerr=1.96 * r["se_A"], fmt="o", ms=4, color=ORANGE, capsize=2, label="A: structural only")
    ax.errorbar(r["est_B"], y, xerr=1.96 * r["se_B"], fmt="s", ms=4, color=BLUE, capsize=2, label="B: + usage/tickets proxies")
    ax.errorbar(r["est_C"], y - .22, xerr=1.96 * r["se_C"], fmt="^", ms=4, color=GREEN, capsize=2, label="C: + true latent state (oracle)")
    ax.scatter(r["true"], y, marker="|", s=250, color="black", label="True value", zorder=3)
    ax.set_yticks(y, r["term"])
    ax.axvline(0, color=GREY, lw=.6)
    ax.set_xlabel("Log-odds coefficient (95% CI)")
    ax.set_title("Can the hazard model recover the true drivers?")
    ax.legend(frameon=False, loc="lower right")
    _save(fig, "driver_recovery.png")
