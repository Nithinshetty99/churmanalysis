-- Two-table star-like schema.
--   customers        one row per customer (dimension)
--   customer_months  one row per customer per active month (fact table)
-- Month columns are integer indices (0 = 2023-01) alongside ISO dates, so cohort arithmetic
-- is portable across SQLite / PostgreSQL / MySQL.
--
-- Semantics: a customer has a row for every month they were active. If churned_this_month = 1,
-- that is their LAST month (they leave at month end), so the churned customer's MRR stops the next month.

DROP TABLE IF EXISTS customer_months;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id      INTEGER PRIMARY KEY,
    signup_idx       INTEGER     NOT NULL,
    signup_month     TEXT        NOT NULL,
    age              INTEGER     NOT NULL CHECK (age BETWEEN 18 AND 100),
    location         VARCHAR(20) NOT NULL CHECK (location IN ('Urban', 'Semi-Urban', 'Rural')),
    plan             VARCHAR(20) NOT NULL CHECK (plan IN ('Basic', 'Standard', 'Premium')),
    contract         VARCHAR(20) NOT NULL CHECK (contract IN ('Monthly', 'Annual')),
    channel          VARCHAR(20) NOT NULL,
    base_price       INTEGER     NOT NULL CHECK (base_price > 0),
    churn_month_idx  INTEGER,                      -- NULL while still active (censored)
    churn_month      TEXT,
    is_churned       SMALLINT    NOT NULL CHECK (is_churned IN (0, 1)),
    observed_months  INTEGER     NOT NULL CHECK (observed_months >= 1)
);

CREATE TABLE customer_months (
    customer_id         INTEGER  NOT NULL REFERENCES customers (customer_id),
    month_idx           INTEGER  NOT NULL,
    month               TEXT     NOT NULL,
    tenure_month        INTEGER  NOT NULL CHECK (tenure_month >= 0),
    usage_hours         NUMERIC  NOT NULL CHECK (usage_hours >= 0),
    sessions            INTEGER  NOT NULL CHECK (sessions >= 0),
    tickets             INTEGER  NOT NULL CHECK (tickets >= 0),
    failed_payment      SMALLINT NOT NULL CHECK (failed_payment IN (0, 1)),
    mrr                 NUMERIC  NOT NULL CHECK (mrr > 0),
    churned_this_month  SMALLINT NOT NULL CHECK (churned_this_month IN (0, 1)),
    PRIMARY KEY (customer_id, month_idx)
);

CREATE INDEX idx_cm_month   ON customer_months (month_idx);
CREATE INDEX idx_cm_tenure  ON customer_months (tenure_month);
CREATE INDEX idx_cust_plan  ON customers (plan, contract);
