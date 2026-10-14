"""Load the CSVs into SQLite and run named SQL queries.

Queries live in sql/*.sql and are separated by `-- name: <query_name>` markers.
Named parameters (:snap) are bound by sqlite3, never string-formatted.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd

from .config import DATA_DIR, SQL_DIR


def build_db(data_dir: Path = DATA_DIR, db_path: str | Path = ":memory:", sql_dir: Path = SQL_DIR) -> sqlite3.Connection:
    """Create the schema and load customers and customer_months from CSV."""
    if db_path != ":memory:" and Path(db_path).exists():
        Path(db_path).unlink()
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript((sql_dir / "01_schema.sql").read_text())
    cust = pd.read_csv(data_dir / "customers.csv")
    cust["churn_month_idx"] = cust["churn_month_idx"].astype("Int64").astype(object).where(cust["churn_month_idx"].notna(), None)
    cust["churn_month"] = cust["churn_month"].astype(object).where(cust["churn_month"].notna(), None)
    cust.to_sql("customers", con, if_exists="append", index=False)
    pd.read_csv(data_dir / "customer_months.csv").to_sql(
        "customer_months", con, if_exists="append", index=False, chunksize=50_000)
    con.commit()
    return con


def load_queries(sql_dir: Path = SQL_DIR) -> dict[str, str]:
    """Parse every sql/*.sql file into {name: statement}."""
    queries: dict[str, str] = {}
    for path in sorted(sql_dir.glob("*.sql")):
        text = path.read_text()
        parts = re.split(r"^-- name:\s*(\w+)\s*$", text, flags=re.MULTILINE)
        for name, body in zip(parts[1::2], parts[2::2]):
            queries[name] = body.strip().rstrip(";")
    return queries


def run(con: sqlite3.Connection, queries: dict[str, str], name: str, **params) -> pd.DataFrame:
    if name not in queries:
        raise KeyError(f"unknown query {name!r}")
    return pd.read_sql_query(queries[name], con, params=params)
