// =====================================================================================
// Power Query (M) loaders. In Power BI Desktop:  Home > Transform data > New Source > Blank Query
// > Advanced Editor, paste ONE block per query, and name each query exactly as in the heading.
//
// First create a text parameter:  Home > Transform data > Manage Parameters > New
//   Name: DatasetFolder   Type: Text   Current value: C:\path\to\churn_platform\powerbi\dataset\
// (keep the trailing backslash). Every query below reads from that folder, so moving the repo
// only means changing one value.
// "en-US" is passed so decimals and dates parse identically on any regional setting.
// =====================================================================================


// ---------- Query: dim_customer ----------
let
    Source  = Csv.Document(File.Contents(DatasetFolder & "dim_customer.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalarValues=true]),
    Typed   = Table.TransformColumnTypes(Headers, {
        {"customer_id", Int64.Type}, {"signup_month", type date}, {"age", Int64.Type},
        {"location", type text}, {"plan", type text}, {"contract", type text}, {"channel", type text},
        {"base_price", Int64.Type}, {"is_churned", Int64.Type}, {"churn_month", type date},
        {"observed_months", Int64.Type}, {"age_band", type text}, {"status", type text},
        {"price_group", type text}, {"signup_year", Int64.Type}}, "en-US")
in Typed


// ---------- Query: dim_date ----------
let
    Source  = Csv.Document(File.Contents(DatasetFolder & "dim_date.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalarValues=true]),
    Typed   = Table.TransformColumnTypes(Headers, {
        {"month", type date}, {"year", Int64.Type}, {"quarter", type text}, {"month_name", type text},
        {"year_month", type text}, {"month_idx", Int64.Type}, {"price_period", type text}}, "en-US")
in Typed


// ---------- Query: fact_customer_month ----------
let
    Source  = Csv.Document(File.Contents(DatasetFolder & "fact_customer_month.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalarValues=true]),
    Typed   = Table.TransformColumnTypes(Headers, {
        {"customer_id", Int64.Type}, {"month", type date}, {"tenure_month", Int64.Type},
        {"usage_hours", type number}, {"sessions", Int64.Type}, {"tickets", Int64.Type},
        {"failed_payment", Int64.Type}, {"mrr", type number}, {"churned_this_month", Int64.Type},
        {"tenure_band", type text}, {"is_new_customer", Int64.Type}}, "en-US")
in Typed


// ---------- Query: at_risk_customers ----------
let
    Source  = Csv.Document(File.Contents(DatasetFolder & "at_risk_customers.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalarValues=true]),
    Typed   = Table.TransformColumnTypes(Headers, {
        {"customer_id", Int64.Type}, {"tenure_months", Int64.Type}, {"mrr", type number},
        {"usage_3m_avg", type number}, {"tickets_3m", Int64.Type}, {"failed_3m", Int64.Type},
        {"risk_pct", type number}, {"risk_decile", Int64.Type}, {"risk_band", type text},
        {"mrr_at_risk", type number}, {"segment", Int64.Type}}, "en-US")
in Typed


// ---------- Query: hazard_by_tenure ----------
let
    Source  = Csv.Document(File.Contents(DatasetFolder & "hazard_by_tenure.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalarValues=true]),
    Typed   = Table.TransformColumnTypes(Headers, {
        {"contract", type text}, {"tenure_month", Int64.Type}, {"at_risk", Int64.Type},
        {"churned", Int64.Type}, {"hazard", type number}}, "en-US")
in Typed


// ---------- Query: cohort_retention ----------
let
    Source  = Csv.Document(File.Contents(DatasetFolder & "cohort_retention.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalarValues=true]),
    Typed   = Table.TransformColumnTypes(Headers, {
        {"cohort_q", Int64.Type}, {"cohort_size", Int64.Type}, {"months_since_signup", Int64.Type},
        {"active", Int64.Type}, {"retention_pct", type number}, {"cohort", type text}}, "en-US")
in Typed


// ---------- Query: survival_curves ----------
let
    Source  = Csv.Document(File.Contents(DatasetFolder & "survival_curves.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalarValues=true]),
    Typed   = Table.TransformColumnTypes(Headers, {
        {"variable", type text}, {"level", type text}, {"time", Int64.Type}, {"at_risk", Int64.Type},
        {"events", Int64.Type}, {"survival", type number}, {"ci_low", type number}, {"ci_high", type number}}, "en-US")
in Typed


// ---------- Query: price_event_study ----------
let
    Source  = Csv.Document(File.Contents(DatasetFolder & "price_event_study.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalarValues=true]),
    Typed   = Table.TransformColumnTypes(Headers, {
        {"month_idx", Int64.Type}, {"year_month", type text}, {"basic_churn_pct", type number},
        {"standard_premium_churn_pct", type number}, {"gap_pp", type number}}, "en-US")
in Typed
