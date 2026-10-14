"""Render static PREVIEWS of the four dashboard pages from powerbi/dataset (matplotlib).

These mirror the layout and numbers of the Power BI report (same tables, same measure logic) so the
README has images without needing Power BI Desktop. They are previews, not Power BI captures: replace
them with real screenshots (see powerbi/BUILD_GUIDE.md, step 9) once the .pbix is built.
Run: python powerbi/render_previews.py   ->  docs/screenshots/preview_*.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DS, OUT = ROOT / "powerbi" / "dataset", ROOT / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

NAVY, RED, GREEN, GREY, BLUE, ORANGE = "#1F4E79", "#C0392B", "#1E8449", "#7F8C8D", "#2E86C1", "#E67E22"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left",
                     "axes.edgecolor": "#BDC3C7", "xtick.color": "#566573", "ytick.color": "#566573"})

dc = pd.read_csv(DS / "dim_customer.csv")
fm = pd.read_csv(DS / "fact_customer_month.csv")
risk = pd.read_csv(DS / "at_risk_customers.csv")
j = fm.merge(dc, on="customer_id")
overall = fm["churned_this_month"].mean()
monthly = fm.groupby("month").agg(active=("customer_id", "count"), churned=("churned_this_month", "sum"),
                                  mrr=("mrr", "sum"))
monthly["rate"] = monthly["churned"] / monthly["active"]
monthly["rate3"] = monthly["rate"].rolling(3, min_periods=1).mean()
x = pd.to_datetime(monthly.index)


def frame(title, subtitle, slicers):
    fig = plt.figure(figsize=(16, 9), facecolor="#F4F6F7")
    fig.text(0.02, 0.955, title, fontsize=20, fontweight="bold", color=NAVY)
    fig.text(0.02, 0.925, subtitle, fontsize=10.5, color="#566573")
    fig.text(0.98, 0.955, "PREVIEW of Power BI page", fontsize=9, color=GREY, ha="right")
    for i, s in enumerate(slicers):                                   # slicer chips
        fig.text(0.02 + i * 0.118, 0.885, f"  {s}  ▾", fontsize=9, color=NAVY, va="center",
                 bbox=dict(boxstyle="round,pad=0.45", fc="white", ec="#BDC3C7"))
    return fig


def card(fig, x0, y0, w, h, label, value, note="", color=NAVY):
    ax = fig.add_axes([x0, y0, w, h]); ax.set_facecolor("white"); ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values(): s.set_color("#D5D8DC")
    ax.text(0.06, 0.74, label, fontsize=9.5, color="#566573", transform=ax.transAxes)
    ax.text(0.06, 0.30, value, fontsize=24, fontweight="bold", color=color, transform=ax.transAxes)
    if note: ax.text(0.06, 0.08, note, fontsize=7.8, color=GREY, transform=ax.transAxes)


def panel(fig, rect):
    ax = fig.add_axes(rect); ax.set_facecolor("white"); return ax


SL = ["Date range", "Plan", "Contract", "Channel", "Location", "Age band"]
pct = lambda v, d=1: f"{v:.{d}f}%"

# ---------------------------------------------------------------- Page 1: overview
fig = frame("Customer Churn: Executive Overview", "How many customers do we have, and how fast are we losing them?", SL)
last = monthly.iloc[-1]
card(fig, .02, .72, .155, .115, "Customers served (all time)", f"{len(dc):,}")
card(fig, .185, .72, .155, .115, "Currently active", f"{(dc.status == 'Active').sum():,}", "still active after Jun 2026")
card(fig, .35, .72, .155, .115, "Customers churned (all time)", f"{(dc.status == 'Churned').sum():,}", f"{(dc.status == 'Churned').mean():.1%} of all customers")
card(fig, .515, .72, .155, .115, "Avg monthly churn rate", pct(100 * overall, 2), "customers lost per month ÷ active", RED)
card(fig, .68, .72, .155, .115, "MRR, Jun 2026", f"{last.mrr / 1e6:.2f}M", "monthly recurring revenue")
card(fig, .845, .72, .135, .115, "Revenue churn rate", pct(100 * fm.loc[fm.churned_this_month == 1, "mrr"].sum() / fm.mrr.sum(), 2), "share of billed revenue lost", RED)
ax = panel(fig, [.04, .10, .45, .54])
ax.plot(x, 100 * monthly.rate, color="#AEB6BF", lw=1.3, label="Monthly churn rate")
ax.plot(x, 100 * monthly.rate3, color=RED, lw=2.4, label="3-month average")
ax.axvline(pd.Timestamp("2025-07-01"), color=ORANGE, ls="--", lw=1.2)
ax.text(pd.Timestamp("2025-07-15"), ax.get_ylim()[1] * .93, "Price increase\n(Standard/Premium)", fontsize=8, color=ORANGE, va="top")
ax.set_title("Monthly churn rate: share of active customers who left that month"); ax.set_ylabel("% of active customers")
ax.legend(frameon=False, fontsize=9); ax.grid(axis="y", color="#ECF0F1")
ax2 = panel(fig, [.54, .10, .43, .54])
ax2.fill_between(x, monthly.mrr / 1e6, color="#AED6F1"); ax2.plot(x, monthly.mrr / 1e6, color=NAVY, lw=2)
ax2.set_title("Monthly recurring revenue (MRR), millions"); ax2.grid(axis="y", color="#ECF0F1")
ax2.axvline(pd.Timestamp("2025-12-01"), color=GREY, ls=":", lw=1)
ax2.text(pd.Timestamp("2025-11-20"), ax2.get_ylim()[1] * .12, "New signups stop in\nthe simulation (Dec 2025),\nso the base shrinks", fontsize=8, color=GREY, ha="right")
fig.text(0.02, 0.03, "Churn is measured per customer-month. Data are simulated; see docs/FINDINGS.md.", fontsize=8.5, color=GREY)
fig.savefig(OUT / "preview_1_overview.png", dpi=110); plt.close(fig)

# ---------------------------------------------------------------- Page 2: segments
fig = frame("Who Churns Most? Segment Comparison", "Average monthly churn rate by customer group. Red = worse than the overall average, green = better.", SL)
dims = [("contract", "Contract type"), ("channel", "Acquisition channel"), ("age_band", "Age band"),
        ("plan", "Plan (see note)"), ("location", "Location")]
pos = [[.07, .50, .26, .33], [.40, .50, .26, .33], [.72, .50, .25, .33], [.07, .08, .26, .33], [.40, .08, .26, .33]]
for (col, title), rect in zip(dims, pos):
    r = (100 * j.groupby(col)["churned_this_month"].mean()).sort_values()
    ax = panel(fig, rect)
    cols = [RED if v - 100 * overall >= .5 else GREEN if v - 100 * overall <= -.5 else GREY for v in r]
    ax.barh(r.index, r.values, color=cols)
    for yy, v in enumerate(r.values): ax.text(v + .04, yy, f"{v:.2f}%", va="center", fontsize=9)
    ax.axvline(100 * overall, color=NAVY, ls="--", lw=1); ax.set_xlim(0, max(r) * 1.22)
    ax.set_title(title); ax.tick_params(axis="y", labelsize=9)
ax = panel(fig, [.70, .08, .27, .33]); ax.axis("off")
ax.text(0, .95, "How to read this", fontsize=11, fontweight="bold", color=NAVY, va="top")
ax.text(0, .82, f"Dashed line = overall average ({100 * overall:.2f}%).\n\nMonthly contracts churn about twice as\noften as annual ones.\n\nPlan note: Standard/Premium received a\n10% price increase in Jul 2025, so their\nhigher churn is not a pure plan effect.",
        fontsize=9.5, color="#34495E", va="top")
fig.savefig(OUT / "preview_2_segments.png", dpi=110); plt.close(fig)

# ---------------------------------------------------------------- Page 3: lifecycle
fig = frame("Retention & Customer Lifecycle", "When do customers leave? Early in life, and at annual renewal.", ["Contract", "Channel"])
hz = pd.read_csv(DS / "hazard_by_tenure.csv"); km = pd.read_csv(DS / "survival_curves.csv"); coh = pd.read_csv(DS / "cohort_retention.csv")
ax = panel(fig, [.04, .50, .45, .33])
for c, col in [("Monthly", RED), ("Annual", NAVY)]:
    h = hz[hz.contract == c]; ax.plot(h.tenure_month, 100 * h.hazard, color=col, lw=2, label=f"{c} contract")
for t in (12, 24, 36): ax.axvline(t, color="#D5D8DC", lw=1)
ax.set_title("Chance of leaving at each month of tenure"); ax.set_xlabel("Months since signup"); ax.set_ylabel("% leaving")
ax.legend(frameon=False, fontsize=9); ax.grid(axis="y", color="#ECF0F1")
ax.annotate("Annual contracts:\nspikes at renewal\n(months 12, 24, 36)", (12, 13.6), (17, 11), fontsize=8.5, color=NAVY, arrowprops=dict(arrowstyle="->", color=NAVY))
ax = panel(fig, [.54, .50, .43, .33])
for c, col in [("Monthly", RED), ("Annual", NAVY)]:
    k = km[(km.variable == "contract") & (km.level == c)]; ax.step(k.time, 100 * k.survival, color=col, lw=2, where="post", label=c)
    ax.fill_between(k.time, 100 * k.ci_low, 100 * k.ci_high, step="post", color=col, alpha=.12)
ax.set_title("Share of customers still active after N months"); ax.set_xlabel("Months since signup"); ax.set_ylabel("% still active")
ax.set_ylim(0, 100); ax.legend(frameon=False, fontsize=9); ax.grid(axis="y", color="#ECF0F1")
ax = panel(fig, [.04, .07, .93, .33])
pv = coh.pivot(index="cohort", columns="months_since_signup", values="retention_pct")
im = ax.imshow(pv.values, aspect="auto", cmap="Blues", vmin=30, vmax=100)
ax.set_xticks(range(len(pv.columns))); ax.set_xticklabels(pv.columns); ax.set_yticks(range(len(pv.index))); ax.set_yticklabels(pv.index, fontsize=8)
for (r_, c_), v in np.ndenumerate(pv.values):
    if not np.isnan(v): ax.text(c_, r_, f"{v:.0f}", ha="center", va="center", fontsize=7.5, color="white" if v > 70 else "#1B2631")
ax.set_title("Cohort retention: % of each signup quarter still active (darker = more retained)"); ax.set_xlabel("Months since signup")
for s in ax.spines.values(): s.set_visible(False)
fig.savefig(OUT / "preview_3_lifecycle.png", dpi=110); plt.close(fig)

# ---------------------------------------------------------------- Page 4: price + at-risk
fig = frame("Price Increase Impact & Customers at Risk", "Did the July 2025 price rise raise churn, and who should we contact first?", ["Plan", "Contract", "Risk band"])
pe = pd.read_csv(DS / "price_event_study.csv")
card(fig, .02, .72, .155, .115, "Price increase effect", "+1.39 pp", "95% CI +0.85 to +1.87", RED)
hi = risk[risk.risk_band == "High"]
card(fig, .185, .72, .155, .115, "High-risk customers", f"{len(hi):,}", f"{len(hi) / len(risk):.0%} of active base", RED)
card(fig, .35, .72, .155, .115, "MRR at risk (high-risk)", f"{hi.mrr_at_risk.sum() / 1e3:.0f}K", "risk % × MRR, next 3 months")
card(fig, .515, .72, .155, .115, "Expected churners, next 3M", f"{(risk.risk_pct / 100).sum():.0f}", "sum of individual risks")
ax = panel(fig, [.04, .08, .43, .55])
xs = pd.to_datetime(pe.year_month + "-01")
ax.plot(xs, pe.basic_churn_pct, color=GREY, lw=2, label="Basic (no price change)")
ax.plot(xs, pe.standard_premium_churn_pct, color=RED, lw=2, label="Standard/Premium (+10%)")
ax.axvline(pd.Timestamp("2025-07-01"), color=ORANGE, ls="--"); ax.text(pd.Timestamp("2025-07-10"), ax.get_ylim()[0] + .1, "Price rise", color=ORANGE, fontsize=8.5)
ax.set_title("Monthly churn %: price-rise plans vs unchanged plan"); ax.legend(frameon=False, fontsize=9); ax.grid(axis="y", color="#ECF0F1")
ax = panel(fig, [.52, .38, .21, .25])
rb = risk.groupby("risk_band").agg(n=("customer_id", "count"), r=("risk_pct", "mean")).loc[["High", "Medium", "Low"]]
ax.bar(rb.index, rb.n, color=[RED, ORANGE, GREEN]); ax.set_title("Customers by risk band")
for i, (n, r) in enumerate(zip(rb.n, rb.r)): ax.text(i, n + 30, f"{n:,}\n({r:.1f}% risk)", ha="center", fontsize=8)
ax.set_ylim(0, rb.n.max() * 1.25)
ax = panel(fig, [.76, .38, .21, .25])
ax.bar(rb.index, risk.groupby("risk_band").mrr_at_risk.sum().loc[rb.index] / 1e3, color=[RED, ORANGE, GREEN]); ax.set_title("MRR at risk (K)")
ax = panel(fig, [.52, .08, .45, .24]); ax.axis("off")
top = risk.nsmallest(8, "risk_decile").sort_values("mrr_at_risk", ascending=False).head(8)
tbl = ax.table(cellText=[[int(r.customer_id), f"{r.risk_pct:.1f}%", f"{r.mrr:,.0f}", int(r.tenure_months), int(r.tickets_3m)] for r in top.itertuples()],
               colLabels=["Customer", "Risk (3 mo)", "MRR", "Tenure (mo)", "Tickets (3 mo)"], loc="center", cellLoc="center")
tbl.auto_set_font_size(False); tbl.set_fontsize(8.5); tbl.scale(1, 1.15)
for (r_, c_), cell in tbl.get_celld().items():
    cell.set_edgecolor("#D5D8DC")
    if r_ == 0: cell.set_facecolor(NAVY); cell.set_text_props(color="white", fontweight="bold")
ax.set_title("Top at-risk customers by revenue exposure")
fig.savefig(OUT / "preview_4_price_and_risk.png", dpi=110); plt.close(fig)
print("done")
