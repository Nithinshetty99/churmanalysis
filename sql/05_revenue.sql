-- Revenue analysis.

-- name: mrr_waterfall
-- Month-over-month MRR bridge:  mrr_t = mrr_(t-1) + new + expansion - churned
-- "expansion" here is the 2025-07 price increase. Churned MRR is booked the month AFTER the
-- customer's last month (when billing stops). The identity is asserted in tests/test_sql.py.
WITH cm AS (
    SELECT customer_id, month_idx, mrr, tenure_month,
           LAG(mrr) OVER (PARTITION BY customer_id ORDER BY month_idx) AS prev_mrr
    FROM customer_months
),
mv AS (
    SELECT month_idx,
           SUM(CASE WHEN tenure_month = 0 THEN mrr ELSE 0 END)                                AS new_mrr,
           SUM(CASE WHEN prev_mrr IS NOT NULL AND mrr > prev_mrr THEN mrr - prev_mrr ELSE 0 END) AS expansion_mrr
    FROM cm GROUP BY month_idx
),
lost AS (
    SELECT month_idx + 1 AS month_idx, SUM(mrr) AS churned_mrr
    FROM customer_months WHERE churned_this_month = 1
    GROUP BY month_idx
),
tot AS (
    SELECT month_idx, SUM(mrr) AS mrr FROM customer_months GROUP BY month_idx
)
SELECT tot.month_idx, tot.mrr,
       mv.new_mrr, mv.expansion_mrr, COALESCE(lost.churned_mrr, 0) AS churned_mrr,
       tot.mrr - LAG(tot.mrr) OVER (ORDER BY tot.month_idx) AS net_change
FROM tot
JOIN mv ON mv.month_idx = tot.month_idx
LEFT JOIN lost ON lost.month_idx = tot.month_idx
ORDER BY tot.month_idx;

-- name: revenue_by_segment
-- Billed revenue to date and observed lifetime by plan and contract. "billed" is history, not
-- predicted customer lifetime value: active customers are still accumulating revenue.
SELECT c.plan, c.contract,
       COUNT(DISTINCT c.customer_id)                         AS customers,
       ROUND(SUM(cm.mrr), 0)                                 AS billed_to_date,
       ROUND(SUM(cm.mrr) / COUNT(DISTINCT c.customer_id), 0) AS billed_per_customer,
       ROUND(1.0 * COUNT(*) / COUNT(DISTINCT c.customer_id), 1) AS avg_observed_months
FROM customer_months cm
JOIN customers c ON c.customer_id = cm.customer_id
GROUP BY c.plan, c.contract
ORDER BY billed_to_date DESC;

-- name: revenue_concentration
-- Share of current MRR by MRR decile (window function: NTILE). With only a few price points,
-- many customers tie, so which tied customers land in which decile is arbitrary; read it as a
-- rough concentration view, not exact decile membership.
WITH cur AS (
    SELECT customer_id, mrr FROM customer_months
    WHERE month_idx = (SELECT MAX(month_idx) FROM customer_months)
),
b AS (SELECT mrr, NTILE(10) OVER (ORDER BY mrr DESC) AS decile FROM cur)
SELECT decile, COUNT(*) AS customers, ROUND(SUM(mrr), 0) AS mrr,
       ROUND(100.0 * SUM(mrr) / (SELECT SUM(mrr) FROM cur), 1) AS pct_of_mrr
FROM b GROUP BY decile ORDER BY decile;
