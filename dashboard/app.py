"""Churn analytics dashboard.  Run:  streamlit run dashboard/app.py   (after python -m churn_platform.pipeline)"""
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from churn_platform import campaign  # noqa: E402
from churn_platform.config import PRICE_HIKE_IDX, month_short  # noqa: E402

OUT = ROOT / "outputs"

st.set_page_config(page_title="Churn analytics", layout="wide")


@st.cache_data
def load(name: str) -> pd.DataFrame:
    return pd.read_csv(OUT / f"{name}.csv")


if not (OUT / "summary.json").exists():
    st.error("No outputs found. Run `python -m churn_platform.pipeline` first.")
    st.stop()

summary = json.loads((OUT / "summary.json").read_text())
did = json.loads((OUT / "price_did.json").read_text())

st.title("Subscription churn analytics")
st.warning("All data here is **simulated** with a known churn mechanism. It demonstrates the method; "
           "nothing below describes real customers.", icon="⚠️")

tab_over, tab_ret, tab_driver, tab_model, tab_act, tab_price = st.tabs(
    ["Overview", "Retention & survival", "Drivers", "Prediction model", "At-risk customers & campaign", "Price change"])

# ------------------------------------------------------------------ overview
with tab_over:
    k = load("monthly_kpis")
    k["month_label"] = k["month_idx"].map(month_short)
    last, prev = k.iloc[-1], k.iloc[-2]
    c = st.columns(4)
    c[0].metric("Active customers", f"{int(last.active_customers):,}", f"{int(last.active_customers - prev.active_customers):+,}")
    c[1].metric("MRR", f"{last.mrr:,.0f}", f"{last.mrr - prev.mrr:+,.0f}")
    c[2].metric("Logo churn (month)", f"{last.logo_churn_pct:.2f}%", f"{last.logo_churn_pct - prev.logo_churn_pct:+.2f} pp", delta_color="inverse")
    c[3].metric("Customers ever churned", f"{100 * summary['share_ever_churned']:.0f}%")
    st.caption("The customer base shrinks at the end because the simulation stops signups after 2025-12; "
               "that is a design choice, not a finding.")
    left, right = st.columns(2)
    f = px.line(k, x="month_label", y=["logo_churn_pct", "logo_churn_3m_avg"], title="Monthly logo churn (%)",
                labels={"value": "%", "month_label": "", "variable": ""})
    f.add_vline(x=month_short(PRICE_HIKE_IDX), line_dash="dot")
    left.plotly_chart(f, use_container_width=True)
    w = load("mrr_waterfall")
    w["month"] = w["month_idx"].map(month_short)
    wf = go.Figure()
    wf.add_bar(x=w["month"], y=w["new_mrr"], name="New")
    wf.add_bar(x=w["month"], y=w["expansion_mrr"], name="Price increase")
    wf.add_bar(x=w["month"], y=-w["churned_mrr"], name="Churned")
    wf.update_layout(barmode="relative", title="MRR movements", yaxis_title="MRR")
    right.plotly_chart(wf, use_container_width=True)
    st.subheader("Churn by segment")
    st.caption("Compare on monthly churn (events per customer-month), not '% ever churned': segments are observed for different lengths.")
    d = load("churn_by_dimension")
    dim = st.selectbox("Dimension", sorted(d["dimension"].unique()))
    st.dataframe(d[d["dimension"] == dim].drop(columns="dimension"), hide_index=True, use_container_width=True)

# ------------------------------------------------------------------ retention
with tab_ret:
    coh = load("cohort_retention")
    piv = coh.pivot(index="cohort_q", columns="k", values="retention_pct")
    piv.index = [f"{2023 + q // 4}-Q{q % 4 + 1}" for q in piv.index]
    st.plotly_chart(px.imshow(piv, text_auto=".0f", aspect="auto", color_continuous_scale="Blues",
                              labels={"x": "Months since signup", "y": "Cohort", "color": "% retained"},
                              title="Cohort retention (only cells every cohort member could have reached)"),
                    use_container_width=True)
    km = load("km_curves")
    var = st.radio("Kaplan-Meier by", ["contract", "channel", "plan"], horizontal=True)
    g = km[km["variable"] == var]
    fk = go.Figure()
    for lvl, gg in g.groupby("level"):
        fk.add_scatter(x=gg["time"], y=gg["survival"], mode="lines", line_shape="hv", name=lvl)
    fk.update_layout(title="Share still subscribed", xaxis_title="Months since signup", yaxis_range=[0, 1.02])
    st.plotly_chart(fk, use_container_width=True)
    hz = load("hazard_by_tenure")
    st.plotly_chart(px.line(hz, x="tenure_month", y="hazard", color="contract", markers=True,
                            title="Churn hazard by tenure month (spikes at annual renewals)"), use_container_width=True)
    st.dataframe(load("survival_summary").round(3), hide_index=True, use_container_width=True)

# ------------------------------------------------------------------ drivers
with tab_driver:
    rec = load("driver_recovery")
    st.markdown("A discrete-time hazard model checked against the **known** generating coefficients. "
               "**A** structural variables only; **B** adds usage/ticket proxies; **C** adds the true latent state (an oracle no analyst has).")
    fr = go.Figure()
    for spec, name in [("A", "A structural"), ("B", "B + proxies"), ("C", "C + oracle")]:
        fr.add_scatter(x=rec[f"est_{spec}"], y=rec["term"], mode="markers", name=name,
                       error_x=dict(type="data", array=1.96 * rec[f"se_{spec}"]))
    fr.add_scatter(x=rec["true"], y=rec["term"], mode="markers", name="True", marker=dict(symbol="line-ns", size=14, color="black"))
    fr.update_layout(height=520, xaxis_title="log-odds coefficient (95% CI)")
    st.plotly_chart(fr, use_container_width=True)
    st.caption(f"Coefficients within 95% CI of truth: A {summary['recovery_cover']['A']}/{summary['recovery_terms']}, "
               f"B {summary['recovery_cover']['B']}/{summary['recovery_terms']}, C {summary['recovery_cover']['C']}/{summary['recovery_terms']}. "
               "Failed payments look more harmful than they are unless the latent state is controlled: omitted-variable bias.")

# ------------------------------------------------------------------ model
with tab_model:
    m = load("model_metrics")
    st.subheader("Out-of-time test (snapshot 2026-03, outcome Apr-Jun 2026)")
    st.dataframe(m[m["split"] == "test"][["model", "roc_auc", "pr_auc", "brier_skill", "lift_top10", "recall_top10", "recall_top20"]].round(3),
                 hide_index=True, use_container_width=True)
    a, b = st.columns(2)
    cal = load("calibration_test")
    fc = go.Figure()
    fc.add_scatter(x=[0, cal.mean_predicted.max()], y=[0, cal.mean_predicted.max()], mode="lines", line=dict(dash="dash"), name="perfect")
    fc.add_scatter(x=cal["mean_predicted"], y=cal["observed_rate"], mode="lines+markers", name="model")
    fc.update_layout(title="Calibration", xaxis_title="mean predicted", yaxis_title="observed")
    a.plotly_chart(fc, use_container_width=True)
    imp = load("permutation_importance").head(10).iloc[::-1]
    b.plotly_chart(px.bar(imp, x="auc_drop", y="feature", orientation="h", title="Permutation importance (AUC drop)"), use_container_width=True)
    st.plotly_chart(px.bar(load("lift_test"), x="decile", y="lift", title="Lift by risk decile (1 = highest risk)"), use_container_width=True)
    st.caption("Importance measures predictive usefulness, not cause. Moderate AUC is expected: most churn in this data is random draws from the hazard.")

# ------------------------------------------------------------------ at-risk + campaign
with tab_act:
    cur = load("scored_current")
    st.subheader("Live customer base, ranked by 3-month churn risk")
    f1, f2, f3 = st.columns(3)
    plans = f1.multiselect("Plan", sorted(cur["plan"].unique()), default=sorted(cur["plan"].unique()))
    contracts = f2.multiselect("Contract", sorted(cur["contract"].unique()), default=sorted(cur["contract"].unique()))
    segs = f3.multiselect("Segment", sorted(cur["segment"].unique()), default=sorted(cur["segment"].unique()))
    sub = cur[cur["plan"].isin(plans) & cur["contract"].isin(contracts) & cur["segment"].isin(segs)].sort_values("risk", ascending=False)
    top_n = st.slider("Show top N", 10, 500, 50, 10)
    show = sub.head(top_n)[["customer_id", "plan", "contract", "channel", "tenure_months", "mrr", "tickets_3m", "failed_3m", "usage_trend", "segment", "risk"]]
    st.dataframe(show.round(3), hide_index=True, use_container_width=True)
    st.download_button("Download filtered list (CSV)", sub.to_csv(index=False), "at_risk_customers.csv", "text/csv")
    st.dataframe(load("segments_profile"), hide_index=True, use_container_width=True)
    st.caption("Segments come from k-means with weak separation (silhouette about 0.2); treat them as convenience groupings.")

    st.subheader("Retention campaign backtest")
    st.info("Save rate, cost and horizon are **assumptions**. This data has no campaign, so the true save rate cannot be estimated. "
            "The best contact depth is chosen with hindsight on the same test outcomes, so net value is an upper bound.", icon="ℹ️")
    s1, s2, s3 = st.columns(3)
    save_rate = s1.slider("Save rate if contacted", 0.01, 0.50, campaign.DEFAULTS["save_rate"], 0.01)
    cost = s2.slider("Cost per contact", 10, 400, int(campaign.DEFAULTS["cost"]), 10)
    horizon = s3.slider("Months of revenue protected", 3, 24, campaign.DEFAULTS["horizon"], 1)
    curves = campaign.campaign_curves(load("scored_test"), save_rate, float(cost), horizon)
    st.plotly_chart(px.line(curves, x="pct_contacted", y="realized_net", color="strategy",
                            title="Net value vs share contacted", labels={"realized_net": "net value", "pct_contacted": "% contacted"}),
                    use_container_width=True)
    st.dataframe(campaign.best_point(curves).round(1), hide_index=True, use_container_width=True)
    st.markdown("**Sensitivity of the best contact depth to the assumptions**")
    st.dataframe(load("campaign_sensitivity"), hide_index=True, use_container_width=True)

# ------------------------------------------------------------------ price
with tab_price:
    es = load("price_event_study")
    es["month"] = es["month_idx"].map(month_short)
    fp = px.line(es, x="month", y=["control (Basic)", "treated (Standard/Premium)"], title="Monthly churn (%) around the 2025-07 price increase",
                 labels={"value": "%", "variable": ""})
    fp.add_vline(x=month_short(PRICE_HIKE_IDX), line_dash="dot")
    st.plotly_chart(fp, use_container_width=True)
    c = st.columns(3)
    c[0].metric("DiD estimate", f"{did['did_pp']:+.2f} pp", f"95% CI {did['ci_low']:+.2f} to {did['ci_high']:+.2f}", delta_color="off")
    c[1].metric("True effect in simulation", f"{did['true_pp']:+.2f} pp")
    c[2].metric("Pre-trend slope of gap", f"{did['pretrend']['slope_pp_per_month']:+.3f} pp/mo", f"SE {did['pretrend']['se']:.3f}", delta_color="off")
    st.caption("Parallel trends is assumed, not proven; the flat pre-period gap is a plausibility check only. "
               "Plan was not randomized, and the CI covers sampling error, not assumption violations. With real data the true effect is unknown.")
