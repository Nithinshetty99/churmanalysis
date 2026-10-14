"""End-to-end pipeline:  python -m churn_platform.pipeline [--n 10000] [--seed 42]

simulate -> load SQL -> data-quality gate -> KPIs/cohorts/revenue -> survival -> hazard model
-> temporal-split prediction -> segmentation -> campaign backtest -> price-change DiD -> figures.
All tables land in outputs/ (CSV) and figures in outputs/figures/.
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

from . import campaign, hazard, modeling, price_change, reporting, segmentation, simulate, survival
from .config import CURRENT_SNAP, DATA_DIR, OUT_DIR, TEST_SNAP, TRAIN_SNAPS, VAL_SNAP
from .db import build_db, load_queries, run


def save(df: pd.DataFrame, name: str) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    df.to_csv(OUT_DIR / f"{name}.csv", index=False)


def step(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main(n: int = 10_000, seed: int = 42) -> dict:
    summary: dict = {}

    step(f"simulating {n:,} customers (seed {seed})")
    customers, months, truth = simulate.simulate(simulate.SimConfig(n, seed))
    simulate.write_csvs(customers, months, truth)
    con = build_db(DATA_DIR, DATA_DIR / "churn.db")
    q = load_queries()

    # ---- data-quality gate: stop if any check fails
    dq = pd.concat([run(con, q, name).assign(check=name) for name in q if name.startswith("dq_") and name != "dq_table_sizes"])
    save(dq, "data_quality")
    if dq["violations"].sum() > 0:
        raise SystemExit(f"data quality failed:\n{dq}")
    step(f"data quality: {len(dq)} checks passed")

    # ---- KPIs, cohorts, revenue (SQL)
    kpis = run(con, q, "monthly_kpis"); save(kpis, "monthly_kpis")
    save(run(con, q, "churn_by_dimension"), "churn_by_dimension")
    hz = run(con, q, "hazard_by_tenure"); save(hz, "hazard_by_tenure")
    save(run(con, q, "engagement_vs_churn"), "engagement_vs_churn")
    coh = run(con, q, "cohort_retention"); save(coh, "cohort_retention")
    save(run(con, q, "first_90_days_by_channel"), "first_90_days_by_channel")
    save(run(con, q, "mrr_waterfall"), "mrr_waterfall")
    save(run(con, q, "revenue_by_segment"), "revenue_by_segment")
    save(run(con, q, "revenue_concentration"), "revenue_concentration")
    summary["customers"] = n
    summary["share_ever_churned"] = float(customers["is_churned"].mean())
    summary["avg_monthly_logo_churn_pct"] = float(100 * months["churned_this_month"].mean())
    summary["final_mrr"] = float(kpis["mrr"].iloc[-1])
    step("SQL KPIs, cohorts and revenue done")

    # ---- survival analysis
    km_rows, sv_rows = [], []
    for var in ["contract", "plan", "channel"]:
        for level, g in customers.groupby(var):
            km = survival.kaplan_meier(g["observed_months"], g["is_churned"])
            km.insert(0, "level", level); km.insert(0, "variable", var)
            km_rows.append(km)
        lr = survival.logrank_test(customers["observed_months"], customers["is_churned"], customers[var])
        for level, g in customers.groupby(var):
            km = survival.kaplan_meier(g["observed_months"], g["is_churned"])
            sv_rows.append({"variable": var, "level": level, "n": len(g),
                            "S_6m": survival.survival_at(km, 6), "S_12m": survival.survival_at(km, 12),
                            "S_24m": survival.survival_at(km, 24),
                            "logrank_chi2": lr["chi2"], "logrank_p": lr["p_value"]})
    km_all = pd.concat(km_rows); save(km_all, "km_curves")
    sv = pd.DataFrame(sv_rows); save(sv, "survival_summary")
    step("survival analysis done")

    # ---- hazard model: can we recover the known drivers?
    rec = hazard.recovery_table(months, customers); save(rec, "driver_recovery")
    step("driver recovery, coefficients within 95% CI of truth: " + ", ".join(f"{k}={int(rec[f'{k}_covers_truth'].sum())}/{len(rec)}" for k in "ABC"))

    # ---- prediction with temporal split
    train = modeling.build_snapshots(con, q, TRAIN_SNAPS)
    val = modeling.build_snapshots(con, q, [VAL_SNAP])
    test = modeling.build_snapshots(con, q, [TEST_SNAP])
    runs, best_cfg = modeling.fit_and_compare(train, val, test)
    metrics = pd.DataFrame([{"model": r.name, "split": s, **m}
                            for r in runs for s, m in (("validation", r.val_metrics), ("test", r.test_metrics))])
    save(metrics, "model_metrics")
    best = runs[-1]
    p_test = best.model.predict_proba(modeling.features_of(test, modeling.NUM, modeling.CAT))[:, 1]
    cal = modeling.calibration_table(test["label"], p_test); save(cal, "calibration_test")
    lift = modeling.lift_table(test["label"], p_test); save(lift, "lift_test")
    imp = modeling.importance_table(best.model, test); save(imp, "permutation_importance")
    save(modeling.logit_coefficients(runs[1].model), "logit_coefficients")
    scored_test = test[["customer_id", "plan", "contract", "mrr", "label"]].assign(risk=p_test)
    save(scored_test, "scored_test")
    step(f"model test AUC: " + ", ".join(f"{r.name.split(' (')[0]}={r.test_metrics['roc_auc']:.3f}" for r in runs))

    # ---- production model: refit on every labelled snapshot, score the live base
    all_labelled = modeling.build_snapshots(con, q, TRAIN_SNAPS + [VAL_SNAP, 36, TEST_SNAP])
    prod = modeling.make_model("gbm", max_depth=best_cfg["max_depth"], learning_rate=best_cfg["learning_rate"])
    prod.fit(modeling.features_of(all_labelled, modeling.NUM, modeling.CAT), all_labelled["label"])
    current = run(con, q, "snapshot_features", snap=CURRENT_SNAP).drop(columns="label")
    current["risk"] = prod.predict_proba(modeling.features_of(current, modeling.NUM, modeling.CAT))[:, 1]
    current["risk_decile"] = pd.qcut(current["risk"].rank(method="first", ascending=False), 10, labels=range(1, 11)).astype(int)

    # ---- segmentation of the live base
    current, prof, sil = segmentation.segment(current)
    save(current, "scored_current"); save(prof, "segments_profile")
    step(f"segmentation: k={len(prof)} (silhouette {max(sil.values()):.2f})")

    # ---- campaign backtest on the test snapshot
    curves = campaign.campaign_curves(scored_test)
    save(curves, "campaign_curves")
    bp = campaign.best_point(curves); save(bp, "campaign_best_points")
    save(campaign.sensitivity_grid(scored_test), "campaign_sensitivity")

    # ---- price-change DiD
    did = price_change.did_estimate(months, customers)
    es = price_change.event_study(months, customers); save(es, "price_event_study")
    pt = price_change.pretrend_slope_gap(es)
    (OUT_DIR / "price_did.json").write_text(json.dumps({**did, "pretrend": pt,
                                                         "true_pp": truth["true_price_effect_pp_on_monthly_hazard"]}, indent=2))
    step(f"price DiD: {did['did_pp']:+.2f} pp (95% CI {did['ci_low']:+.2f} to {did['ci_high']:+.2f}); truth {truth['true_price_effect_pp_on_monthly_hazard']:+.2f}")

    # ---- figures
    reporting.fig_kpis(kpis); reporting.fig_cohorts(coh); reporting.fig_survival(km_all, hz)
    reporting.fig_model(cal, lift, imp, metrics); reporting.fig_recovery(rec)
    reporting.fig_campaign(curves, "assumes 15% save rate, cost 100/contact, 12-month horizon")
    reporting.fig_did(es, did, truth["true_price_effect_pp_on_monthly_hazard"])

    summary.update({
        "best_gbm": best_cfg,
        "test_metrics": {r.name: r.test_metrics for r in runs},
        "did": did, "true_price_effect_pp": truth["true_price_effect_pp_on_monthly_hazard"],
        "campaign_best": bp.to_dict("records"),
        "recovery_cover": {k: int(rec[f"{k}_covers_truth"].sum()) for k in "ABC"},
        "recovery_terms": int(len(rec)),
    })
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=float))
    con.close()
    step("done -> outputs/")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10_000)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    main(a.n, a.seed)
