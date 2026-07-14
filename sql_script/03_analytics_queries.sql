
SET search_path TO churn, public;
-- -----------------------------------------------------------------------------
-- QUERY 01: Total Subscribers and Churn Count
SELECT
    COUNT(DISTINCT customer_id)                                         AS total_subscribers,
    SUM(churn)                                                          AS total_churned,
    COUNT(DISTINCT customer_id) - SUM(churn)                           AS total_retained,
    ROUND(SUM(churn)::NUMERIC * 100.0 / NULLIF(COUNT(*), 0), 2)       AS overall_churn_rate_pct
FROM churn.fact_usage;
-- -----------------------------------------------------------------------------
-- QUERY 02: Churn Rate by Telecom Partner
SELECT
    tp.partner_name                                                     AS telecom_partner,
    COUNT(*)                                                            AS total_customers,
    SUM(fu.churn)                                                       AS churned_customers,
    COUNT(*) - SUM(fu.churn)                                           AS retained_customers,
    ROUND(SUM(fu.churn)::NUMERIC * 100.0 / NULLIF(COUNT(*), 0), 2)   AS churn_rate_pct
FROM churn.fact_usage          fu
JOIN churn.dim_telecom_partner tp ON tp.partner_id = fu.partner_id
GROUP BY tp.partner_name
ORDER BY churn_rate_pct DESC;
-- -----------------------------------------------------------------------------
-- QUERY 03: Gender Distribution and Churn Rate
SELECT
    dc.gender,
    COUNT(*)                                                            AS total_customers,
    SUM(fu.churn)                                                       AS churned,
    ROUND(SUM(fu.churn)::NUMERIC * 100.0 / NULLIF(COUNT(*), 0), 2)   AS churn_rate_pct,
    ROUND(COUNT(*)::NUMERIC * 100.0 / SUM(COUNT(*)) OVER (), 2)      AS gender_share_pct
FROM churn.fact_usage    fu
JOIN churn.dim_customers dc ON dc.customer_sk = fu.customer_sk AND dc.is_current
GROUP BY dc.gender
ORDER BY churn_rate_pct DESC;
-- -----------------------------------------------------------------------------
-- QUERY 04: Top 10 States by Subscriber Count
SELECT
    dg.state,
    COUNT(DISTINCT fu.customer_id)                                      AS total_subscribers,
    SUM(fu.churn)                                                       AS churned,
    ROUND(SUM(fu.churn)::NUMERIC * 100.0 / NULLIF(COUNT(*), 0), 2)   AS churn_rate_pct
FROM churn.fact_usage    fu
JOIN churn.dim_geography dg ON dg.geography_id = fu.geography_id
GROUP BY dg.state
ORDER BY total_subscribers DESC
LIMIT 10;

-- -----------------------------------------------------------------------------
-- QUERY 05: Average Calls/SMS/Data by Churn Status
SELECT
    CASE WHEN fu.churn = 1 THEN 'Churned' ELSE 'Retained' END         AS churn_status,
    COUNT(*)                                                            AS customer_count,
    ROUND(AVG(fu.calls_made), 1)                                       AS avg_calls_made,
    ROUND(AVG(fu.sms_sent), 1)                                         AS avg_sms_sent,
    ROUND(AVG(fu.data_used), 3)                                        AS avg_data_used_gb,
    ROUND(AVG(fu.calls_per_month), 2)                                  AS avg_calls_per_month,
    ROUND(AVG(fu.data_per_month), 4)                                   AS avg_data_per_month_gb,
    ROUND(AVG(fu.usage_score), 4)                                      AS avg_usage_score
FROM churn.fact_usage fu
GROUP BY fu.churn
ORDER BY fu.churn DESC;

-- -----------------------------------------------------------------------------
-- QUERY 06: Age Group Distribution and Churn Rate
SELECT
    dc.age_group,
    COUNT(*)                                                            AS total_customers,
    SUM(fu.churn)                                                       AS churned,
    ROUND(SUM(fu.churn)::NUMERIC * 100.0 / NULLIF(COUNT(*), 0), 2)   AS churn_rate_pct,
    ROUND(AVG(dc.age), 1)                                              AS avg_age,
    ROUND(AVG(dc.estimated_salary), 2)                                 AS avg_salary
FROM churn.fact_usage    fu
JOIN churn.dim_customers dc ON dc.customer_sk = fu.customer_sk AND dc.is_current
WHERE dc.age_group IN ('18-30', '31-45', '46-60', '61-75')
GROUP BY dc.age_group
ORDER BY dc.age_group;
-- -----------------------------------------------------------------------------
-- QUERY 07: Monthly New Registrations Trend
SELECT
    dd.calendar_year,
    dd.month_number,
    dd.month_name_short                                                 AS month,
    COUNT(DISTINCT fu.customer_id)                                      AS new_registrations
FROM churn.fact_usage fu
JOIN churn.dim_date   dd ON dd.date_id = fu.registration_date_id
GROUP BY dd.calendar_year, dd.month_number, dd.month_name_short
ORDER BY dd.calendar_year, dd.month_number;

-- -----------------------------------------------------------------------------
-- QUERY 08: Salary Percentile Distribution
SELECT
    dc.salary_tier,
    COUNT(*)                                                            AS customer_count,
    ROUND(MIN(dc.estimated_salary), 2)                                 AS min_salary,
    ROUND(AVG(dc.estimated_salary), 2)                                 AS avg_salary,
    ROUND(MAX(dc.estimated_salary), 2)                                 AS max_salary,
    ROUND(
        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY dc.estimated_salary)::NUMERIC, 2
    )                                                                   AS p25_salary,
    ROUND(
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY dc.estimated_salary)::NUMERIC, 2
    )                                                                   AS p50_salary,
    ROUND(
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY dc.estimated_salary)::NUMERIC, 2
    )                                                                   AS p75_salary,
    ROUND(SUM(fu.churn)::NUMERIC * 100.0 / NULLIF(COUNT(*), 0), 2)   AS churn_rate_pct
FROM churn.fact_usage    fu
JOIN churn.dim_customers dc ON dc.customer_sk = fu.customer_sk AND dc.is_current
GROUP BY dc.salary_tier
ORDER BY MIN(dc.estimated_salary);

-- -----------------------------------------------------------------------------
-- QUERY 09: Inactive Customers (Zero Calls)
SELECT
    fu.customer_id,
    dc.gender,
    dc.age,
    dg.state,
    tp.partner_name                                                     AS telecom_partner,
    fu.calls_made,
    fu.sms_sent,
    fu.data_used,
    fu.tenure_months,
    CASE WHEN fu.churn = 1 THEN 'Churned' ELSE 'Retained' END         AS churn_status
FROM churn.fact_usage          fu
JOIN churn.dim_customers       dc ON dc.customer_sk = fu.customer_sk AND dc.is_current
JOIN churn.dim_geography       dg ON dg.geography_id = fu.geography_id
JOIN churn.dim_telecom_partner tp ON tp.partner_id   = fu.partner_id
WHERE fu.calls_made = 0
ORDER BY fu.tenure_months DESC;

-- -----------------------------------------------------------------------------
-- QUERY 10: Churn Rate by Num Dependents
SELECT
    dc.num_dependents,
    COUNT(*)                                                            AS total_customers,
    SUM(fu.churn)                                                       AS churned,
    ROUND(SUM(fu.churn)::NUMERIC * 100.0 / NULLIF(COUNT(*), 0), 2)   AS churn_rate_pct,
    ROUND(AVG(dc.estimated_salary), 2)                                 AS avg_salary
FROM churn.fact_usage    fu
JOIN churn.dim_customers dc ON dc.customer_sk = fu.customer_sk AND dc.is_current
GROUP BY dc.num_dependents
ORDER BY dc.num_dependents;
-- -----------------------------------------------------------------------------
-- QUERY 11: Rolling 3-Month Churn Rate
WITH monthly_churn AS (
    SELECT
        dd.calendar_year,
        dd.month_number,
        dd.month_start_date,
        COUNT(*)                                AS total_customers,
        SUM(fu.churn)                           AS churned_count
    FROM churn.fact_usage fu
    JOIN churn.dim_date   dd ON dd.date_id = fu.snapshot_date_id
    GROUP BY dd.calendar_year, dd.month_number, dd.month_start_date
)
SELECT
    calendar_year,
    month_number,
    month_start_date,
    total_customers,
    churned_count,
    ROUND(churned_count::NUMERIC * 100.0 / NULLIF(total_customers, 0), 2) AS monthly_churn_rate_pct,
    ROUND(
        SUM(churned_count)   OVER w3 ::NUMERIC * 100.0
        / NULLIF(SUM(total_customers) OVER w3, 0),
        2
    )                                                                     AS rolling_3m_churn_rate_pct
FROM monthly_churn
WINDOW w3 AS (ORDER BY calendar_year, month_number ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
ORDER BY calendar_year, month_number;

-- -----------------------------------------------------------------------------
-- QUERY 12: Partner Market Share with RANK
SELECT
    tp.partner_name,
    tp.market_share,
    COUNT(DISTINCT fu.customer_id)                                      AS subscribers_in_dataset,
    ROUND(COUNT(*)::NUMERIC * 100.0 / SUM(COUNT(*)) OVER (), 2)      AS dataset_share_pct,
    RANK()     OVER (ORDER BY COUNT(*) DESC)                           AS rank_by_subscribers,
    DENSE_RANK() OVER (ORDER BY tp.market_share DESC NULLS LAST)      AS rank_by_market_share
FROM churn.fact_usage          fu
JOIN churn.dim_telecom_partner tp ON tp.partner_id = fu.partner_id
GROUP BY tp.partner_name, tp.market_share
ORDER BY rank_by_subscribers;
-- -----------------------------------------------------------------------------
-- QUERY 13: Cohort Analysis by Registration Year
SELECT
    dd_reg.calendar_year                                                AS registration_cohort,
    COUNT(DISTINCT fu.customer_id)                                      AS cohort_size,
    SUM(fu.churn)                                                       AS churned_in_cohort,
    ROUND(SUM(fu.churn)::NUMERIC * 100.0 / NULLIF(COUNT(*), 0), 2)   AS cohort_churn_rate_pct,
    ROUND(AVG(fu.tenure_months), 1)                                    AS avg_tenure_months,
    ROUND(AVG(dc.estimated_salary), 2)                                 AS avg_salary
FROM churn.fact_usage    fu
JOIN churn.dim_date      dd_reg ON dd_reg.date_id = fu.registration_date_id
JOIN churn.dim_customers dc     ON dc.customer_sk = fu.customer_sk AND dc.is_current
GROUP BY dd_reg.calendar_year
ORDER BY registration_cohort;

-- -----------------------------------------------------------------------------
-- QUERY 14: High-Value Churned Customers
WITH salary_percentiles AS (
    SELECT PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY estimated_salary) AS p75_salary
    FROM   churn.dim_customers WHERE is_current
)
SELECT
    fu.customer_id,
    dc.gender,
    dc.age,
    dc.estimated_salary,
    dg.state,
    tp.partner_name                                                     AS telecom_partner,
    fu.tenure_months,
    fu.usage_score,
    fu.calls_made,
    fu.data_used
FROM churn.fact_usage          fu
JOIN churn.dim_customers       dc ON dc.customer_sk = fu.customer_sk AND dc.is_current
JOIN churn.dim_geography       dg ON dg.geography_id = fu.geography_id
JOIN churn.dim_telecom_partner tp ON tp.partner_id   = fu.partner_id
CROSS JOIN salary_percentiles   sp
WHERE fu.churn = 1
  AND dc.estimated_salary > sp.p75_salary
ORDER BY dc.estimated_salary DESC;

-- -----------------------------------------------------------------------------
-- QUERY 15: Usage Segmentation with NTILE(4)
WITH usage_quartiles AS (
    SELECT
        customer_id,
        usage_score,
        churn,
        NTILE(4) OVER (ORDER BY usage_score)   AS usage_quartile
    FROM churn.fact_usage
)
SELECT
    usage_quartile,
    CASE usage_quartile
        WHEN 1 THEN 'Q1 - Lowest Usage'
        WHEN 2 THEN 'Q2 - Low-Mid Usage'
        WHEN 3 THEN 'Q3 - Mid-High Usage'
        WHEN 4 THEN 'Q4 - Highest Usage'
    END                                                                 AS quartile_label,
    COUNT(*)                                                            AS customer_count,
    ROUND(MIN(usage_score)::NUMERIC, 4)                                AS min_score,
    ROUND(MAX(usage_score)::NUMERIC, 4)                                AS max_score,
    ROUND(AVG(usage_score)::NUMERIC, 4)                                AS avg_score,
    SUM(churn)                                                          AS churned,
    ROUND(SUM(churn)::NUMERIC * 100.0 / NULLIF(COUNT(*), 0), 2)      AS churn_rate_pct
FROM usage_quartiles
GROUP BY usage_quartile
ORDER BY usage_quartile;

-- -----------------------------------------------------------------------------
-- QUERY 16: Month-over-Month Churn Change with LAG
WITH monthly AS (
    SELECT
        dd.calendar_year,
        dd.month_number,
        dd.month_name_short                         AS month_abbr,
        SUM(fu.churn)                               AS churned_count,
        COUNT(*)                                    AS total_customers
    FROM churn.fact_usage fu
    JOIN churn.dim_date   dd ON dd.date_id = fu.snapshot_date_id
    GROUP BY dd.calendar_year, dd.month_number, dd.month_name_short
)
SELECT
    calendar_year,
    month_number,
    month_abbr,
    total_customers,
    churned_count,
    ROUND(churned_count::NUMERIC * 100.0 / NULLIF(total_customers, 0), 2)       AS churn_rate_pct,
    LAG(churned_count) OVER (ORDER BY calendar_year, month_number)               AS prev_month_churn,
    churned_count - LAG(churned_count) OVER (ORDER BY calendar_year, month_number) AS mom_churn_delta,
    ROUND(
        (churned_count - LAG(churned_count) OVER (ORDER BY calendar_year, month_number))::NUMERIC
        * 100.0 / NULLIF(LAG(churned_count) OVER (ORDER BY calendar_year, month_number), 0),
        2
    )                                                                            AS mom_churn_change_pct
FROM monthly
ORDER BY calendar_year, month_number;

-- -----------------------------------------------------------------------------
-- QUERY 17: Customer Lifetime Value Estimate by Segment
SELECT
    tp.partner_name                                                     AS telecom_partner,
    dc.age_group,
    dc.salary_tier,
    COUNT(*)                                                            AS customer_count,
    ROUND(AVG(fu.tenure_months), 1)                                    AS avg_tenure_months,
    ROUND(AVG(dc.estimated_salary), 2)                                 AS avg_annual_salary,
    ROUND(AVG(dc.estimated_salary) / 12.0, 2)                         AS avg_monthly_salary,
    -- Simple CLV: monthly salary × tenure
    ROUND(AVG(dc.estimated_salary / 12.0 * fu.tenure_months), 2)      AS estimated_clv,
    ROUND(SUM(fu.churn)::NUMERIC * 100.0 / NULLIF(COUNT(*), 0), 2)   AS churn_rate_pct
FROM churn.fact_usage          fu
JOIN churn.dim_customers       dc ON dc.customer_sk = fu.customer_sk AND dc.is_current
JOIN churn.dim_telecom_partner tp ON tp.partner_id   = fu.partner_id
GROUP BY tp.partner_name, dc.age_group, dc.salary_tier
ORDER BY estimated_clv DESC;

-- QUERY 18: Retention Rate by Tenure Cohort
SELECT
    CASE
        WHEN fu.tenure_months BETWEEN 0  AND 6  THEN '0-6 months'
        WHEN fu.tenure_months BETWEEN 7  AND 12 THEN '7-12 months'
        WHEN fu.tenure_months BETWEEN 13 AND 24 THEN '13-24 months'
        ELSE '25+ months'
    END                                                                 AS tenure_cohort,
    CASE
        WHEN fu.tenure_months BETWEEN 0  AND 6  THEN 1
        WHEN fu.tenure_months BETWEEN 7  AND 12 THEN 2
        WHEN fu.tenure_months BETWEEN 13 AND 24 THEN 3
        ELSE 4
    END                                                                 AS sort_order,
    COUNT(*)                                                            AS total_customers,
    SUM(fu.churn)                                                       AS churned,
    COUNT(*) - SUM(fu.churn)                                           AS retained,
    ROUND(SUM(fu.churn)::NUMERIC * 100.0 / NULLIF(COUNT(*), 0), 2)   AS churn_rate_pct,
    ROUND((COUNT(*) - SUM(fu.churn))::NUMERIC * 100.0 / NULLIF(COUNT(*), 0), 2) AS retention_rate_pct,
    ROUND(AVG(fu.usage_score), 4)                                      AS avg_usage_score
FROM churn.fact_usage fu
GROUP BY
    CASE WHEN fu.tenure_months BETWEEN 0  AND 6  THEN '0-6 months'
         WHEN fu.tenure_months BETWEEN 7  AND 12 THEN '7-12 months'
         WHEN fu.tenure_months BETWEEN 13 AND 24 THEN '13-24 months'
         ELSE '25+ months' END,
    CASE WHEN fu.tenure_months BETWEEN 0  AND 6  THEN 1
         WHEN fu.tenure_months BETWEEN 7  AND 12 THEN 2
         WHEN fu.tenure_months BETWEEN 13 AND 24 THEN 3
         ELSE 4 END
ORDER BY sort_order;

-- QUERY 19: At-Risk Customers — Low Usage, High Tenure
WITH at_risk AS (
    SELECT
        fu.customer_id,
        fu.tenure_months,
        fu.usage_score,
        fu.calls_made,
        fu.data_used,
        fu.sms_sent,
        fu.is_low_engagement,
        fu.low_usage_high_tenure,
        fu.churn
    FROM churn.fact_usage fu
    WHERE fu.low_usage_high_tenure = 1     -- is_low_engagement AND tenure > 12m
),
enriched AS (
    SELECT
        ar.*,
        dc.gender,
        dc.age,
        dc.age_group,
        dc.estimated_salary,
        dg.state,
        dg.city,
        tp.partner_name                     AS telecom_partner
    FROM at_risk            ar
    JOIN churn.dim_customers dc ON dc.customer_id = ar.customer_id AND dc.is_current
    JOIN churn.fact_usage    fu ON fu.customer_id = ar.customer_id
    JOIN churn.dim_geography dg ON dg.geography_id = fu.geography_id
    JOIN churn.dim_telecom_partner tp ON tp.partner_id = fu.partner_id
)
SELECT
    customer_id,
    gender,
    age,
    age_group,
    estimated_salary,
    state,
    city,
    telecom_partner,
    tenure_months,
    usage_score,
    calls_made,
    data_used,
    sms_sent,
    churn
FROM enriched
ORDER BY tenure_months DESC, usage_score ASC;

-- -----------------------------------------------------------------------------
-- QUERY 20: Running Total of Churned Revenue by Month
WITH monthly_churn_revenue AS (
    SELECT
        dd.calendar_year,
        dd.month_number,
        dd.month_name_short                                             AS month_abbr,
        dd.month_start_date,
        -- Revenue proxy: salary/12 for each churned customer
        SUM(CASE WHEN fu.churn = 1 THEN dc.estimated_salary / 12.0 ELSE 0 END) AS churned_mrr
    FROM churn.fact_usage    fu
    JOIN churn.dim_date      dd ON dd.date_id      = fu.snapshot_date_id
    JOIN churn.dim_customers dc ON dc.customer_sk  = fu.customer_sk AND dc.is_current
    GROUP BY dd.calendar_year, dd.month_number, dd.month_name_short, dd.month_start_date
)
SELECT
    calendar_year,
    month_number,
    month_abbr,
    month_start_date,
    ROUND(churned_mrr, 2)                                               AS monthly_churned_mrr,
    ROUND(
        SUM(churned_mrr) OVER (ORDER BY calendar_year, month_number
                               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),
        2
    )                                                                   AS cumulative_churned_mrr
FROM monthly_churn_revenue
ORDER BY calendar_year, month_number;
-- -----------------------------------------------------------------------------
-- QUERY 21: Recursive CTE — Customer Referral Chain (Simulated)
WITH RECURSIVE referral_chain AS (
    -- Anchor: seed churned customers with high predicted churn probability
    SELECT
        fu.customer_id              AS root_customer_id,
        fu.customer_id              AS current_customer_id,
        dc.date_of_registration,
        dg.state,
        0                           AS depth,
        ARRAY[fu.customer_id]       AS visited_chain
    FROM churn.fact_usage          fu
    JOIN churn.dim_customers       dc ON dc.customer_sk = fu.customer_sk AND dc.is_current
    JOIN churn.dim_geography       dg ON dg.geography_id = fu.geography_id
    WHERE fu.churn = 1
      AND fu.usage_score < 0.5          -- Low-usage churners as seed nodes

    UNION ALL

    -- Recursive: find "referred" customers (same state, registered within 30 days after)
    SELECT
        rc.root_customer_id,
        fu2.customer_id,
        dc2.date_of_registration,
        dg2.state,
        rc.depth + 1,
        rc.visited_chain || fu2.customer_id
    FROM referral_chain            rc
    JOIN churn.fact_usage          fu2 ON fu2.customer_id <> rc.current_customer_id
                                      AND fu2.customer_id <> ALL(rc.visited_chain)
    JOIN churn.dim_customers       dc2 ON dc2.customer_sk   = fu2.customer_sk AND dc2.is_current
    JOIN churn.dim_geography       dg2 ON dg2.geography_id  = fu2.geography_id
    WHERE dg2.state = rc.state
      AND dc2.date_of_registration BETWEEN rc.date_of_registration
                                       AND rc.date_of_registration + 30
      AND rc.depth < 3                  -- Limit recursion depth to 3 hops
)
SELECT
    root_customer_id,
    current_customer_id         AS referred_customer_id,
    depth                       AS referral_hops,
    state,
    date_of_registration
FROM referral_chain
WHERE depth > 0
ORDER BY root_customer_id, depth;

-- -----------------------------------------------------------------------------
-- QUERY 22: Pivot — Churn Rate by Partner × Gender
SELECT
    tp.partner_name                                                     AS telecom_partner,
    COUNT(*)                                                            AS total_customers,
    -- Male churn rate
    ROUND(
        SUM(CASE WHEN dc.gender = 'Male'   AND fu.churn = 1 THEN 1 ELSE 0 END)::NUMERIC
        * 100.0 / NULLIF(SUM(CASE WHEN dc.gender = 'Male'   THEN 1 ELSE 0 END), 0), 2
    )                                                                   AS male_churn_rate_pct,
    -- Female churn rate
    ROUND(
        SUM(CASE WHEN dc.gender = 'Female' AND fu.churn = 1 THEN 1 ELSE 0 END)::NUMERIC
        * 100.0 / NULLIF(SUM(CASE WHEN dc.gender = 'Female' THEN 1 ELSE 0 END), 0), 2
    )                                                                   AS female_churn_rate_pct,
    -- Other gender churn rate
    ROUND(
        SUM(CASE WHEN dc.gender = 'Other'  AND fu.churn = 1 THEN 1 ELSE 0 END)::NUMERIC
        * 100.0 / NULLIF(SUM(CASE WHEN dc.gender = 'Other'  THEN 1 ELSE 0 END), 0), 2
    )                                                                   AS other_churn_rate_pct,
    -- Overall partner churn
    ROUND(SUM(fu.churn)::NUMERIC * 100.0 / NULLIF(COUNT(*), 0), 2)   AS overall_churn_rate_pct
FROM churn.fact_usage          fu
JOIN churn.dim_customers       dc ON dc.customer_sk = fu.customer_sk AND dc.is_current
JOIN churn.dim_telecom_partner tp ON tp.partner_id   = fu.partner_id
GROUP BY tp.partner_name
ORDER BY overall_churn_rate_pct DESC;

-- -----------------------------------------------------------------------------
-- QUERY 23: Dense Rank by Usage Score Within State
SELECT
    fu.customer_id,
    dg.state,
    tp.partner_name                                                     AS telecom_partner,
    dc.age_group,
    fu.usage_score,
    fu.tenure_months,
    fu.churn,
    DENSE_RANK() OVER (
        PARTITION BY dg.state
        ORDER BY fu.usage_score DESC
    )                                                                   AS rank_in_state,
    PERCENT_RANK() OVER (
        PARTITION BY dg.state
        ORDER BY fu.usage_score DESC
    )                                                                   AS pct_rank_in_state
FROM churn.fact_usage          fu
JOIN churn.dim_customers       dc ON dc.customer_sk = fu.customer_sk AND dc.is_current
JOIN churn.dim_geography       dg ON dg.geography_id = fu.geography_id
JOIN churn.dim_telecom_partner tp ON tp.partner_id   = fu.partner_id
ORDER BY dg.state, rank_in_state;

-- -----------------------------------------------------------------------------
-- QUERY 24: Median Salary by State
SELECT
    dg.state,
    COUNT(DISTINCT fu.customer_id)                                      AS subscriber_count,
    ROUND(MIN(dc.estimated_salary), 2)                                 AS min_salary,
    ROUND(AVG(dc.estimated_salary), 2)                                 AS avg_salary,
    ROUND(
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY dc.estimated_salary)::NUMERIC, 2
    )                                                                   AS median_salary,
    ROUND(
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY dc.estimated_salary)::NUMERIC, 2
    )                                                                   AS p75_salary,
    ROUND(MAX(dc.estimated_salary), 2)                                 AS max_salary,
    ROUND(SUM(fu.churn)::NUMERIC * 100.0 / NULLIF(COUNT(*), 0), 2)   AS churn_rate_pct
FROM churn.fact_usage    fu
JOIN churn.dim_customers dc ON dc.customer_sk = fu.customer_sk AND dc.is_current
JOIN churn.dim_geography dg ON dg.geography_id = fu.geography_id
GROUP BY dg.state
ORDER BY median_salary DESC;

-- -----------------------------------------------------------------------------
-- QUERY 25: Segment Overlap — Low-Engagement AND High-Tenure
SELECT
    tp.partner_name                                                     AS telecom_partner,
    dg.state,
    dc.age_group,
    COUNT(*)                                                            AS overlap_count,
    SUM(fu.churn)                                                       AS overlap_churned,
    ROUND(SUM(fu.churn)::NUMERIC * 100.0 / NULLIF(COUNT(*), 0), 2)   AS overlap_churn_rate_pct,
    ROUND(AVG(fu.tenure_months), 1)                                    AS avg_tenure_months,
    ROUND(AVG(fu.usage_score), 4)                                      AS avg_usage_score,
    ROUND(AVG(dc.estimated_salary), 2)                                 AS avg_salary,
    -- What % of total partner subscribers does this overlap represent?
    ROUND(
        COUNT(*)::NUMERIC * 100.0
        / NULLIF(
            (SELECT COUNT(*) FROM churn.fact_usage f2
             JOIN churn.dim_telecom_partner tp2 ON tp2.partner_id = f2.partner_id
             WHERE tp2.partner_name = tp.partner_name), 0
        ), 2
    )                                                                   AS pct_of_partner_base
FROM churn.fact_usage          fu
JOIN churn.dim_customers       dc ON dc.customer_sk = fu.customer_sk AND dc.is_current
JOIN churn.dim_geography       dg ON dg.geography_id = fu.geography_id
JOIN churn.dim_telecom_partner tp ON tp.partner_id   = fu.partner_id
WHERE fu.is_low_engagement    = 1      -- Low usage flag
  AND fu.tenure_months        > 12     -- Long-tenure customers
GROUP BY tp.partner_name, dg.state, dc.age_group
HAVING COUNT(*) >= 5                   -- Minimum segment size for statistical validity
ORDER BY overlap_churn_rate_pct DESC;

-- -----------------------------------------------------------------------------
-- QUERY 26: Anomaly Detection — Usage Outliers (>3σ)
WITH usage_stats AS (
    SELECT
        AVG(calls_made)         AS mean_calls,
        STDDEV(calls_made)      AS std_calls,
        AVG(data_used)          AS mean_data,
        STDDEV(data_used)       AS std_data,
        AVG(sms_sent)           AS mean_sms,
        STDDEV(sms_sent)        AS std_sms
    FROM churn.fact_usage
)
SELECT
    fu.customer_id,
    fu.calls_made,
    fu.data_used,
    fu.sms_sent,
    fu.usage_score,
    fu.churn,
    ROUND((fu.calls_made - us.mean_calls) / NULLIF(us.std_calls, 0), 2) AS calls_z_score,
    ROUND((fu.data_used  - us.mean_data)  / NULLIF(us.std_data,  0), 2) AS data_z_score,
    ROUND((fu.sms_sent   - us.mean_sms)   / NULLIF(us.std_sms,   0), 2) AS sms_z_score,
    CASE
        WHEN ABS((fu.calls_made - us.mean_calls) / NULLIF(us.std_calls, 0)) > 3
          OR ABS((fu.data_used  - us.mean_data)  / NULLIF(us.std_data,  0)) > 3
          OR ABS((fu.sms_sent   - us.mean_sms)   / NULLIF(us.std_sms,   0)) > 3
        THEN 'OUTLIER'
        ELSE 'NORMAL'
    END                                                                 AS anomaly_flag
FROM churn.fact_usage fu
CROSS JOIN usage_stats us
WHERE
    ABS((fu.calls_made - us.mean_calls) / NULLIF(us.std_calls, 0)) > 3
 OR ABS((fu.data_used  - us.mean_data)  / NULLIF(us.std_data,  0)) > 3
 OR ABS((fu.sms_sent   - us.mean_sms)   / NULLIF(us.std_sms,   0)) > 3
ORDER BY ABS((fu.usage_score - (SELECT AVG(usage_score) FROM churn.fact_usage))) DESC;

-- -----------------------------------------------------------------------------
-- QUERY 27: Executive KPI Dashboard
WITH kpi_base AS (
    SELECT
        COUNT(DISTINCT fu.customer_id)                                  AS total_subscribers,
        SUM(fu.churn)                                                   AS total_churned,
        COUNT(DISTINCT fu.customer_id) - SUM(fu.churn)                 AS total_retained,
        ROUND(SUM(fu.churn)::NUMERIC * 100.0 / NULLIF(COUNT(*), 0), 2) AS overall_churn_rate,
        ROUND(AVG(fu.tenure_months), 1)                                 AS avg_tenure_months,
        ROUND(AVG(dc.estimated_salary), 2)                              AS avg_annual_salary,
        ROUND(AVG(dc.estimated_salary) / 12.0, 2)                      AS avg_mrr_proxy,
        ROUND(AVG(fu.usage_score), 4)                                   AS avg_usage_score,
        SUM(CASE WHEN fu.is_low_engagement = 1 THEN 1 ELSE 0 END)      AS low_engagement_count,
        SUM(CASE WHEN fu.low_usage_high_tenure = 1 THEN 1 ELSE 0 END)  AS at_risk_segment_count,
        ROUND(SUM(dc.estimated_salary / 12.0 * CASE WHEN fu.churn=1 THEN 1 ELSE 0 END), 2) AS total_mrr_lost
    FROM churn.fact_usage    fu
    JOIN churn.dim_customers dc ON dc.customer_sk = fu.customer_sk AND dc.is_current
),
pred_base AS (
    SELECT
        COUNT(*)                                                        AS total_predictions,
        SUM(predicted_churn)                                            AS predicted_churners,
        ROUND(AVG(predicted_prob) * 100, 2)                            AS avg_predicted_prob_pct,
        SUM(CASE WHEN predicted_prob > 0.70 THEN 1 ELSE 0 END)        AS high_risk_count
    FROM churn.fact_churn_predictions
)
SELECT 'Total Subscribers'          AS kpi_name,  total_subscribers::TEXT        AS kpi_value, 'count'   AS unit FROM kpi_base
UNION ALL
SELECT 'Total Churned',                            total_churned::TEXT,            'count'   FROM kpi_base
UNION ALL
SELECT 'Total Retained',                           total_retained::TEXT,           'count'   FROM kpi_base
UNION ALL
SELECT 'Overall Churn Rate (%)',                   overall_churn_rate::TEXT,       '%'       FROM kpi_base
UNION ALL
SELECT 'Avg Tenure (Months)',                      avg_tenure_months::TEXT,        'months'  FROM kpi_base
UNION ALL
SELECT 'Avg Annual Salary (INR)',                  avg_annual_salary::TEXT,        'INR'     FROM kpi_base
UNION ALL
SELECT 'Avg MRR Proxy (INR/mo)',                   avg_mrr_proxy::TEXT,            'INR'     FROM kpi_base
UNION ALL
SELECT 'Avg Usage Score',                          avg_usage_score::TEXT,          'score'   FROM kpi_base
UNION ALL
SELECT 'Low Engagement Customers',                 low_engagement_count::TEXT,     'count'   FROM kpi_base
UNION ALL
SELECT 'At-Risk Segment (Low Use + High Tenure)',  at_risk_segment_count::TEXT,    'count'   FROM kpi_base
UNION ALL
SELECT 'Total MRR Lost to Churn (INR)',            total_mrr_lost::TEXT,           'INR'     FROM kpi_base
UNION ALL
SELECT 'High Risk Customers (Prob > 70%)',         high_risk_count::TEXT,          'count'   FROM pred_base
UNION ALL
SELECT 'Avg Predicted Churn Prob (%)',             avg_predicted_prob_pct::TEXT,   '%'       FROM pred_base;
