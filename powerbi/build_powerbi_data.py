"""Build the Power BI star schema from the pipeline output.

Run AFTER `python -m churn_platform.pipeline`:
    python powerbi/build_powerbi_data.py

Writes tidy CSVs to powerbi/dataset/ (this folder is committed so Power BI users do not need Python):
    dim_customer, dim_date, fact_customer_month, at_risk_customers,
    hazard_by_tenure, cohort_retention, survival_curves, price_event_study
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA, OUT, DST = ROOT / "data", ROOT / "outputs", ROOT / "powerbi" / "dataset"
DST.mkdir(parents=True, exist_ok=True)

AGE_BANDS = [(18, 24, "18-24"), (25, 34, "25-34"), (35, 44, "35-44"), (45, 54, "45-54"), (55, 200, "55+")]
TENURE_BANDS = [(0, 2, "0-2 months"), (3, 5, "3-5 months"), (6, 11, "6-11 months"),
                (12, 23, "12-23 months"), (24, 999, "24+ months")]


def band(s: pd.Series, bands) -> pd.Series:
    out = pd.Series(index=s.index, dtype="object")
    for lo, hi, label in bands:
        out[(s >= lo) & (s <= hi)] = label
    return out


def main() -> None:
    cust = pd.read_csv(DATA / "customers.csv")
    cm = pd.read_csv(DATA / "customer_months.csv")

    # ---- dim_customer
    dc = cust[["customer_id", "signup_month", "age", "location", "plan", "contract", "channel",
               "base_price", "is_churned", "churn_month", "observed_months"]].copy()
    dc["age_band"] = band(dc["age"], AGE_BANDS)
    dc["status"] = dc["is_churned"].map({1: "Churned", 0: "Active"})
    dc["price_group"] = dc["plan"].map({"Basic": "Basic (no price change)",
                                        "Standard": "Standard/Premium (+10% from Jul 2025)",
                                        "Premium": "Standard/Premium (+10% from Jul 2025)"})
    dc["signup_year"] = pd.to_datetime(dc["signup_month"]).dt.year
    dc.to_csv(DST / "dim_customer.csv", index=False)

    # ---- dim_date (one row per month)
    months = pd.date_range("2023-01-01", "2026-06-01", freq="MS")
    dd = pd.DataFrame({"month": months.strftime("%Y-%m-%d")})
    dd["year"] = months.year
    dd["quarter"] = "Q" + months.quarter.astype(str)
    dd["month_name"] = months.strftime("%b")
    dd["year_month"] = months.strftime("%Y-%m")
    dd["month_idx"] = range(len(months))
    dd["price_period"] = ["Before price increase" if m < pd.Timestamp("2025-07-01") else "After price increase"
                          for m in months]
    dd.to_csv(DST / "dim_date.csv", index=False)

    # ---- fact_customer_month
    fm = cm.copy()
    fm["tenure_band"] = band(fm["tenure_month"], TENURE_BANDS)
    fm["is_new_customer"] = (fm["tenure_month"] == 0).astype(int)
    fm.drop(columns=["month_idx"]).to_csv(DST / "fact_customer_month.csv", index=False)

    # ---- at_risk_customers (live base, scored by the gradient-boosting model)
    sc = pd.read_csv(OUT / "scored_current.csv")
    sc["risk_pct"] = (sc["risk"] * 100).round(2)
    # NOTE: in scored_current.csv decile 1 = HIGHEST predicted risk (mean 16%), decile 10 = lowest (2%).
    sc["risk_band"] = pd.cut(sc["risk_decile"], [0, 2, 4, 10], labels=["High", "Medium", "Low"]).astype(str)
    sc["mrr_at_risk"] = (sc["risk"] * sc["mrr"]).round(2)
    keep = ["customer_id", "tenure_months", "mrr", "usage_3m_avg", "tickets_3m", "failed_3m",
            "risk_pct", "risk_decile", "risk_band", "mrr_at_risk", "segment"]
    sc[keep].to_csv(DST / "at_risk_customers.csv", index=False)

    # ---- small pre-aggregated tables that DAX cannot easily reproduce (survival / cohort methods)
    pd.read_csv(OUT / "hazard_by_tenure.csv").to_csv(DST / "hazard_by_tenure.csv", index=False)
    coh = pd.read_csv(OUT / "cohort_retention.csv")
    coh["cohort"] = coh["cohort_q"].map(lambda q: f"{2023 + q // 4} Q{q % 4 + 1}")
    coh.rename(columns={"k": "months_since_signup"}).to_csv(DST / "cohort_retention.csv", index=False)
    km = pd.read_csv(OUT / "km_curves.csv")
    km[km["variable"].isin(["contract", "channel"])].to_csv(DST / "survival_curves.csv", index=False)
    pe = pd.read_csv(OUT / "price_event_study.csv")
    pe.insert(1, "year_month", pe["month_idx"].map(lambda i: f"{2023 + i // 12}-{i % 12 + 1:02d}"))
    pe.columns = ["month_idx", "year_month", "basic_churn_pct", "standard_premium_churn_pct", "gap_pp"]
    pe.to_csv(DST / "price_event_study.csv", index=False)

    for f in sorted(DST.glob("*.csv")):
        print(f"{f.name:28s} {sum(1 for _ in open(f)) - 1:>8,} rows")


if __name__ == "__main__":
    main()
