# Findings and methodology

All numbers come from `python -m churn_platform.pipeline` (seed 42, 10,000 customers) and are in `outputs/`.

## 0. How to read this

The data are **simulated**. Churn is generated from a monthly hazard model with known coefficients (`churn_platform/simulate.py`). That makes this project useful for two things only:

1. showing a full analytics workflow (SQL, survival, prediction, causal-style analysis) that would run on real data;
2. **validating the methods**, because the truth is known and estimates can be scored against it.

It says nothing about real customers. Every "finding" below is a finding about the simulator or about how well a method recovers it. A real dataset (for example a public telecom churn set) would have different answers and messier problems.

The earlier version of this project had a different flaw: churn was set by `if` rules, so the patterns were circular. Here the mechanism is probabilistic, documented, and includes a hidden variable that the analyst cannot see, which is closer to real life.

## 1. Data

| Table | Rows | Content |
|---|---|---|
| `customers` | 10,000 | signup month, age, location, plan, contract, channel, churn month (NULL if active), observed months |
| `customer_months` | 156,065 | one row per active customer-month: usage hours, sessions, tickets, failed payment, MRR, churned-this-month flag |

Window: 2023-01 to 2026-06 (42 months). Signups run 2023-01 to 2025-12, then stop. A **price increase of 10% on Standard and Premium** takes effect in 2025-07.

**Definitions**
- A customer's last active month is the one flagged `churned_this_month = 1`; billing stops the following month.
- *Logo churn %* = customers whose last month is month t divided by customers active in t.
- *Censoring*: customers still active in 2026-06 have not churned *yet*. Comparisons use monthly churn per customer-month and Kaplan-Meier curves, not "% ever churned", because that percentage depends on how long each segment has been observed.

**Hidden variable.** A latent "dissatisfaction" state (AR(1), never written to the data) raises churn and also lowers usage and raises tickets and failed payments. So usage and tickets *predict* churn but are symptoms, not causes.

**Simulation artifact to ignore.** The customer base peaks at 6,537 in 2025-12 and then shrinks only because the simulator stops signups. It is not a business finding.

## 2. Data quality

Seven SQL checks (`sql/02_data_quality.sql`) run inside the pipeline as a gate and all return 0 violations: orphan rows, customers without months, rows after churn, multiple churn rows, flag mismatches, month gaps, active customers with a churn date. `tests/test_sql.py` also corrupts a copy of the data and confirms the checks fire, so they are not vacuous. There are no missing values or duplicates by construction; with real data this is where imputation and deduplication decisions would be documented.

## 3. Descriptive findings

- **Scale:** 46.9% of customers have churned; average monthly logo churn is 3.0%. MRR in 2026-06 is 3.19 million.
- **Contract is the dominant structural factor.** Monthly churn per customer-month is 3.82% (monthly contracts) vs 1.84% (annual). Twelve-month survival is 85.1% vs 60.6% (log-rank p < 10^-100).
- **Annual contracts do not remove churn; they move it to renewal.** Hazard is roughly 0.3 to 1.5% in ordinary months but 13.6% at month 12, 11.3% at month 24 and 15.6% at month 36. Monthly-contract customers show early-life churn instead: 8.5% in their first month, falling to about 3% by month 6.
- **Acquisition channel:** Referral customers churn least (2.37% per month; 11.2% leave within 90 days) and Social most (3.57%; 17.4%). Paid Search is close to Social.
- **Age gradient:** monthly churn falls steadily from 3.80% (18 to 24) to 2.15% (55+).
- **Location effect is small:** Urban 3.25%, Rural 2.67%.
- **Plan differences are confounded by the price increase.** Standard (3.27%) looks worse than Premium (2.81%) and Basic (2.89%), but Standard and Premium were the plans that received the hike. Reading this table as a plan effect would be wrong; see section 5.
- **Usage:** monthly churn is 4.30% in the lowest usage decile and 1.40% in the highest. This is an association; because usage is partly a symptom of the latent state, it does not show that raising usage would reduce churn.
- **Revenue:** monthly-contract Premium customers have the highest billed revenue to date (19.95 million), but annual customers have longer observed lifetimes and higher billed revenue per customer within each plan.

## 4. Can we recover the true drivers? (`hazard.py`)

A person-period logistic regression was fitted three ways and compared with the known coefficients:

| Spec | Adds | Coefficients within 95% CI of truth |
|---|---|---|
| A | structural variables only (contract, plan, channel, location, age, failed payment, price hike) | 8 of 12 |
| B | A + usage and ticket proxies | 11 of 12 |
| C | A + the true latent state (impossible in practice) | 11 of 12 |

The cleanest lesson is the failed-payment coefficient (true value 0.70): **0.93 in A, 0.84 in B, 0.66 in C**. Failed payments look too harmful when the hidden state is omitted, because they carry part of its signal. Annual-contract and renewal effects are also off in A and exact in C. This is omitted-variable bias, and because spec C exists the explanation is tested rather than assumed.

The one remaining miss in C (Premium plan, z = -2.0) is consistent with chance: with 12 coefficients, about one is expected outside a 95% interval.

## 5. Did the price increase raise churn? (`price_change.py`)

Difference-in-differences: Standard and Premium customers (treated) vs Basic (control), six months before vs six months after 2025-07.

- Estimate: **+1.39 percentage points** of monthly churn (95% cluster-bootstrap CI +0.85 to +1.87).
- True effect in the simulation: **+1.32 pp**. The interval covers it.
- Pre-period check: the treated-minus-control gap trends at -0.007 pp per month (SE 0.027), so there is no sign of diverging trends beforehand.

**What this does and does not show.** The method worked here because the simulator satisfies parallel trends by construction. Parallel trends cannot be proven on real data; plan was not randomized; and the interval reflects sampling error only. On real data this would be evidence about the hike, not proof.

## 6. Prediction (`modeling.py`)

Task: for customers active at a month end, predict churn within the next 3 months using only information up to that month. Features come from one SQL query (`sql/06_features.sql`). The split is strictly temporal: train on snapshots 2024-01 to 2025-07 (every 3 months), choose hyperparameters on 2025-10, report once on 2026-03 (outcome April to June 2026). Train, validation and test label windows do not overlap (asserted in `tests/test_features.py`).

| Model (test set, n = 5,796, base rate 8.4%) | ROC AUC | PR AUC | Lift, top 10% | Churners caught, top 20% |
|---|---|---|---|---|
| Baseline: tenure + contract | 0.546 | 0.097 | 1.23x | 24.1% |
| Logistic regression, all features | 0.654 | 0.153 | 2.23x | 36.8% |
| Gradient boosting (depth 3, lr 0.03) | **0.693** | 0.165 | 2.35x | 40.7% |

- The gain over the baseline comes from behavioral features, as expected given the latent state.
- The model is **moderately** useful, not strong. Most churn in the simulator is random draws from a hazard of roughly 3% a month, which limits any model. I did not compute the best achievable AUC, so I cannot say how close 0.69 is to that ceiling.
- **Calibration:** good in the lower deciles; the upper deciles under-predict (the third-highest risk decile predicted 10.0% and observed 13.3%; the top decile predicted 17.4% and observed 19.8%). Probabilities should be recalibrated before use in money terms.
- **Permutation importance (AUC drop):** contract 0.074, tenure 0.062, usage vs own lifetime 0.030, price vs base 0.019, channel 0.011. Importance describes predictive usefulness, not causal effect, and correlated features share credit.
- Failed payments have near-zero importance here. They are rare (about 4% of months) and their effect on the same-month hazard does not carry far into a 3-month window.

## 7. Segments and campaign backtest

**Segments** (k-means on tenure, usage, MRR, tickets, usage vs lifetime; k = 5 chosen by silhouette). The silhouette is only **0.22**, meaning weak separation; these are convenience groupings, not natural types. The highest-risk segment (8.4% of customers, about 2.3 tickets per 3 months, mean predicted risk 9.2%) and the lowest (15% of customers, usage 34% above their own average, risk 4.2%) are the most distinct.

**Campaign value** (`campaign.py`). The data contain no campaign, so the save rate is **unknowable here**. The backtest therefore shows sensitivity, not a recommendation. Using the actual test outcomes and ranking by expected revenue at risk (risk times MRR), over a 12-month protected horizon:

| Save rate | Cost per contact | Best share to contact | Net value at that share | Net value contacting everyone |
|---|---|---|---|---|
| 5% | 100 | 2% | 3,005 | -397,260 |
| 10% | 100 | 27% | 73,186 | -214,920 |
| 20% | 100 | 39% | 313,427 | 149,760 |
| 30% | 100 | 62% | 643,226 | 514,440 |

The best contact depth swings from almost nobody to most customers depending on an assumption nobody here can estimate. The "best share" is also chosen with hindsight on the same outcomes, so net values are upper bounds; in practice the depth would be set on a validation snapshot, and the save rate would come from a randomized holdout test.

## 8. Correlation, causation, and what is actually causal

- Churn here is caused by the simulator's mechanism; the code makes that known. In real data none of this is knowable, and the same tables could not distinguish cause from symptom.
- Usage, tickets and failed payments are **symptoms** of a hidden state. The failed-payment bias in section 4 shows how an observational coefficient can overstate a harm even with 150,000 observations.
- The price-increase estimate is the only causal-style claim, and it depends on parallel trends.
- The campaign analysis assumes an effect it cannot measure.

## 9. Limitations

- One simulated world with one parameter set. Conclusions about method accuracy might not carry to other settings.
- Training snapshots stack the same customers several times, so training rows are correlated. Splitting by time avoids leakage but does not remove that.
- Hazard-model standard errors are not cluster-robust; they are probably a little too small because customers contribute many rows.
- Hyperparameters were tuned over a small grid (6 settings) on a single validation snapshot.
- SQL was executed on SQLite only. The schema and queries use standard SQL, and `sql/postgres_load.sql` notes the known dialect differences, but I have not run them on PostgreSQL.
- No external benchmark: results were not checked against any real churn data.

## 10. Recommendations

The six recommendations, each with its evidence and caveat, are in the project README. In short: push monthly customers to annual contracts early; run a renewal programme for annual customers; favour Referral/Organic acquisition; be cautious with price rises; pilot risk-based outreach as a randomised test; do not treat usage as a lever. The pricing illustration (expected lifetime about 40 vs 26 months, 1/monthly churn, assuming the +1.39 pp effect persists) is back-of-envelope and ignores discounting and any fading of the effect.

## 11. Reproduce

```bash
pip install -r requirements.txt
python -m churn_platform.pipeline      # about 25 seconds
pytest                                  # 51 tests
python powerbi/build_powerbi_data.py    # Power BI tables
streamlit run dashboard/app.py
```
