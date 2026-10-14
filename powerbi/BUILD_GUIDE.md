# Building the Power BI report (about 45 minutes)

The repository ships everything the report is made of except the `.pbix` binary itself: a clean data
model (`dataset/`), Power Query loaders (`power_query.m`), every DAX measure (`measures.dax`) and a
theme (`theme.json`). Power BI Desktop is Windows-only and a `.pbix` cannot be generated outside it, so
follow these steps once, then save the file as `powerbi/Churn_Dashboard.pbix`.

`docs/screenshots/preview_*.png` show the target layout. They are rendered from the same tables with the
same measure logic, **not** captured from Power BI. Replace them with real screenshots in step 9.

## 1. Load the data
1. Open Power BI Desktop. **Home > Transform data > Manage parameters > New**: `DatasetFolder`, type Text,
   value = full path to `powerbi\dataset\` **with a trailing backslash**.
2. For each of the 8 blocks in `power_query.m`: **New Source > Blank Query > Advanced Editor**, paste the block,
   rename the query to the heading name. **Close & Apply**.

## 2. Model (Model view)
Create these relationships (all one-to-many, single direction, from the dimension):

| From (one) | To (many) |
|---|---|
| `dim_date[month]` | `fact_customer_month[month]` |
| `dim_customer[customer_id]` | `fact_customer_month[customer_id]` |
| `dim_customer[customer_id]` | `at_risk_customers[customer_id]` (one-to-one is fine) |

Leave `hazard_by_tenure`, `cohort_retention`, `survival_curves`, `price_event_study` unrelated.
Select `dim_date` > **Table tools > Mark as date table** > `month`.
Hide `customer_id` and `month` in the fact table; set **Sort by column**: `dim_date[month_name]` by `month_idx`.

## 3. Measures
**Home > Enter data**, create an empty table `_Measures`. Paste each measure from `measures.dax` into
**New measure**. Format: churn rates `0.00%`, MRR `#,0`, counts `#,0`, pp measures `0.00`.

## 4. Theme
**View > Themes > Browse for themes > `theme.json`**.

## 5. Pages and visuals
Put the same slicers on every page: `dim_date[year_month]` (between), `dim_customer[plan]`,
`[contract]`, `[channel]`, `[location]`, `[age_band]`. **View > Sync slicers** so they apply everywhere.
Use the title measures from `measures.dax` as dynamic titles (fx button on the title).

**Page 1: Executive Overview.** Cards: `Customers Served`, `Currently Active Customers`,
`Customers Churned (All Time)`, `Monthly Churn Rate`, `MRR (Period End)`, `Revenue Churn Rate`.
Line chart: `dim_date[year_month]` vs `Monthly Churn Rate` + `Churn Rate 3M Avg`. Area chart: MRR over time.
Text box under the charts: *"Churn is churners ÷ active customers per month. Data are simulated."*

**Page 2: Segment comparison.** Five clustered bar charts (axis: `contract`, `channel`, `age_band`, `plan`,
`location`; value: `Monthly Churn Rate`). Conditional-format bar colour with *Field value* = `Churn Status Colour`.
Add a text box: *"Standard/Premium got a 10% price rise in Jul 2025, so plan differences are not a pure plan effect."*

**Page 3: Retention and lifecycle.** Line chart `hazard_by_tenure` (x `tenure_month`, y `hazard`, legend `contract`);
line chart `survival_curves` (x `time`, y `survival`, legend `level`, slicer on `variable`);
matrix `cohort_retention` (rows `cohort`, columns `months_since_signup`, values Average of `retention_pct`,
Background colour gradient). The matrix is blank where a cohort was not yet old enough; that is intended.

**Page 4: Price impact and at-risk customers.** Card `Price Increase Effect (pp)` (expect **1.39**);
line chart `price_event_study` (x `year_month`, y `basic_churn_pct` and `standard_premium_churn_pct`);
cards `High-Risk Customers`, `MRR at Risk (High Risk)`, `Expected Churners Next 3M`;
column chart count of `customer_id` by `risk_band`; table of `customer_id`, `risk_pct`, `mrr`, `tenure_months`,
`tickets_3m`, sorted by `mrr_at_risk` (top N 25).

## 6. Sanity checks (the numbers you must see)
With no slicers applied: Customers Served **10,000**; Currently Active **5,307**; Customers Churned **4,693**;
Monthly Churn Rate **3.01%**; Contract: Monthly **3.82%**, Annual **1.84%**; Price Increase Effect **+1.39**.
These are asserted in `tests/test_powerbi_data.py` against the SQL results, so a mismatch means a model or
relationship error in the report, not in the data.

## 7. Usability for non-technical readers
Rename axes in plain language, show data labels on bars, keep the "how to read this" text boxes, add a
tooltip page or ⓘ text for "churn rate", and set **Edit interactions** so the cards ignore the date slicer
where noted (`Currently Active Customers`).

## 8. Optional: Row-level refresh
Re-run `python -m churn_platform.pipeline && python powerbi/build_powerbi_data.py`, then **Refresh** in Power BI.

## 9. Screenshots for the README
Use **File > Export > Export to PDF**, or Windows + Shift + S on each page. Save as
`docs/screenshots/powerbi_1_overview.png` ... `powerbi_4_price_and_risk.png`, then in `README.md` change the
four image links from `preview_` to `powerbi_` and delete the "Preview" notice.
