-- Business KPIs. Queries are named so the Python pipeline can call them individually.

-- name: monthly_kpis
-- Active customers, new customers, churn, MRR, with 3-month rolling churn and MoM MRR change.
-- "Logo churn %" = customers whose last month is this month / customers active this month.
WITH m AS (
    SELECT month_idx, month,
           COUNT(*)                                                       AS active_customers,
           SUM(CASE WHEN tenure_month = 0 THEN 1 ELSE 0 END)              AS new_customers,
           SUM(churned_this_month)                                        AS churned_customers,
           SUM(mrr)                                                       AS mrr,
           SUM(CASE WHEN churned_this_month = 1 THEN mrr ELSE 0 END)      AS churned_mrr
    FROM customer_months
    GROUP BY month_idx, month
)
SELECT month_idx, month, active_customers, new_customers, churned_customers, mrr, churned_mrr,
       ROUND(100.0 * churned_customers / active_customers, 2) AS logo_churn_pct,
       ROUND(100.0 * churned_mrr / mrr, 2)                    AS revenue_churn_pct,
       ROUND(AVG(100.0 * churned_customers / active_customers)
             OVER (ORDER BY month_idx ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS logo_churn_3m_avg,
       mrr - LAG(mrr) OVER (ORDER BY month_idx)               AS mrr_change
FROM m
ORDER BY month_idx;

-- name: churn_by_dimension
-- IMPORTANT: compare segments on churn per customer-month (monthly hazard), NOT on "% ever churned".
-- Segments observed for different lengths have different chances to churn; raw % would mislead.
SELECT 'plan' AS dimension, plan AS level, COUNT(*) AS customers, SUM(is_churned) AS churned,
       ROUND(100.0 * AVG(is_churned), 1) AS pct_ever_churned,
       ROUND(100.0 * SUM(is_churned) / SUM(observed_months), 2) AS monthly_churn_pct
FROM customers GROUP BY plan
UNION ALL
SELECT 'contract', contract, COUNT(*), SUM(is_churned), ROUND(100.0 * AVG(is_churned), 1),
       ROUND(100.0 * SUM(is_churned) / SUM(observed_months), 2)
FROM customers GROUP BY contract
UNION ALL
SELECT 'channel', channel, COUNT(*), SUM(is_churned), ROUND(100.0 * AVG(is_churned), 1),
       ROUND(100.0 * SUM(is_churned) / SUM(observed_months), 2)
FROM customers GROUP BY channel
UNION ALL
SELECT 'location', location, COUNT(*), SUM(is_churned), ROUND(100.0 * AVG(is_churned), 1),
       ROUND(100.0 * SUM(is_churned) / SUM(observed_months), 2)
FROM customers GROUP BY location
UNION ALL
SELECT 'age_band',
       CASE WHEN age < 25 THEN '18-24' WHEN age < 35 THEN '25-34' WHEN age < 45 THEN '35-44'
            WHEN age < 55 THEN '45-54' ELSE '55+' END,
       COUNT(*), SUM(is_churned), ROUND(100.0 * AVG(is_churned), 1),
       ROUND(100.0 * SUM(is_churned) / SUM(observed_months), 2)
FROM customers
GROUP BY CASE WHEN age < 25 THEN '18-24' WHEN age < 35 THEN '25-34' WHEN age < 45 THEN '35-44'
              WHEN age < 55 THEN '45-54' ELSE '55+' END
ORDER BY dimension, level;

-- name: hazard_by_tenure
-- Empirical churn hazard at each tenure month: churners / customers at risk. Shows early-life
-- churn and the spikes at annual renewals (tenure 12, 24, 36).
SELECT c.contract, cm.tenure_month,
       COUNT(*)                                  AS at_risk,
       SUM(cm.churned_this_month)                AS churned,
       1.0 * SUM(cm.churned_this_month) / COUNT(*) AS hazard
FROM customer_months cm
JOIN customers c ON c.customer_id = cm.customer_id
WHERE cm.tenure_month <= 36
GROUP BY c.contract, cm.tenure_month
HAVING COUNT(*) >= 30
ORDER BY c.contract, cm.tenure_month;

-- name: engagement_vs_churn
-- Average behavior in the 3 months before leaving vs the same tenure window for stayers is hard
-- in plain SQL; this simpler view compares usage deciles with next-month churn.
WITH ranked AS (
    SELECT customer_id, month_idx, usage_hours, churned_this_month,
           NTILE(10) OVER (PARTITION BY month_idx ORDER BY usage_hours) AS usage_decile
    FROM customer_months
    WHERE tenure_month >= 3
)
SELECT usage_decile, COUNT(*) AS customer_months,
       ROUND(100.0 * AVG(churned_this_month), 2) AS monthly_churn_pct
FROM ranked
GROUP BY usage_decile
ORDER BY usage_decile;
