"""Shared constants. Months are integer indices: 0 = 2023-01, 41 = 2026-06."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "outputs"
FIG_DIR = OUT_DIR / "figures"
SQL_DIR = ROOT / "sql"

START_YEAR = 2023
END_IDX = 41            # last observed month (2026-06); customers active then are censored
LAST_SIGNUP_IDX = 35    # no signups in the final 6 months
PRICE_HIKE_IDX = 30     # 2025-07: +10% on Standard and Premium
HORIZON = 3             # prediction horizon in months

# Temporal split. Each snapshot's label window is the next HORIZON months,
# so train labels (<= month 33) never overlap the validation labels (34-36) or test labels (39-41).
TRAIN_SNAPS = [12, 15, 18, 21, 24, 27, 30]
VAL_SNAP = 33
TEST_SNAP = 38
CURRENT_SNAP = END_IDX  # score the live customer base; outcomes not yet observed


def month_label(idx: int) -> str:
    """Integer month index -> 'YYYY-MM-01'."""
    return f"{START_YEAR + idx // 12}-{idx % 12 + 1:02d}-01"


def month_short(idx: int) -> str:
    return month_label(idx)[:7]
