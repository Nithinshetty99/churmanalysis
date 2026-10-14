import numpy as np
import pandas as pd

from churn_platform import simulate
from churn_platform.config import END_IDX, PRICE_HIKE_IDX


def test_reproducible_with_same_seed():
    a = simulate.simulate(simulate.SimConfig(200, seed=1))
    b = simulate.simulate(simulate.SimConfig(200, seed=1))
    pd.testing.assert_frame_equal(a[0], b[0])
    pd.testing.assert_frame_equal(a[1], b[1])


def test_different_seed_differs():
    a = simulate.simulate(simulate.SimConfig(200, seed=1))[0]
    b = simulate.simulate(simulate.SimConfig(200, seed=2))[0]
    assert not a["age"].equals(b["age"])


def test_customer_ids_unique(sim):
    customers, _, _ = sim
    assert customers["customer_id"].is_unique


def test_churned_customers_have_exactly_one_final_churn_row(sim):
    customers, months, _ = sim
    last = months.sort_values("month_idx").groupby("customer_id").tail(1).set_index("customer_id")
    flags = months.groupby("customer_id")["churned_this_month"].sum()
    assert (flags <= 1).all()
    churned = customers[customers["is_churned"] == 1]["customer_id"]
    assert (last.loc[churned, "churned_this_month"] == 1).all()
    active = customers[customers["is_churned"] == 0]["customer_id"]
    assert (last.loc[active, "month_idx"] == END_IDX).all()


def test_months_are_consecutive_and_match_observed_months(sim):
    customers, months, _ = sim
    g = months.groupby("customer_id")["month_idx"].agg(["min", "max", "count"])
    c = customers.set_index("customer_id")
    assert ((g["max"] - g["min"] + 1) == g["count"]).all()
    assert (g["min"] == c["signup_idx"]).all()
    assert (g["count"] == c["observed_months"]).all()


def test_price_hike_only_hits_standard_and_premium_after_hike(sim):
    customers, months, _ = sim
    m = months.merge(customers[["customer_id", "plan", "base_price"]], on="customer_id")
    ratio = m["mrr"] / m["base_price"]
    hiked = (m["plan"] != "Basic") & (m["month_idx"] >= PRICE_HIKE_IDX)
    assert np.allclose(ratio[hiked], 1.10, atol=1e-2)
    assert np.allclose(ratio[~hiked], 1.0, atol=1e-2)


def test_latent_state_is_not_written_to_csv(sim, tmp_path):
    simulate.write_csvs(*sim, out_dir=tmp_path)
    cols = pd.read_csv(tmp_path / "customer_months.csv", nrows=1).columns
    assert "latent_dissatisfaction" not in cols


def test_annual_contracts_churn_less_than_monthly(sim):
    customers, months, _ = sim
    m = months.merge(customers[["customer_id", "contract"]], on="customer_id")
    rate = m.groupby("contract")["churned_this_month"].mean()
    assert rate["Annual"] < rate["Monthly"]
