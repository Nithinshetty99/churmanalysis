-- Point-in-time feature table for churn prediction.
--
-- For snapshot month :snap, one row per customer active at the end of that month, with:
--   * features computed ONLY from months <= :snap   (no future information)
--   * label = 1 if the customer churns in months :snap+1 .. :snap+3
-- tests/test_features.py proves the no-leakage property by rebuilding the features after deleting
-- every row beyond :snap and checking they are identical.

-- name: snapshot_features
WITH active AS (
    SELECT c.customer_id, c.plan, c.contract, c.channel, c.location, c.age, c.base_price, c.signup_idx
    FROM customers c
    JOIN customer_months cm ON cm.customer_id = c.customer_id AND cm.month_idx = :snap
    WHERE cm.churned_this_month = 0      -- still a customer after the snapshot month
),
recent AS (
    SELECT cm.customer_id,
           SUM(CASE WHEN cm.month_idx > :snap - 3 THEN cm.usage_hours END)                          AS usage_sum_3m,
           SUM(CASE WHEN cm.month_idx > :snap - 3 THEN 1 ELSE 0 END)                                AS months_3m,
           SUM(CASE WHEN cm.month_idx > :snap - 3 THEN cm.sessions ELSE 0 END)                      AS sessions_3m,
           SUM(CASE WHEN cm.month_idx > :snap - 3 THEN cm.tickets ELSE 0 END)                       AS tickets_3m,
           SUM(CASE WHEN cm.month_idx > :snap - 3 THEN cm.failed_payment ELSE 0 END)                AS failed_3m,
           SUM(CASE WHEN cm.month_idx <= :snap - 3 AND cm.month_idx > :snap - 6
                    THEN cm.usage_hours END)                                                        AS usage_sum_prev3m,
           SUM(CASE WHEN cm.month_idx <= :snap - 3 AND cm.month_idx > :snap - 6 THEN 1 ELSE 0 END)  AS months_prev3m,
           AVG(cm.usage_hours)                                                                      AS usage_lifetime_avg,
           MAX(CASE WHEN cm.month_idx = :snap THEN cm.mrr END)                                      AS mrr
    FROM customer_months cm
    WHERE cm.month_idx <= :snap
    GROUP BY cm.customer_id
),
future AS (
    SELECT customer_id, 1 AS churn_next_3m
    FROM customer_months
    WHERE churned_this_month = 1 AND month_idx BETWEEN :snap + 1 AND :snap + 3
    GROUP BY customer_id
)
SELECT a.customer_id, a.plan, a.contract, a.channel, a.location, a.age,
       :snap                                                         AS snap_idx,
       :snap - a.signup_idx                                          AS tenure_months,
       r.mrr,
       r.mrr / a.base_price                                          AS price_vs_base,
       1.0 * r.usage_sum_3m / r.months_3m                            AS usage_3m_avg,
       CASE WHEN r.months_prev3m = 3
            THEN (1.0 * r.usage_sum_3m / r.months_3m) / (r.usage_sum_prev3m / r.months_prev3m)
       END                                                           AS usage_trend,
       (1.0 * r.usage_sum_3m / r.months_3m) / r.usage_lifetime_avg   AS usage_vs_lifetime,
       r.sessions_3m, r.tickets_3m, r.failed_3m,
       COALESCE(f.churn_next_3m, 0)                                  AS label
FROM active a
JOIN recent r ON r.customer_id = a.customer_id
LEFT JOIN future f ON f.customer_id = a.customer_id;
