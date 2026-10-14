import numpy as np
import pandas as pd

from churn_platform import campaign, hazard, modeling, price_change, survival


# ---------------------------------------------------------------- survival
def test_km_matches_empirical_survival_without_censoring():
    rng = np.random.default_rng(0)
    d = rng.integers(1, 20, 500)
    km = survival.kaplan_meier(d, np.ones_like(d))
    for t in (1, 5, 10, 19):
        assert np.isclose(km.loc[km["time"] == t, "survival"].iloc[0], np.mean(d > t))


def test_km_hand_computed_example_with_censoring():
    km = survival.kaplan_meier([1, 2, 3, 4], [1, 0, 1, 0]).set_index("time")
    assert np.isclose(km.loc[1, "survival"], 0.75)
    assert np.isclose(km.loc[2, "survival"], 0.75)
    assert np.isclose(km.loc[3, "survival"], 0.375)
    assert np.isclose(km.loc[4, "survival"], 0.375)


def test_km_confidence_band_brackets_estimate():
    rng = np.random.default_rng(1)
    d = rng.integers(1, 30, 400)
    e = rng.integers(0, 2, 400)
    km = survival.kaplan_meier(d, e)
    assert (km["ci_low"] <= km["survival"] + 1e-12).all() and (km["survival"] <= km["ci_high"] + 1e-12).all()
    assert km["survival"].is_monotonic_decreasing


def test_logrank_detects_difference_and_is_symmetric():
    rng = np.random.default_rng(2)
    a = rng.exponential(10, 400).astype(int) + 1
    b = rng.exponential(20, 400).astype(int) + 1
    d = np.concatenate([a, b]); e = np.ones(len(d), int); g = np.array(["a"] * 400 + ["b"] * 400)
    r1 = survival.logrank_test(d, e, g)
    r2 = survival.logrank_test(d, e, np.where(g == "a", "z", "b"))   # relabel groups
    assert r1["p_value"] < 1e-6
    assert np.isclose(r1["chi2"], r2["chi2"])


def test_logrank_does_not_flag_identical_groups():
    rng = np.random.default_rng(3)
    d = rng.exponential(12, 1000).astype(int) + 1
    g = rng.choice(["a", "b", "c"], 1000)
    assert survival.logrank_test(d, np.ones(1000, int), g)["p_value"] > 0.01


# ---------------------------------------------------------------- hazard regression
def test_fit_logit_recovers_known_coefficients():
    rng = np.random.default_rng(4)
    n = 60_000
    X = pd.DataFrame({"x1": rng.normal(size=n), "x2": rng.integers(0, 2, n).astype(float)})
    true = np.array([-2.0, 0.8, -0.5])
    p = 1 / (1 + np.exp(-(true[0] + true[1] * X["x1"] + true[2] * X["x2"])))
    y = (rng.random(n) < p).astype(float)
    fit = hazard.fit_logit(X, y)
    assert (np.abs(fit["coef"].to_numpy() - true) < 4 * fit["se"].to_numpy()).all()


def test_recovery_table_oracle_spec_is_close_to_truth(sim):
    customers, months, _ = sim
    rec = hazard.recovery_table(months, customers)
    # small sample: require the strongest, best-identified effects to be within 3 SE under the oracle spec
    strong = rec[rec["term"].isin(["annual_contract", "annual_renewal_month", "price_hike"])]
    assert ((strong["est_C"] - strong["true"]).abs() < 3 * strong["se_C"]).all()


# ---------------------------------------------------------------- modeling metrics
def test_evaluate_perfect_and_random_scores():
    y = np.array([0] * 90 + [1] * 10)
    perfect = modeling.evaluate(y, y.astype(float))
    assert perfect["roc_auc"] == 1.0 and perfect["recall_top10"] == 1.0
    assert np.isclose(perfect["lift_top10"], 10.0)
    # random scores: use many positives, otherwise AUC noise (SE ~0.09 with 10 positives) swamps the check
    y_big = (np.random.default_rng(1).random(20_000) < 0.1).astype(int)
    rnd = modeling.evaluate(y_big, np.random.default_rng(0).random(20_000))
    assert 0.47 < rnd["roc_auc"] < 0.53


def test_lift_and_calibration_tables_are_consistent():
    rng = np.random.default_rng(5)
    p = rng.random(2000) * 0.3
    y = (rng.random(2000) < p).astype(int)
    lift = modeling.lift_table(y, p)
    assert lift["customers"].sum() == 2000
    assert np.isclose(lift["cum_capture"].iloc[-1], 1.0)
    assert lift["lift"].iloc[0] > lift["lift"].iloc[-1]
    cal = modeling.calibration_table(y, p)
    assert cal["customers"].sum() == 2000


def test_model_pipeline_fits_and_handles_missing_values():
    rng = np.random.default_rng(6)
    n = 500
    df = pd.DataFrame({c: rng.normal(size=n) for c in modeling.NUM})
    df["usage_trend"] = df["usage_trend"].where(rng.random(n) > 0.2)   # 20% missing
    for c in modeling.CAT:
        df[c] = rng.choice(["a", "b", "c"], n)
    y = (rng.random(n) < 0.3).astype(int)
    for kind in ("logit", "gbm"):
        m = modeling.make_model(kind).fit(modeling.features_of(df, modeling.NUM, modeling.CAT), y)
        p = m.predict_proba(modeling.features_of(df, modeling.NUM, modeling.CAT))[:, 1]
        assert p.shape == (n,) and np.isfinite(p).all() and ((0 <= p) & (p <= 1)).all()


# ---------------------------------------------------------------- campaign
def _scored(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    risk = rng.random(n) * 0.3
    return pd.DataFrame({"risk": risk, "label": (rng.random(n) < risk).astype(int), "mrr": rng.uniform(300, 1200, n)})


def test_campaign_zero_contacts_is_zero_and_full_contact_equal_across_strategies():
    cu = campaign.campaign_curves(_scored())
    assert (cu[cu["contacted"] == 0]["realized_net"] == 0).all()
    full = cu[cu["contacted"] == cu["contacted"].max()].groupby("strategy")["realized_net"].first()
    assert np.allclose(full.to_numpy(), full.iloc[0])


def test_campaign_with_perfect_foresight_beats_random():
    s = _scored()
    s["risk"] = s["label"].astype(float)          # oracle ranking
    best = campaign.best_point(campaign.campaign_curves(s)).set_index("strategy")["realized_net"]
    assert best["by risk"] > best["random"]


def test_campaign_value_rises_with_save_rate():
    s = _scored()
    lo = campaign.sensitivity_grid(s, save_rates=(0.05,), costs=(100,))["net_at_best"].iloc[0]
    hi = campaign.sensitivity_grid(s, save_rates=(0.30,), costs=(100,))["net_at_best"].iloc[0]
    assert hi > lo


def test_breakeven_save_rate():
    assert np.isclose(campaign.breakeven_save_rate(50, 100, 12), 100 / (50 * 12))


# ---------------------------------------------------------------- difference-in-differences
def test_did_recovers_known_effect_on_synthetic_panel():
    rng = np.random.default_rng(7)
    n = 6000
    plan = rng.choice(["Basic", "Standard"], n)
    rows = []
    for t in range(24, 36):
        treated = plan != "Basic"
        post = t >= 30
        p = np.where(treated, 0.025 + 0.015 * post, 0.03)    # true DiD = +1.5 pp
        rows.append(pd.DataFrame({"customer_id": np.arange(n), "month_idx": t,
                                  "churned_this_month": (rng.random(n) < p).astype(int)}))
    months = pd.concat(rows)
    customers = pd.DataFrame({"customer_id": np.arange(n), "plan": plan})
    est = price_change.did_estimate(months, customers, n_boot=150)
    assert est["ci_low"] < 1.5 < est["ci_high"]
    assert 0.8 < est["did_pp"] < 2.2
