"""The Power BI tables must reproduce the SQL results exactly.

The DAX measures in powerbi/measures.dax are simple sums and ratios of these columns, so if the pandas
equivalents below match the SQL outputs, the dashboard numbers will match too.
Needs powerbi/dataset/ (python powerbi/build_powerbi_data.py) and outputs/ from a pipeline run.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
DS, OUT = ROOT / "powerbi" / "dataset", ROOT / "outputs"
pytestmark = pytest.mark.skipif(not (DS / "fact_customer_month.csv").exists() or not (OUT / "monthly_kpis.csv").exists(),
                                reason="build the pipeline outputs and powerbi/dataset first")


@pytest.fixture(scope="module")
def star():
    return (pd.read_csv(DS / "dim_customer.csv"), pd.read_csv(DS / "fact_customer_month.csv"),
            pd.read_csv(DS / "dim_date.csv"))


def test_relationships_are_clean(star):
    dc, fm, dd = star
    assert dc["customer_id"].is_unique and dd["month"].is_unique
    assert fm["customer_id"].isin(dc["customer_id"]).all()      # no orphan facts
    assert fm["month"].isin(dd["month"]).all()
    assert not fm.duplicated(["customer_id", "month"]).any()    # one row per customer-month


def test_monthly_kpis_match_sql(star):
    _, fm, _ = star
    sql = pd.read_csv(OUT / "monthly_kpis.csv")
    g = fm.groupby("month").agg(active=("customer_id", "count"), churned=("churned_this_month", "sum"),
                                mrr=("mrr", "sum")).reset_index()
    m = sql.merge(g, on="month")
    assert len(m) == len(sql) == 42
    assert (m["active"] == m["active_customers"]).all()
    assert (m["churned"] == m["churned_customers"]).all()
    assert np.allclose(m["mrr_x"] if "mrr_x" in m else m["mrr"], sql["mrr"])
    # DAX: Monthly Churn Rate = DIVIDE(SUM(churned), COUNTROWS(fact))
    assert np.allclose((100 * m["churned"] / m["active"]).round(2), m["logo_churn_pct"])


def test_segment_churn_matches_sql(star):
    dc, fm, _ = star
    j = fm.merge(dc, on="customer_id")
    sql = pd.read_csv(OUT / "churn_by_dimension.csv")
    for dim, col in [("plan", "plan"), ("contract", "contract"), ("channel", "channel"),
                     ("location", "location"), ("age_band", "age_band")]:
        dax = (100 * j.groupby(col)["churned_this_month"].mean()).round(2)
        exp = sql[sql["dimension"] == dim].set_index("level")["monthly_churn_pct"]
        assert np.allclose(dax.sort_index(), exp.sort_index(), atol=0.011), dim


def test_headline_numbers(star):
    dc, fm, _ = star
    assert len(dc) == 10_000
    assert round(100 * fm["churned_this_month"].mean(), 2) == 3.01
    assert dc["status"].value_counts()["Churned"] == 4693


def test_risk_bands_are_ordered():
    s = pd.read_csv(DS / "at_risk_customers.csv")
    r = s.groupby("risk_band")["risk_pct"].mean()
    assert r["High"] > r["Medium"] > r["Low"]


def test_did_measure_logic_matches_pipeline(star):
    """Mirrors the DAX [Price Increase Effect (pp)] measure: windows 24-29 vs 30-35, treated vs Basic."""
    dc, fm, dd = star
    j = fm.merge(dc[["customer_id", "plan"]], on="customer_id").merge(dd[["month", "month_idx"]], on="month")

    def rate(plans, lo, hi):
        g = j[j["plan"].isin(plans) & j["month_idx"].between(lo, hi)]
        return g["churned_this_month"].mean()

    t, c = ["Standard", "Premium"], ["Basic"]
    did = 100 * ((rate(t, 30, 35) - rate(t, 24, 29)) - (rate(c, 30, 35) - rate(c, 24, 29)))
    assert did == pytest.approx(1.39, abs=0.01)
