-- Data quality checks. Every query returns ONE row with a "violations" count; expected value is 0.
-- Run by the pipeline and asserted in tests/test_sql.py.

-- name: dq_orphan_months
SELECT COUNT(*) AS violations
FROM customer_months cm
LEFT JOIN customers c ON c.customer_id = cm.customer_id
WHERE c.customer_id IS NULL;

-- name: dq_customers_without_months
SELECT COUNT(*) AS violations
FROM customers c
LEFT JOIN customer_months cm ON cm.customer_id = c.customer_id
WHERE cm.customer_id IS NULL;

-- name: dq_rows_after_churn
SELECT COUNT(*) AS violations
FROM customer_months cm
JOIN customers c ON c.customer_id = cm.customer_id
WHERE c.churn_month_idx IS NOT NULL AND cm.month_idx > c.churn_month_idx;

-- name: dq_multiple_churn_rows
SELECT COUNT(*) AS violations
FROM (
    SELECT customer_id
    FROM customer_months
    GROUP BY customer_id
    HAVING SUM(churned_this_month) > 1
) t;

-- name: dq_churn_flag_mismatch
-- customers.is_churned must agree with the fact table, and churn_month_idx with the churn row.
SELECT COUNT(*) AS violations
FROM customers c
LEFT JOIN (
    SELECT customer_id, MAX(churned_this_month) AS f, MAX(CASE WHEN churned_this_month = 1 THEN month_idx END) AS m
    FROM customer_months GROUP BY customer_id
) x ON x.customer_id = c.customer_id
WHERE c.is_churned <> COALESCE(x.f, -1)
   OR COALESCE(c.churn_month_idx, -1) <> COALESCE(x.m, -1);

-- name: dq_month_gaps
-- Months for a customer must be consecutive: count = max tenure + 1, and first month = signup.
SELECT COUNT(*) AS violations
FROM (
    SELECT c.customer_id
    FROM customers c
    JOIN customer_months cm ON cm.customer_id = c.customer_id
    GROUP BY c.customer_id, c.signup_idx, c.observed_months
    HAVING COUNT(*) <> MAX(cm.tenure_month) + 1
        OR MIN(cm.month_idx) <> c.signup_idx
        OR COUNT(*) <> c.observed_months
) t;

-- name: dq_active_customers_with_churn_date
SELECT COUNT(*) AS violations
FROM customers
WHERE (is_churned = 0 AND churn_month_idx IS NOT NULL)
   OR (is_churned = 1 AND churn_month_idx IS NULL);

-- name: dq_table_sizes
SELECT (SELECT COUNT(*) FROM customers) AS customers,
       (SELECT COUNT(*) FROM customer_months) AS customer_months,
       (SELECT MIN(month_idx) FROM customer_months) AS first_month_idx,
       (SELECT MAX(month_idx) FROM customer_months) AS last_month_idx;
