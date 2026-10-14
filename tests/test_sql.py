import sqlite3

import pytest

from churn_platform.db import run


def test_all_data_quality_checks_pass(con, queries):
    for name in [n for n in queries if n.startswith("dq_") and n != "dq_table_sizes"]:
        assert run(con, queries, name)["violations"].iloc[0] == 0, name


def test_data_quality_checks_can_actually_fail(sim, queries, tmp_path):
    """A check that never fires is worthless: corrupt a copy of the data and expect violations."""
    from churn_platform import simulate
    from churn_platform.db import build_db
    simulate.write_csvs(*sim, out_dir=tmp_path)
    bad = build_db(tmp_path, ":memory:")
    cid, cm = bad.execute("SELECT customer_id, churn_month_idx FROM customers WHERE is_churned = 1 LIMIT 1").fetchone()
    # add a billing row AFTER the churn month, and an orphan row
    bad.execute("INSERT INTO customer_months VALUES (?,?,?,?,?,?,?,?,?,?)", (cid, cm + 1, "x", 99, 1, 1, 0, 0, 100, 0))
    bad.commit()                              # PRAGMA foreign_keys is ignored inside an open transaction
    bad.execute("PRAGMA foreign_keys = OFF")
    bad.execute("INSERT INTO customer_months VALUES (?,?,?,?,?,?,?,?,?,?)", (999999, 5, "x", 0, 1, 1, 0, 0, 100, 0))
    assert run(bad, queries, "dq_rows_after_churn")["violations"].iloc[0] >= 1
    assert run(bad, queries, "dq_orphan_months")["violations"].iloc[0] >= 1
    assert run(bad, queries, "dq_month_gaps")["violations"].iloc[0] >= 1


def test_schema_rejects_invalid_values(con):
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO customers VALUES (999998, 0, 'x', 30, 'Urban', 'Gold', 'Monthly', 'Organic', 100, NULL, NULL, 0, 1)")


def test_monthly_churn_totals_match_customer_table(con, queries):
    k = run(con, queries, "monthly_kpis")
    total = con.execute("SELECT SUM(is_churned) FROM customers").fetchone()[0]
    assert k["churned_customers"].sum() == total


def test_mrr_waterfall_identity(con, queries):
    w = run(con, queries, "mrr_waterfall")
    resid = w["mrr"] - w["mrr"].shift() - w["new_mrr"] - w["expansion_mrr"] + w["churned_mrr"]
    assert resid.iloc[1:].abs().max() < 1e-6


def test_cohort_retention_starts_at_100_and_never_increases(con, queries):
    c = run(con, queries, "cohort_retention")
    assert (c[c["k"] == 0]["retention_pct"] == 100).all()
    for _, g in c.groupby("cohort_q"):
        assert g.sort_values("k")["retention_pct"].is_monotonic_decreasing


def test_cohort_cells_respect_censoring(con, queries):
    """No cell may be reported for a month some cohort member could not yet have reached."""
    c = run(con, queries, "cohort_retention")
    last = con.execute("SELECT MAX(month_idx) FROM customer_months").fetchone()[0]
    for _, row in c.iterrows():
        last_signup = con.execute("SELECT MAX(signup_idx) FROM customers WHERE signup_idx/3 = ?", (int(row["cohort_q"]),)).fetchone()[0]
        assert last_signup + row["k"] <= last


def test_hazard_values_are_probabilities(con, queries):
    h = run(con, queries, "hazard_by_tenure")
    assert h["hazard"].between(0, 1).all()


def test_churn_by_dimension_covers_every_customer_once_per_dimension(con, queries):
    d = run(con, queries, "churn_by_dimension")
    n = con.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    assert (d.groupby("dimension")["customers"].sum() == n).all()
