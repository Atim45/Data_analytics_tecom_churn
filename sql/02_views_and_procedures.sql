SET search_path TO churn, public;

-- ===========================================================================
-- SECTION 1: VIEWS
-- ===========================================================================

DROP VIEW IF EXISTS churn.vw_customer_360 CASCADE;

CREATE OR REPLACE VIEW churn.vw_customer_360 AS
SELECT
    -- ---- Identity ----
    dc.customer_id,
    dc.customer_sk,

    -- ---- Demographics ----
    dc.gender,
    dc.age,
    dc.age_group,
    dc.num_dependents,
    dc.estimated_salary,
    dc.salary_tier,
    dc.date_of_registration,

    -- ---- Geography ----
    dg.pincode,
    dg.city,
    dg.state,
    dg.region,

    -- ---- Partner ----
    tp.partner_name                             AS telecom_partner,
    tp.partner_code,
    tp.market_share                             AS partner_market_share_pct,
    tp.technology                               AS network_technology,

    -- ---- Snapshot Date ----
    dd_snap.full_date                           AS snapshot_date,
    dd_snap.calendar_year                       AS snapshot_year,
    dd_snap.month_name                          AS snapshot_month,
    dd_snap.quarter_name                        AS snapshot_quarter,

    -- ---- Raw Usage ----
    fu.calls_made,
    fu.sms_sent,
    fu.data_used,
    fu.churn,

    -- ---- Engineered Features ----
    fu.tenure_months,
    fu.calls_per_month,
    fu.data_per_month,
    fu.sms_per_month,
    fu.data_per_call,
    fu.sms_to_call_ratio,
    fu.age_x_dependents,
    fu.estimated_salary_log,
    fu.usage_score,
    fu.is_low_engagement,
    fu.low_usage_high_tenure,

    -- ---- Derived Flags ----
    CASE WHEN fu.churn = 1 THEN 'Churned' ELSE 'Retained' END  AS churn_status,
    CASE WHEN fu.tenure_months >= 24 THEN 'Loyal'
         WHEN fu.tenure_months >= 12 THEN 'Established'
         WHEN fu.tenure_months >=  6 THEN 'Growing'
         ELSE 'New' END                                        AS tenure_segment,

    -- ---- Metadata ----
    fu.usage_id,
    fu.created_at                               AS record_created_at

FROM churn.fact_usage          fu
JOIN churn.dim_customers       dc ON dc.customer_sk = fu.customer_sk AND dc.is_current = TRUE
JOIN churn.dim_geography       dg ON dg.geography_id = fu.geography_id
JOIN churn.dim_telecom_partner tp ON tp.partner_id   = fu.partner_id
JOIN churn.dim_date        dd_snap ON dd_snap.date_id = fu.snapshot_date_id;

COMMENT ON VIEW churn.vw_customer_360 IS
    'Full customer 360 view. Joins all dimension and fact tables into a single '
    'denormalised, analytics-ready record per customer per snapshot date.';

-- ---------------------------------------------------------------------------
-- VIEW 2: vw_churn_summary
-- Churn rates sliced by partner, state, and age group
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS churn.vw_churn_summary CASCADE;

CREATE OR REPLACE VIEW churn.vw_churn_summary AS

SELECT
    tp.partner_name                                             AS telecom_partner,
    dg.state,
    dc.age_group,
    COUNT(*)                                                    AS total_customers,
    SUM(fu.churn)                                               AS churned_customers,
    SUM(fu.churn)::NUMERIC * 100.0 / NULLIF(COUNT(*), 0)       AS churn_rate_pct,
    AVG(fu.usage_score)                                         AS avg_usage_score,
    AVG(dc.estimated_salary)                                    AS avg_salary,
    AVG(fu.tenure_months)                                       AS avg_tenure_months,
    SUM(CASE WHEN fu.is_low_engagement = 1 THEN 1 ELSE 0 END)  AS low_engagement_count

FROM churn.fact_usage          fu
JOIN churn.dim_customers       dc ON dc.customer_sk = fu.customer_sk AND dc.is_current
JOIN churn.dim_geography       dg ON dg.geography_id = fu.geography_id
JOIN churn.dim_telecom_partner tp ON tp.partner_id   = fu.partner_id

GROUP BY
    tp.partner_name,
    dg.state,
    dc.age_group;

COMMENT ON VIEW churn.vw_churn_summary IS
    'Aggregated churn rate by telecom partner, state, and age group. '
    'Refresh-friendly; no materialisation needed for datasets < 50M rows.';

-- ---------------------------------------------------------------------------
-- VIEW 3: vw_monthly_trends
-- Month-over-month registrations, churn volume, and churn rate trend
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS churn.vw_monthly_trends CASCADE;

CREATE OR REPLACE VIEW churn.vw_monthly_trends AS

WITH monthly_base AS (
    SELECT
        dd.calendar_year,
        dd.month_number,
        dd.month_name_short                                         AS month_abbr,
        dd.month_start_date,
        COUNT(DISTINCT fu.customer_id)                              AS total_active_customers,
        SUM(fu.churn)                                               AS churned_count,
        COUNT(DISTINCT CASE WHEN dd_reg.full_date >= dd.month_start_date
                             AND dd_reg.full_date <= dd.month_end_date
                            THEN fu.customer_id END)                AS new_registrations
    FROM churn.fact_usage          fu
    JOIN churn.dim_date        dd      ON dd.date_id      = fu.snapshot_date_id
    JOIN churn.dim_date        dd_reg  ON dd_reg.date_id  = fu.registration_date_id
    GROUP BY
        dd.calendar_year, dd.month_number, dd.month_name_short, dd.month_start_date, dd.month_end_date
)
SELECT
    calendar_year,
    month_number,
    month_abbr,
    month_start_date,
    total_active_customers,
    new_registrations,
    churned_count,
    ROUND(churned_count::NUMERIC * 100.0 / NULLIF(total_active_customers, 0), 2) AS churn_rate_pct,
    LAG(churned_count) OVER (ORDER BY calendar_year, month_number)               AS prev_month_churned,
    churned_count - LAG(churned_count) OVER (ORDER BY calendar_year, month_number) AS churn_mom_delta,
    SUM(churned_count) OVER (ORDER BY calendar_year, month_number
                             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)   AS cumulative_churned
FROM monthly_base
ORDER BY calendar_year, month_number;

COMMENT ON VIEW churn.vw_monthly_trends IS
    'Monthly time-series of registrations, churn volume, churn rate, '
    'MoM delta, and running cumulative churn. Includes LAG and SUM window functions.';

-- ---------------------------------------------------------------------------
-- VIEW 4: vw_high_risk_customers
-- Customers whose predicted churn probability exceeds 0.70
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS churn.vw_high_risk_customers CASCADE;

CREATE OR REPLACE VIEW churn.vw_high_risk_customers AS

WITH latest_predictions AS (
    SELECT DISTINCT ON (customer_id)
        customer_id,
        customer_sk,
        predicted_prob,
        predicted_churn,
        threshold,
        model_version,
        confidence_band,
        snapshot_date_id,
        created_at
    FROM churn.fact_churn_predictions
    ORDER BY customer_id, created_at DESC  -- latest batch first
)
SELECT
    lp.customer_id,
    dc.gender,
    dc.age,
    dc.age_group,
    dc.estimated_salary,
    dc.salary_tier,
    dg.city,
    dg.state,
    tp.partner_name                         AS telecom_partner,
    fu.tenure_months,
    fu.usage_score,
    fu.calls_made,
    fu.data_used,
    fu.sms_sent,
    fu.is_low_engagement,
    lp.predicted_prob,
    lp.predicted_churn,
    lp.confidence_band,
    lp.model_version,
    dd.full_date                            AS prediction_date,

    -- Priority score: higher prob + lower salary = handle sooner
    ROUND(lp.predicted_prob * 100, 1)                                   AS risk_score,
    NTILE(3) OVER (ORDER BY lp.predicted_prob DESC)                     AS risk_tier  -- 1=top risk, 3=lower risk

FROM latest_predictions                lp
JOIN churn.dim_customers               dc ON dc.customer_sk = lp.customer_sk AND dc.is_current
JOIN churn.dim_geography               dg ON dg.geography_id = (
        SELECT geography_id FROM churn.fact_usage
        WHERE  customer_sk = lp.customer_sk ORDER BY snapshot_date_id DESC LIMIT 1
)
JOIN churn.dim_telecom_partner         tp ON tp.partner_id = (
        SELECT partner_id FROM churn.fact_usage
        WHERE  customer_sk = lp.customer_sk ORDER BY snapshot_date_id DESC LIMIT 1
)
JOIN churn.fact_usage                  fu ON fu.customer_sk = lp.customer_sk
                                         AND fu.snapshot_date_id = lp.snapshot_date_id
JOIN churn.dim_date                    dd ON dd.date_id = lp.snapshot_date_id
WHERE lp.predicted_prob > 0.70;

COMMENT ON VIEW churn.vw_high_risk_customers IS
    'Customers with predicted churn probability > 70% from the latest model batch. '
    'Ranked by risk_score descending. Primary input for retention campaign CRM export.';

-- ---------------------------------------------------------------------------
-- VIEW 5: vw_revenue_at_risk
-- Estimated revenue at risk from high-churn-probability customers
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS churn.vw_revenue_at_risk CASCADE;

CREATE OR REPLACE VIEW churn.vw_revenue_at_risk AS

SELECT
    tp.partner_name                                         AS telecom_partner,
    dg.state,
    hr.confidence_band                                      AS risk_band,
    COUNT(DISTINCT hr.customer_id)                          AS high_risk_customers,
    SUM(dc.estimated_salary)                                AS total_salary_at_risk,
    AVG(dc.estimated_salary)                                AS avg_salary_at_risk,
    AVG(hr.predicted_prob)                                  AS avg_predicted_prob,

    -- Expected revenue loss = sum(prob × salary)
    SUM(hr.predicted_prob * dc.estimated_salary)            AS expected_revenue_loss,

    -- Simple MRR proxy: annual salary / 12 * prob
    SUM(hr.predicted_prob * dc.estimated_salary / 12.0)     AS expected_mrr_loss

FROM churn.vw_high_risk_customers    hr
JOIN churn.dim_customers             dc ON dc.customer_id = hr.customer_id AND dc.is_current
JOIN churn.dim_geography             dg ON dg.city  = hr.city AND dg.state = hr.state
JOIN churn.dim_telecom_partner       tp ON tp.partner_name = hr.telecom_partner

GROUP BY
    tp.partner_name,
    dg.state,
    hr.confidence_band

ORDER BY expected_revenue_loss DESC;

COMMENT ON VIEW churn.vw_revenue_at_risk IS
    'Estimated annual revenue (salary proxy) at risk from high-churn-probability customers. '
    'Groups by partner, state, and risk confidence band.';

-- ===========================================================================
-- SECTION 2: STORED PROCEDURES
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- PROCEDURE: sp_load_customer
-- UPSERT a single customer into dim_customers (SCD Type-2 aware)
-- ---------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS churn.sp_load_customer;

CREATE OR REPLACE PROCEDURE churn.sp_load_customer(
    p_customer_id           BIGINT,
    p_gender                VARCHAR(10),
    p_age                   SMALLINT,
    p_num_dependents        SMALLINT,
    p_estimated_salary      NUMERIC(14, 2),
    p_date_of_registration  DATE
)
LANGUAGE plpgsql
AS $$

DECLARE
    v_existing_sk       BIGINT;
    v_has_changed       BOOLEAN := FALSE;
BEGIN
    -- Check if a current record exists for this customer_id
    SELECT customer_sk
    INTO   v_existing_sk
    FROM   churn.dim_customers
    WHERE  customer_id = p_customer_id
      AND  is_current  = TRUE
    LIMIT  1;

    IF FOUND THEN
        -- Detect any attribute change
        SELECT TRUE INTO v_has_changed
        FROM   churn.dim_customers
        WHERE  customer_sk       = v_existing_sk
          AND (
              gender              IS DISTINCT FROM p_gender
           OR age                 IS DISTINCT FROM p_age
           OR num_dependents      IS DISTINCT FROM p_num_dependents
           OR estimated_salary    IS DISTINCT FROM p_estimated_salary
          );

        IF v_has_changed THEN
            -- Expire the current record (SCD Type-2)
            UPDATE churn.dim_customers
            SET    effective_end_date = CURRENT_DATE - 1,
                   is_current         = FALSE,
                   updated_at         = NOW()
            WHERE  customer_sk = v_existing_sk;

            -- Insert the new current version
            INSERT INTO churn.dim_customers (
                customer_id, gender, age, num_dependents,
                estimated_salary, date_of_registration,
                effective_start_date, effective_end_date, is_current
            ) VALUES (
                p_customer_id, p_gender, p_age, p_num_dependents,
                p_estimated_salary, p_date_of_registration,
                CURRENT_DATE, '9999-12-31', TRUE
            );

            RAISE NOTICE 'Customer % updated: old SK=% expired, new record inserted.', p_customer_id, v_existing_sk;
        ELSE
            RAISE NOTICE 'Customer % is unchanged. No action taken.', p_customer_id;
        END IF;
    ELSE
        -- Brand-new customer — insert fresh
        INSERT INTO churn.dim_customers (
            customer_id, gender, age, num_dependents,
            estimated_salary, date_of_registration,
            effective_start_date, effective_end_date, is_current
        ) VALUES (
            p_customer_id, p_gender, p_age, p_num_dependents,
            p_estimated_salary, p_date_of_registration,
            CURRENT_DATE, '9999-12-31', TRUE
        );

        RAISE NOTICE 'Customer % inserted as new record.', p_customer_id;
    END IF;

    COMMIT;

EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE EXCEPTION 'sp_load_customer failed for customer_id=%: %', p_customer_id, SQLERRM;
END;
$$;

COMMENT ON PROCEDURE churn.sp_load_customer IS
    'SCD Type-2 UPSERT for dim_customers. Expires stale rows, inserts new versions '
    'on attribute change, skips unchanged records, and inserts new customers fresh.';

-- ---------------------------------------------------------------------------
-- PROCEDURE: sp_refresh_predictions
-- Populate fact_churn_predictions from a staging table
-- ---------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS churn.sp_refresh_predictions;

CREATE OR REPLACE PROCEDURE churn.sp_refresh_predictions(
    p_model_version     VARCHAR(30),
    p_model_name        VARCHAR(60)         DEFAULT 'XGBoostClassifier',
    p_threshold         NUMERIC(4,3)        DEFAULT 0.500,
    p_snapshot_date     DATE                DEFAULT CURRENT_DATE,
    p_feature_set_ver   VARCHAR(20)         DEFAULT 'v1.0'
)
LANGUAGE plpgsql
AS $$

DECLARE
    v_snap_date_id      INTEGER;
    v_batch_uuid        UUID := GEN_RANDOM_UUID();
    v_rows_inserted     BIGINT := 0;
BEGIN
    -- Resolve snapshot date to dim_date surrogate key
    SELECT date_id INTO v_snap_date_id
    FROM   churn.dim_date
    WHERE  full_date = p_snapshot_date;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Snapshot date % not found in dim_date. Populate dim_date first.', p_snapshot_date;
    END IF;

    -- Ensure staging table exists (callers pre-load it)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE  table_schema = 'churn' AND table_name = 'stg_predictions'
    ) THEN
        RAISE EXCEPTION 'Staging table churn.stg_predictions does not exist. Create and load it before calling this procedure.';
    END IF;

    -- Bulk insert, resolving customer_sk from dim_customers
    INSERT INTO churn.fact_churn_predictions (
        customer_id,
        customer_sk,
        snapshot_date_id,
        predicted_prob,
        predicted_churn,
        threshold,
        model_version,
        model_name,
        feature_set_version,
        prediction_batch_id
    )
    SELECT
        sp.customer_id,
        dc.customer_sk,
        v_snap_date_id,
        sp.predicted_prob,
        CASE WHEN sp.predicted_prob >= p_threshold THEN 1 ELSE 0 END,
        p_threshold,
        p_model_version,
        p_model_name,
        p_feature_set_ver,
        v_batch_uuid
    FROM       churn.stg_predictions  sp
    JOIN       churn.dim_customers    dc
           ON  dc.customer_id = sp.customer_id
           AND dc.is_current  = TRUE
    ON CONFLICT (customer_id, prediction_batch_id) DO NOTHING;

    GET DIAGNOSTICS v_rows_inserted = ROW_COUNT;

    RAISE NOTICE 'sp_refresh_predictions: % rows inserted. Batch UUID = %, Model = %, Snapshot = %',
        v_rows_inserted, v_batch_uuid, p_model_version, p_snapshot_date;

    COMMIT;

EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE EXCEPTION 'sp_refresh_predictions failed: %', SQLERRM;
END;
$$;

COMMENT ON PROCEDURE churn.sp_refresh_predictions IS
    'Bulk-loads ML churn predictions from churn.stg_predictions staging table '
    'into fact_churn_predictions. Resolves customer_sk, applies decision threshold, '
    'and tags records with a batch UUID for full lineage tracking.';

-- ===========================================================================
-- SECTION 3: SCALAR FUNCTIONS
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- FUNCTION: fn_get_churn_rate
-- Returns the churn rate percentage for a given telecom partner name
-- ---------------------------------------------------------------------------
DROP FUNCTION IF EXISTS churn.fn_get_churn_rate(VARCHAR);

CREATE OR REPLACE FUNCTION churn.fn_get_churn_rate(
    p_partner_name  VARCHAR(100)
)
RETURNS NUMERIC(6, 2)
LANGUAGE plpgsql
STABLE  -- result is stable within a single transaction given same inputs
AS $$

DECLARE
    v_churn_rate    NUMERIC(6, 2);
BEGIN
    SELECT
        ROUND(
            SUM(fu.churn)::NUMERIC * 100.0 / NULLIF(COUNT(*), 0),
            2
        )
    INTO  v_churn_rate
    FROM  churn.fact_usage          fu
    JOIN  churn.dim_telecom_partner tp ON tp.partner_id  = fu.partner_id
    WHERE LOWER(tp.partner_name) = LOWER(p_partner_name);

    RETURN v_churn_rate;

EXCEPTION
    WHEN OTHERS THEN
        RAISE WARNING 'fn_get_churn_rate: Error for partner "%": %', p_partner_name, SQLERRM;
        RETURN NULL;
END;
$$;

COMMENT ON FUNCTION churn.fn_get_churn_rate(VARCHAR) IS
    'Returns the overall churn rate (%) for the named telecom partner. '
    'Case-insensitive match. Returns NULL if partner not found or on error.';

-- ---------------------------------------------------------------------------
-- FUNCTION: fn_calculate_mrr_risk
-- Returns estimated Monthly Recurring Revenue at risk for a given segment
-- ---------------------------------------------------------------------------
DROP FUNCTION IF EXISTS churn.fn_calculate_mrr_risk(VARCHAR, VARCHAR);

CREATE OR REPLACE FUNCTION churn.fn_calculate_mrr_risk(
    p_partner_name  VARCHAR(100),
    p_state         VARCHAR(100)    DEFAULT NULL  -- NULL = all states for the partner
)
RETURNS NUMERIC(18, 2)
LANGUAGE plpgsql
STABLE
AS $$

DECLARE
    v_mrr_risk      NUMERIC(18, 2);
BEGIN
    SELECT
        COALESCE(
            SUM(fcp.predicted_prob * dc.estimated_salary / 12.0),
            0
        )
    INTO  v_mrr_risk
    FROM  churn.fact_churn_predictions  fcp
    JOIN  churn.dim_customers           dc  ON dc.customer_sk   = fcp.customer_sk AND dc.is_current
    JOIN  churn.fact_usage              fu  ON fu.customer_sk   = fcp.customer_sk
                                          AND fu.snapshot_date_id = fcp.snapshot_date_id
    JOIN  churn.dim_geography           dg  ON dg.geography_id  = fu.geography_id
    JOIN  churn.dim_telecom_partner     tp  ON tp.partner_id    = fu.partner_id
    WHERE LOWER(tp.partner_name)            = LOWER(p_partner_name)
      AND (p_state IS NULL OR LOWER(dg.state) = LOWER(p_state))
      AND fcp.predicted_prob > 0.70;  -- only high-risk

    RETURN v_mrr_risk;

EXCEPTION
    WHEN OTHERS THEN
        RAISE WARNING 'fn_calculate_mrr_risk: Error: %', SQLERRM;
        RETURN 0;
END;
$$;

COMMENT ON FUNCTION churn.fn_calculate_mrr_risk(VARCHAR, VARCHAR) IS
    'Estimates monthly recurring revenue (MRR) at risk from high-probability churners '
    '(predicted_prob > 0.70) for a given partner and optionally a state. '
    'Uses salary/12 as MRR proxy. Returns INR amount.';

-- ===========================================================================
-- SECTION 4: TRIGGER
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- TRIGGER FUNCTION: fn_audit_churn_predictions
-- ---------------------------------------------------------------------------
DROP FUNCTION IF EXISTS churn.fn_audit_churn_predictions() CASCADE;

CREATE OR REPLACE FUNCTION churn.fn_audit_churn_predictions()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$

BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO churn.audit_churn_predictions (
            prediction_id,
            customer_id,
            predicted_prob,
            predicted_churn,
            model_version,
            action_type,
            action_by,
            action_at
        ) VALUES (
            NEW.prediction_id,
            NEW.customer_id,
            NEW.predicted_prob,
            NEW.predicted_churn,
            NEW.model_version,
            'INSERT',
            CURRENT_USER,
            NOW()
        );
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO churn.audit_churn_predictions (
            prediction_id,
            customer_id,
            predicted_prob,
            predicted_churn,
            model_version,
            action_type,
            action_by,
            action_at
        ) VALUES (
            NEW.prediction_id,
            NEW.customer_id,
            NEW.predicted_prob,
            NEW.predicted_churn,
            NEW.model_version,
            'UPDATE',
            CURRENT_USER,
            NOW()
        );
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO churn.audit_churn_predictions (
            prediction_id,
            customer_id,
            predicted_prob,
            predicted_churn,
            model_version,
            action_type,
            action_by,
            action_at
        ) VALUES (
            OLD.prediction_id,
            OLD.customer_id,
            OLD.predicted_prob,
            OLD.predicted_churn,
            OLD.model_version,
            'DELETE',
            CURRENT_USER,
            NOW()
        );
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION churn.fn_audit_churn_predictions() IS
    'Trigger function: captures INSERT/UPDATE/DELETE events on fact_churn_predictions '
    'and writes an immutable audit record to audit_churn_predictions.';

-- ---------------------------------------------------------------------------
-- TRIGGER: tr_audit_churn_predictions
-- ---------------------------------------------------------------------------
DROP TRIGGER IF EXISTS tr_audit_churn_predictions ON churn.fact_churn_predictions;

CREATE TRIGGER tr_audit_churn_predictions
    AFTER INSERT OR UPDATE OR DELETE
    ON churn.fact_churn_predictions
    FOR EACH ROW
    EXECUTE FUNCTION churn.fn_audit_churn_predictions();

COMMENT ON TRIGGER tr_audit_churn_predictions ON churn.fact_churn_predictions IS
    'Logs all INSERT, UPDATE, and DELETE operations on fact_churn_predictions '
    'to the audit_churn_predictions table for compliance and debugging.';

-- ===========================================================================
-- SECTION 5: ADDITIONAL UTILITY VIEWS
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- VIEW 6: vw_feature_stats
-- Descriptive statistics for all engineered features (for ML validation)
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS churn.vw_feature_stats CASCADE;

CREATE OR REPLACE VIEW churn.vw_feature_stats AS

SELECT
    'tenure_months'         AS feature_name,
    AVG(tenure_months)      AS mean_val,
    STDDEV(tenure_months)   AS std_val,
    MIN(tenure_months)      AS min_val,
    MAX(tenure_months)      AS max_val,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY tenure_months) AS median_val
FROM churn.fact_usage

UNION ALL

SELECT 'calls_per_month',
    AVG(calls_per_month), STDDEV(calls_per_month),
    MIN(calls_per_month), MAX(calls_per_month),
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY calls_per_month)
FROM churn.fact_usage

UNION ALL

SELECT 'data_per_month',
    AVG(data_per_month), STDDEV(data_per_month),
    MIN(data_per_month), MAX(data_per_month),
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY data_per_month)
FROM churn.fact_usage

UNION ALL

SELECT 'sms_per_month',
    AVG(sms_per_month), STDDEV(sms_per_month),
    MIN(sms_per_month), MAX(sms_per_month),
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY sms_per_month)
FROM churn.fact_usage

UNION ALL

SELECT 'usage_score',
    AVG(usage_score), STDDEV(usage_score),
    MIN(usage_score), MAX(usage_score),
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY usage_score)
FROM churn.fact_usage

UNION ALL

SELECT 'estimated_salary_log',
    AVG(estimated_salary_log), STDDEV(estimated_salary_log),
    MIN(estimated_salary_log), MAX(estimated_salary_log),
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY estimated_salary_log)
FROM churn.fact_usage;

COMMENT ON VIEW churn.vw_feature_stats IS
    'Descriptive statistics (mean, std, min, max, median) for all numeric '
    'engineered features in fact_usage. Used for ML pipeline validation.';

-- ---------------------------------------------------------------------------
-- VIEW 7: vw_partner_scorecard
-- One-row-per-partner executive scorecard
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS churn.vw_partner_scorecard CASCADE;

CREATE OR REPLACE VIEW churn.vw_partner_scorecard AS
SELECT
    tp.partner_name                                                     AS telecom_partner,
    tp.market_share                                                     AS market_share_pct,
    COUNT(DISTINCT fu.customer_id)                                      AS total_subscribers,
    SUM(fu.churn)                                                       AS total_churned,
    ROUND(SUM(fu.churn)::NUMERIC * 100.0 / NULLIF(COUNT(*), 0), 2)    AS churn_rate_pct,
    ROUND(AVG(fu.usage_score), 4)                                       AS avg_usage_score,
    ROUND(AVG(fu.tenure_months), 1)                                     AS avg_tenure_months,
    ROUND(AVG(dc.estimated_salary), 2)                                  AS avg_customer_salary,
    SUM(CASE WHEN fu.is_low_engagement = 1 THEN 1 ELSE 0 END)          AS low_engagement_count,
    ROUND(
        SUM(CASE WHEN fu.is_low_engagement = 1 THEN 1 ELSE 0 END)::NUMERIC
        * 100.0 / NULLIF(COUNT(*), 0), 2
    )                                                                   AS low_engagement_pct
FROM churn.fact_usage          fu
JOIN churn.dim_customers       dc ON dc.customer_sk = fu.customer_sk AND dc.is_current
JOIN churn.dim_telecom_partner tp ON tp.partner_id  = fu.partner_id
GROUP BY tp.partner_name, tp.market_share
ORDER BY churn_rate_pct DESC;

COMMENT ON VIEW churn.vw_partner_scorecard IS
    'Executive one-row-per-partner scorecard with churn rate, usage score, '
    'tenure, salary, and low-engagement metrics.';
