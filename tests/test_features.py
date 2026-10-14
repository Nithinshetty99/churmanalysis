"""Leakage tests for the point-in-time feature query. These matter more than any model metric."""
import pandas as pd
import pytest

from churn_platform import simulate
from churn_platform.config import HORIZON
from churn_platform.db import build_db, run

SNAPS = [12, 24, 33]
FEATURE_COLS = ["customer_id", "plan", "contract", "channel", "location", "age", "snap_idx", "tenure_months", "mrr",
                "price_vs_base", "usage_3m_avg", "usage_trend", "usage_vs_lifetime", "sessions_3m", "tickets_3m", "failed_3m"]


@pytest.mark.parametrize("snap", SNAPS)
def test_features_use_no_data_after_snapshot(sim, queries, tmp_path, con, snap):
    """Delete every row after the snapshot, rebuild the features, and require identical values."""
    full = run(con, queries, "snapshot_features", snap=snap).sort_values("customer_id").reset_index(drop=True)
    simulate.write_csvs(*sim, out_dir=tmp_path)
    trunc = build_db(tmp_path, ":memory:")
    trunc.execute("DELETE FROM customer_months WHERE month_idx > ?", (snap,))
    cut = run(trunc, queries, "snapshot_features", snap=snap).sort_values("customer_id").reset_index(drop=True)
    pd.testing.assert_frame_equal(full[FEATURE_COLS], cut[FEATURE_COLS])
    assert cut["label"].sum() == 0          # with the future deleted, no label can be 1
    assert full["label"].sum() > 0          # and the full data does contain positives


@pytest.mark.parametrize("snap", SNAPS)
def test_label_matches_independent_pandas_calculation(sim, queries, con, snap):
    customers, months, _ = sim
    feats = run(con, queries, "snapshot_features", snap=snap)
    at_snap = months[(months["month_idx"] == snap) & (months["churned_this_month"] == 0)]["customer_id"]
    assert set(feats["customer_id"]) == set(at_snap)
    c = customers.set_index("customer_id").loc[feats["customer_id"]]
    expected = c["churn_month_idx"].between(snap + 1, snap + HORIZON).fillna(False).astype(int).to_numpy()
    assert (feats["label"].to_numpy() == expected).all()


@pytest.mark.parametrize("snap", SNAPS)
def test_snapshot_population_excludes_already_churned(sim, queries, con, snap):
    customers, _, _ = sim
    feats = run(con, queries, "snapshot_features", snap=snap)
    c = customers.set_index("customer_id").loc[feats["customer_id"]]
    assert not (c["churn_month_idx"] <= snap).any()


def test_feature_sanity(sim, queries, con):
    customers, _, _ = sim
    feats = run(con, queries, "snapshot_features", snap=24)
    c = customers.set_index("customer_id").loc[feats["customer_id"]]
    assert (feats["tenure_months"].to_numpy() == (24 - c["signup_idx"]).to_numpy()).all()
    assert (feats["mrr"] > 0).all()
    assert (feats["usage_3m_avg"] > 0).all()
    # usage_trend needs 6 months of history, so it is missing only for tenure < 5
    assert feats.loc[feats["tenure_months"] >= 5, "usage_trend"].notna().all()
    assert feats.loc[feats["tenure_months"] < 5, "usage_trend"].isna().all()


def test_temporal_split_labels_do_not_overlap():
    from churn_platform.config import END_IDX, TEST_SNAP, TRAIN_SNAPS, VAL_SNAP
    assert max(TRAIN_SNAPS) + HORIZON < VAL_SNAP + 1      # train label window ends before val labels start
    assert VAL_SNAP + HORIZON < TEST_SNAP + 1
    assert TEST_SNAP + HORIZON <= END_IDX                  # test labels are fully observed
