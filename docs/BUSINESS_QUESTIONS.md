# Business questions

Each question maps to the SQL that answers it, the Power BI page where a non-technical user sees it,
and the answer in this (simulated) dataset. Queries are in `sql/`; the named query is the `-- name:` marker.

| # | Business question | SQL (file : query) | Dashboard page | Answer (seed 42) |
|---|---|---|---|---|
| 1 | What is our churn rate, and is it improving? | `03_kpis` : `monthly_kpis` | 1 Overview | 3.01% of active customers leave per month; 3-month average stays between 2.5% and 3.6% after the first 8 months (early months are noisier because the base is tiny) |
| 2 | How many customers do we have and how much revenue do they bring? | `03_kpis` : `monthly_kpis`, `05_revenue` : `mrr_waterfall` | 1 Overview | 10,000 customers served; 5,470 billed in Jun 2026, of whom 5,307 are still active after month end; MRR 3.19M |
| 3 | Which customer groups churn most? | `03_kpis` : `churn_by_dimension` | 2 Segments | Monthly contract 3.82% vs annual 1.84%; Social 3.57% vs Referral 2.37%; age 18-24 3.80% vs 55+ 2.15% |
| 4 | When in the customer lifetime do people leave? | `03_kpis` : `hazard_by_tenure` | 3 Lifecycle | Monthly: 8.5% in month 1, falling to about 3% by month 6. Annual: about 1% normally, 13.6% / 11.3% / 15.6% at months 12 / 24 / 36 |
| 5 | Do newer cohorts retain better or worse? | `04_cohorts` : `cohort_retention` | 3 Lifecycle | Cohort matrix; cells shown only when every cohort member could have reached that age |
| 6 | Which acquisition channel brings durable customers? | `04_cohorts` : `first_90_days_by_channel` | 2 Segments | 90-day churn: Referral 11.2%, Organic 13.8%, Paid Search 16.0%, Social 17.4% |
| 7 | Did the July 2025 price rise increase churn? | `03_kpis` : `monthly_kpis`; `price_change.py` (DiD) | 4 Price & risk | +1.39 pp monthly churn on Standard/Premium (95% CI +0.85 to +1.87) |
| 8 | Where is revenue concentrated and how much do we lose to churn? | `05_revenue` : `revenue_by_segment`, `revenue_concentration`, `mrr_waterfall` | 1 Overview | Revenue churn 3.02% of billed MRR; top 2 revenue deciles hold 37.6% of billed revenue |
| 9 | Does low engagement signal churn? | `03_kpis` : `engagement_vs_churn` | 3 Lifecycle | Monthly churn 4.30% in the lowest usage decile vs 1.40% in the highest (association, not cause) |
| 10 | Which live customers should we contact first? | `06_features` : `snapshot_features` + model | 4 Price & risk | 1,062 high-risk customers (avg 13.9% 3-month risk) with 95K MRR at risk; top 20% of scores catch 40.7% of churners |
| 11 | Can we trust the data? | `02_data_quality` : 7 `dq_*` checks | n/a | All 7 pass; `tests/test_sql.py` proves they fire on corrupted data |

**Measurement note.** Segments are compared on churn per customer-month, not "% who ever churned", because
groups are observed for different lengths of time. `pct_ever_churned` is in the output for reference only.
