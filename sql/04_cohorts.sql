-- Cohort retention by signup quarter.

-- name: cohort_retention
-- retention at k = share of the cohort that still had an active row at tenure month k.
-- A cell is reported only if EVERY member of the cohort could have reached month k before the
-- observation window ended (right-censoring guard), otherwise retention would be biased upward.
WITH last_obs AS (
    SELECT MAX(month_idx) AS last_idx FROM customer_months
),
cohort AS (
    SELECT customer_id, signup_idx / 3 AS cohort_q, signup_idx FROM customers
),
size AS (
    SELECT cohort_q, COUNT(*) AS cohort_size, MAX(signup_idx) AS last_signup
    FROM cohort GROUP BY cohort_q
),
alive AS (
    SELECT co.cohort_q, cm.tenure_month AS k, COUNT(*) AS active
    FROM customer_months cm
    JOIN cohort co ON co.customer_id = cm.customer_id
    GROUP BY co.cohort_q, cm.tenure_month
)
SELECT s.cohort_q, s.cohort_size, a.k, a.active,
       ROUND(100.0 * a.active / s.cohort_size, 1) AS retention_pct
FROM size s
JOIN alive a ON a.cohort_q = s.cohort_q
CROSS JOIN last_obs lo
WHERE s.last_signup + a.k <= lo.last_idx
  AND a.k IN (0, 1, 2, 3, 6, 9, 12, 15, 18, 24)
ORDER BY s.cohort_q, a.k;

-- name: first_90_days_by_channel
-- Early-life churn: share of customers gone within their first 3 months, by acquisition channel.
-- Only customers who signed up early enough to be observed for 3 full months are included.
SELECT c.channel,
       COUNT(*) AS customers,
       ROUND(100.0 * AVG(CASE WHEN c.is_churned = 1 AND c.observed_months <= 3 THEN 1.0 ELSE 0.0 END), 2) AS churn_within_3m_pct
FROM customers c
WHERE c.signup_idx <= (SELECT MAX(month_idx) FROM customer_months) - 3
GROUP BY c.channel
ORDER BY churn_within_3m_pct DESC;
