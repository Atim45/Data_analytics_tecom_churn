CREATE SCHEMA IF NOT EXISTS churn AUTHORIZATION postgres;
COMMENT ON SCHEMA churn IS 'Primary schema for telecom churn star schema objects.';

SET search_path TO churn, public;

-- DIMENSION TABLES

DROP TABLE IF EXISTS churn.dim_customers CASCADE;

CREATE TABLE churn.dim_customers (
    -- ---------------- Surrogate / Natural Keys ----------------
    customer_id             BIGINT          NOT NULL,   
    customer_sk             BIGSERIAL       NOT NULL,   

    -- ---------------- Demographics ----------------
    gender                  VARCHAR(10)     NOT NULL    
                                CHECK (gender IN ('Male', 'Female', 'Other')),
    age                     SMALLINT        NOT NULL    
                                CHECK (age BETWEEN 0 AND 120),
    num_dependents          SMALLINT        NOT NULL DEFAULT 0  
                                CHECK (num_dependents BETWEEN 0 AND 20),
    estimated_salary        NUMERIC(14, 2)  NOT NULL    
                                CHECK (estimated_salary >= 0),

    -- ---------------- Registration ----------------
    date_of_registration    DATE            NOT NULL,   

    -- ---------------- Derived Demographics ----------------
    age_group               VARCHAR(20)     GENERATED ALWAYS AS (
                                CASE
                                    WHEN age BETWEEN 18 AND 30 THEN '18-30'
                                    WHEN age BETWEEN 31 AND 45 THEN '31-45'
                                    WHEN age BETWEEN 46 AND 60 THEN '46-60'
                                    WHEN age BETWEEN 61 AND 75 THEN '61-75'
                                    ELSE '76+'
                                END
                            ) STORED,

    salary_tier             VARCHAR(20)     GENERATED ALWAYS AS (
                                CASE
                                    WHEN estimated_salary < 25000   THEN 'Low'
                                    WHEN estimated_salary < 75000   THEN 'Mid'
                                    WHEN estimated_salary < 150000  THEN 'High'
                                    ELSE 'Premium'
                                END
                            ) STORED,

    -- ---------------- SCD Type-2 Metadata ----------------
    effective_start_date    DATE            NOT NULL DEFAULT CURRENT_DATE,  
    effective_end_date      DATE            NOT NULL DEFAULT '9999-12-31',  
    is_current              BOOLEAN         NOT NULL DEFAULT TRUE,           

    -- ---------------- Audit ----------------
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),          
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),          

    -- ---------------- Constraints ----------------
    CONSTRAINT pk_dim_customers PRIMARY KEY (customer_sk),
    CONSTRAINT uq_dim_customers_id_current UNIQUE (customer_id, is_current)
);

COMMENT ON TABLE churn.dim_customers IS
    'Slowly Changing Dimension (SCD Type-2) for telecom customers. '
    'Tracks all historical changes to customer demographics.';

-- DIM_GEOGRAPHY

DROP TABLE IF EXISTS churn.dim_geography CASCADE;

CREATE TABLE churn.dim_geography (
    -- ---------------- Keys ----------------
    geography_id    SERIAL          NOT NULL,   
    pincode         VARCHAR(10)     NOT NULL,   
    city            VARCHAR(100)    NOT NULL,   
    state           VARCHAR(100)    NOT NULL,   
    country         VARCHAR(60)     NOT NULL DEFAULT 'India',  
    region          VARCHAR(50),                
    timezone        VARCHAR(40)     NOT NULL DEFAULT 'Asia/Kolkata', 

    -- ---------------- Audit ----------------
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- ---------------- Constraints ----------------
    CONSTRAINT pk_dim_geography PRIMARY KEY (geography_id),
    CONSTRAINT uq_dim_geography_pincode UNIQUE (pincode, city, state)
);

COMMENT ON TABLE churn.dim_geography IS
    'Geographic dimension mapping customer locations to state/city/pincode hierarchies.';
COMMENT ON COLUMN churn.dim_geography.pincode IS '6-digit India Post PIN code. E.g., 110001 for New Delhi.';
COMMENT ON COLUMN churn.dim_geography.region IS 'Aggregated regional grouping for macro-level analysis.';


-- DIM_TELECOM_PARTNER

DROP TABLE IF EXISTS churn.dim_telecom_partner CASCADE;

CREATE TABLE churn.dim_telecom_partner (
    -- ---------------- Keys ----------------
    partner_id          SERIAL          NOT NULL,   
    partner_name        VARCHAR(100)    NOT NULL,   
    partner_code        VARCHAR(10)     NOT NULL, 

    -- ---------------- Business Attributes ----------------
    market_share        NUMERIC(5, 2)               
                            CHECK (market_share BETWEEN 0 AND 100),
    technology          VARCHAR(20),               
    hq_city             VARCHAR(100),              
    founded_year        SMALLINT,                   
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,  

    -- ---------------- Audit ----------------
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- ---------------- Constraints ----------------
    CONSTRAINT pk_dim_telecom_partner PRIMARY KEY (partner_id),
    CONSTRAINT uq_dim_telecom_partner_name UNIQUE (partner_name),
    CONSTRAINT uq_dim_telecom_partner_code UNIQUE (partner_code)
);

COMMENT ON TABLE churn.dim_telecom_partner IS
    'Telecom operator/partner dimension. Stores brand metadata and market share.';
COMMENT ON COLUMN churn.dim_telecom_partner.market_share IS
    'Percentage of total subscriber base. E.g., 35.50 = 35.5% market share.';


-- DIM_DATE  (Full Date Dimension)

DROP TABLE IF EXISTS churn.dim_date CASCADE;

CREATE TABLE churn.dim_date (
    -- ---------------- Keys ----------------
    date_id             INTEGER         NOT NULL,   
    full_date           DATE            NOT NULL,   

    -- ---------------- Year/Quarter ----------------
    calendar_year       SMALLINT        NOT NULL,   
    fiscal_year         SMALLINT        NOT NULL,   
    quarter_number      SMALLINT        NOT NULL    
                            CHECK (quarter_number BETWEEN 1 AND 4),
    quarter_name        VARCHAR(6)      NOT NULL,   
    fiscal_quarter      VARCHAR(6)      NOT NULL,   

    -- ---------------- Month ----------------
    month_number        SMALLINT        NOT NULL    
                            CHECK (month_number BETWEEN 1 AND 12),
    month_name          VARCHAR(12)     NOT NULL,   
    month_name_short    VARCHAR(3)      NOT NULL,   
    month_start_date    DATE            NOT NULL,  
    month_end_date      DATE            NOT NULL,   

    -- ---------------- Week ----------------
    week_number         SMALLINT        NOT NULL,   
    week_start_date     DATE            NOT NULL,   
    week_end_date       DATE            NOT NULL,   

    -- ---------------- Day ----------------
    day_of_month        SMALLINT        NOT NULL    
                            CHECK (day_of_month BETWEEN 1 AND 31),
    day_of_week         SMALLINT        NOT NULL    
                            CHECK (day_of_week BETWEEN 1 AND 7),
    day_name            VARCHAR(12)     NOT NULL,   
    day_name_short      VARCHAR(3)      NOT NULL,   
    day_of_year         SMALLINT        NOT NULL,   

    -- ---------------- Flags ----------------
    is_weekend          BOOLEAN         NOT NULL,  
    is_month_start      BOOLEAN         NOT NULL,  
    is_month_end        BOOLEAN         NOT NULL,  
    is_quarter_start    BOOLEAN         NOT NULL,   
    is_quarter_end      BOOLEAN         NOT NULL,   
    is_leap_year        BOOLEAN         NOT NULL,   

    -- ---------------- Constraints ----------------
    CONSTRAINT pk_dim_date PRIMARY KEY (date_id),
    CONSTRAINT uq_dim_date_full_date UNIQUE (full_date)
);

COMMENT ON TABLE churn.dim_date IS
    'Fully populated date dimension spanning 2000-01-01 to 2030-12-31. '
    'Supports calendar and India fiscal year (April–March) analysis.';
COMMENT ON COLUMN churn.dim_date.date_id IS 'Integer surrogate key in YYYYMMDD format for fast joins.';
COMMENT ON COLUMN churn.dim_date.fiscal_year IS
    'India fiscal year where FY2024 = 1 Apr 2023 – 31 Mar 2024.';

-- ---------------------------------------------------------------------------
-- Populate DIM_DATE (2015-01-01 to 2030-12-31)
-- ---------------------------------------------------------------------------
INSERT INTO churn.dim_date (
    date_id, full_date,
    calendar_year, fiscal_year,
    quarter_number, quarter_name, fiscal_quarter,
    month_number, month_name, month_name_short, month_start_date, month_end_date,
    week_number, week_start_date, week_end_date,
    day_of_month, day_of_week, day_name, day_name_short, day_of_year,
    is_weekend, is_month_start, is_month_end, is_quarter_start, is_quarter_end, is_leap_year
)
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INTEGER                     AS date_id,
    d                                                    AS full_date,
    EXTRACT(YEAR FROM d)::SMALLINT                      AS calendar_year,
    CASE WHEN EXTRACT(MONTH FROM d) >= 4
         THEN EXTRACT(YEAR FROM d)::SMALLINT + 1
         ELSE EXTRACT(YEAR FROM d)::SMALLINT
    END                                                 AS fiscal_year,
    EXTRACT(QUARTER FROM d)::SMALLINT                   AS quarter_number,
    'Q' || EXTRACT(QUARTER FROM d)::TEXT                AS quarter_name,
    CASE
        WHEN EXTRACT(MONTH FROM d) IN (4,5,6)   THEN 'FQ1'
        WHEN EXTRACT(MONTH FROM d) IN (7,8,9)   THEN 'FQ2'
        WHEN EXTRACT(MONTH FROM d) IN (10,11,12) THEN 'FQ3'
        ELSE 'FQ4'
    END                                                 AS fiscal_quarter,
    EXTRACT(MONTH FROM d)::SMALLINT                     AS month_number,
    TO_CHAR(d, 'Month')                                 AS month_name,
    TO_CHAR(d, 'Mon')                                   AS month_name_short,
    DATE_TRUNC('month', d)::DATE                        AS month_start_date,
    (DATE_TRUNC('month', d) + INTERVAL '1 month' - INTERVAL '1 day')::DATE AS month_end_date,
    EXTRACT(WEEK FROM d)::SMALLINT                      AS week_number,
    (d - (EXTRACT(ISODOW FROM d)::INTEGER - 1) * INTERVAL '1 day')::DATE  AS week_start_date,
    (d + (7 - EXTRACT(ISODOW FROM d)::INTEGER) * INTERVAL '1 day')::DATE  AS week_end_date,
    EXTRACT(DAY FROM d)::SMALLINT                       AS day_of_month,
    EXTRACT(ISODOW FROM d)::SMALLINT                    AS day_of_week,
    TO_CHAR(d, 'Day')                                   AS day_name,
    TO_CHAR(d, 'Dy')                                    AS day_name_short,
    EXTRACT(DOY FROM d)::SMALLINT                       AS day_of_year,
    EXTRACT(ISODOW FROM d) IN (6, 7)                    AS is_weekend,
    d = DATE_TRUNC('month', d)::DATE                    AS is_month_start,
    d = (DATE_TRUNC('month', d) + INTERVAL '1 month' - INTERVAL '1 day')::DATE AS is_month_end,
    EXTRACT(DAY FROM d) = 1 AND EXTRACT(MONTH FROM d) IN (1,4,7,10)        AS is_quarter_start,
    d = (DATE_TRUNC('quarter', d) + INTERVAL '3 months' - INTERVAL '1 day')::DATE AS is_quarter_end,
    EXTRACT(YEAR FROM d)::INTEGER % 4 = 0
        AND (EXTRACT(YEAR FROM d)::INTEGER % 100 <> 0
             OR EXTRACT(YEAR FROM d)::INTEGER % 400 = 0)                   AS is_leap_year
FROM GENERATE_SERIES('2015-01-01'::DATE, '2030-12-31'::DATE, '1 day'::INTERVAL) AS g(d);

-- ===========================================================================
-- FACT TABLES
-- ===========================================================================

DROP TABLE IF EXISTS churn.fact_usage CASCADE;

CREATE TABLE churn.fact_usage (
    -- ---------------- Surrogate PK ----------------
    usage_id                BIGSERIAL       NOT NULL,   
    -- ---------------- Foreign Keys ----------------
    customer_sk             BIGINT          NOT NULL,   
    customer_id             BIGINT          NOT NULL,   
    geography_id            INTEGER         NOT NULL,   
    partner_id              INTEGER         NOT NULL,   
    registration_date_id    INTEGER         NOT NULL,   
    snapshot_date_id        INTEGER         NOT NULL,   

    -- ---------------- Raw Usage Metrics ----------------
    calls_made              INTEGER         NOT NULL DEFAULT 0   
                                CHECK (calls_made >= 0),
    sms_sent                INTEGER         NOT NULL DEFAULT 0  
                                CHECK (sms_sent >= 0),
    data_used               NUMERIC(10, 3)  NOT NULL DEFAULT 0   
                                CHECK (data_used >= 0),

    -- ---------------- Churn Flag ----------------
    churn                   SMALLINT        NOT NULL DEFAULT 0   
                                CHECK (churn IN (0, 1)),

    -- ==============================================================
    -- ENGINEERED FEATURES
    -- ==============================================================

    -- Tenure (months since registration to snapshot date)
    tenure_months           NUMERIC(6, 2)   NOT NULL DEFAULT 0   
                                CHECK (tenure_months >= 0),

    -- Normalised usage rates
    calls_per_month         NUMERIC(8, 2)   NOT NULL DEFAULT 0   
                                CHECK (calls_per_month >= 0),
    data_per_month          NUMERIC(10, 4)  NOT NULL DEFAULT 0   
                                CHECK (data_per_month >= 0),
    sms_per_month           NUMERIC(8, 2)   NOT NULL DEFAULT 0   
                                CHECK (sms_per_month >= 0),

    -- Cross-metric ratios
    data_per_call           NUMERIC(10, 4)  NOT NULL DEFAULT 0   
                                CHECK (data_per_call >= 0),
    sms_to_call_ratio       NUMERIC(10, 4)  NOT NULL DEFAULT 0   
                                CHECK (sms_to_call_ratio >= 0),

    -- Interaction features
    age_x_dependents        NUMERIC(8, 2)   NOT NULL DEFAULT 0   
                                CHECK (age_x_dependents >= 0),

    -- Transformed features
    estimated_salary_log    NUMERIC(12, 6)  NOT NULL DEFAULT 0   

    -- Composite score
    ,usage_score            NUMERIC(10, 4)  NOT NULL DEFAULT 0   

    -- Binary engagement flags
    ,is_low_engagement      SMALLINT        NOT NULL DEFAULT 0   
                                CHECK (is_low_engagement IN (0, 1)),
    low_usage_high_tenure   SMALLINT        NOT NULL DEFAULT 0   
                                CHECK (low_usage_high_tenure IN (0, 1)),

    -- ---------------- Audit ----------------
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- ---------------- Constraints ----------------
    CONSTRAINT pk_fact_usage PRIMARY KEY (usage_id, snapshot_date_id),
    CONSTRAINT fk_fact_usage_customer  FOREIGN KEY (customer_sk)
        REFERENCES churn.dim_customers (customer_sk) ON DELETE RESTRICT,
    CONSTRAINT fk_fact_usage_geography FOREIGN KEY (geography_id)
        REFERENCES churn.dim_geography (geography_id) ON DELETE RESTRICT,
    CONSTRAINT fk_fact_usage_partner   FOREIGN KEY (partner_id)
        REFERENCES churn.dim_telecom_partner (partner_id) ON DELETE RESTRICT,
    CONSTRAINT fk_fact_usage_reg_date  FOREIGN KEY (registration_date_id)
        REFERENCES churn.dim_date (date_id) ON DELETE RESTRICT,
    CONSTRAINT fk_fact_usage_snap_date FOREIGN KEY (snapshot_date_id)
        REFERENCES churn.dim_date (date_id) ON DELETE RESTRICT
) PARTITION BY RANGE (snapshot_date_id);

COMMENT ON TABLE churn.fact_usage IS
    'Central grain fact table: one row per customer per monthly snapshot. '
    'Contains raw usage metrics, churn label, and all engineered ML features.';
COMMENT ON COLUMN churn.fact_usage.usage_score IS
    'Composite engagement score combining calls, data, and SMS usage. '
    'Higher = more engaged. Formula: (calls_made/100 + data_used + sms_sent/100) / 3.';
COMMENT ON COLUMN churn.fact_usage.is_low_engagement IS
    '1 if customer made < 10 calls AND used < 1 GB data AND sent < 5 SMS in the period.';
COMMENT ON COLUMN churn.fact_usage.low_usage_high_tenure IS
    '1 if is_low_engagement = 1 AND tenure_months > 12. '
    'High-risk segment: long-term customers with minimal engagement.';

-- Partition for 2015-2019 historical data
CREATE TABLE churn.fact_usage_2015_2019
    PARTITION OF churn.fact_usage
    FOR VALUES FROM (20150101) TO (20200101);

-- Partition per year 2020-2030
CREATE TABLE churn.fact_usage_2020
    PARTITION OF churn.fact_usage FOR VALUES FROM (20200101) TO (20210101);
CREATE TABLE churn.fact_usage_2021
    PARTITION OF churn.fact_usage FOR VALUES FROM (20210101) TO (20220101);
CREATE TABLE churn.fact_usage_2022
    PARTITION OF churn.fact_usage FOR VALUES FROM (20220101) TO (20230101);
CREATE TABLE churn.fact_usage_2023
    PARTITION OF churn.fact_usage FOR VALUES FROM (20230101) TO (20240101);
CREATE TABLE churn.fact_usage_2024
    PARTITION OF churn.fact_usage FOR VALUES FROM (20240101) TO (20250101);
CREATE TABLE churn.fact_usage_2025
    PARTITION OF churn.fact_usage FOR VALUES FROM (20250101) TO (20260101);
CREATE TABLE churn.fact_usage_2026
    PARTITION OF churn.fact_usage FOR VALUES FROM (20260101) TO (20270101);
CREATE TABLE churn.fact_usage_default
    PARTITION OF churn.fact_usage DEFAULT;

-- ---------------------------------------------------------------------------
-- FACT_CHURN_PREDICTIONS
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS churn.fact_churn_predictions CASCADE;

CREATE TABLE churn.fact_churn_predictions (
    -- ---------------- Keys ----------------
    prediction_id       BIGSERIAL       NOT NULL,   
    customer_id         BIGINT          NOT NULL,   
    customer_sk         BIGINT          NOT NULL,   
    snapshot_date_id    INTEGER         NOT NULL,   

    -- ---------------- Model Outputs ----------------
    predicted_prob      NUMERIC(6, 5)   NOT NULL    
                            CHECK (predicted_prob BETWEEN 0 AND 1),
    predicted_churn     SMALLINT        NOT NULL   
                            CHECK (predicted_churn IN (0, 1)),
    threshold           NUMERIC(4, 3)   NOT NULL DEFAULT 0.500 
                            CHECK (threshold BETWEEN 0 AND 1),

    -- ---------------- Model Metadata ----------------
    model_version       VARCHAR(30)     NOT NULL,  
    model_name          VARCHAR(60),                
    feature_set_version VARCHAR(20),                
    prediction_batch_id UUID            NOT NULL DEFAULT GEN_RANDOM_UUID(), 

    -- ---------------- Calibration / Uncertainty ----------------
    confidence_band     VARCHAR(10)     GENERATED ALWAYS AS (
                            CASE
                                WHEN predicted_prob < 0.3  THEN 'Low'
                                WHEN predicted_prob < 0.7  THEN 'Medium'
                                ELSE 'High'
                            END
                        ) STORED,                   

    -- ---------------- Audit ----------------
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- ---------------- Constraints ----------------
    CONSTRAINT pk_fact_churn_predictions PRIMARY KEY (prediction_id),
    CONSTRAINT fk_fcp_customer  FOREIGN KEY (customer_sk)
        REFERENCES churn.dim_customers (customer_sk) ON DELETE CASCADE,
    CONSTRAINT fk_fcp_snap_date FOREIGN KEY (snapshot_date_id)
        REFERENCES churn.dim_date (date_id) ON DELETE RESTRICT,
    CONSTRAINT uq_fcp_customer_batch UNIQUE (customer_id, prediction_batch_id)
);

COMMENT ON TABLE churn.fact_churn_predictions IS
    'Stores ML model churn probability predictions per customer per batch run. '
    'Supports multi-model versioning and threshold sensitivity analysis.';
COMMENT ON COLUMN churn.fact_churn_predictions.predicted_prob IS
    'Raw model output probability in [0, 1]. E.g., 0.82300 = 82.3% churn probability.';
COMMENT ON COLUMN churn.fact_churn_predictions.model_version IS
    'Semantic version with algorithm suffix. E.g., v2.1.0-xgb = XGBoost version 2.1.0.';

-- ---------------------------------------------------------------------------
-- AUDIT TABLE 
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS churn.audit_churn_predictions CASCADE;

CREATE TABLE churn.audit_churn_predictions (
    audit_id            BIGSERIAL       NOT NULL,
    prediction_id       BIGINT,
    customer_id         BIGINT,
    predicted_prob      NUMERIC(6, 5),
    predicted_churn     SMALLINT,
    model_version       VARCHAR(30),
    action_type         VARCHAR(10)     NOT NULL DEFAULT 'INSERT', 
    action_by           VARCHAR(100)    NOT NULL DEFAULT CURRENT_USER,
    action_at           TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_audit_churn_predictions PRIMARY KEY (audit_id)
);

COMMENT ON TABLE churn.audit_churn_predictions IS
    'Immutable audit log for all DML events on fact_churn_predictions, populated by triggers.';

-- ===========================================================================
-- INDEXES
-- ===========================================================================

-- dim_customers
CREATE INDEX idx_dim_customers_customer_id   ON churn.dim_customers (customer_id);
CREATE INDEX idx_dim_customers_is_current    ON churn.dim_customers (is_current) WHERE is_current = TRUE;
CREATE INDEX idx_dim_customers_age_group     ON churn.dim_customers (age_group);
CREATE INDEX idx_dim_customers_salary_tier   ON churn.dim_customers (salary_tier);
CREATE INDEX idx_dim_customers_gender        ON churn.dim_customers (gender);
CREATE INDEX idx_dim_customers_reg_date      ON churn.dim_customers (date_of_registration);

-- dim_geography
CREATE INDEX idx_dim_geography_state         ON churn.dim_geography (state);
CREATE INDEX idx_dim_geography_city          ON churn.dim_geography (city);
CREATE INDEX idx_dim_geography_pincode       ON churn.dim_geography (pincode);

-- dim_telecom_partner
CREATE INDEX idx_dim_tp_partner_name         ON churn.dim_telecom_partner (partner_name);
CREATE INDEX idx_dim_tp_is_active            ON churn.dim_telecom_partner (is_active) WHERE is_active = TRUE;

-- dim_date
CREATE INDEX idx_dim_date_calendar_year      ON churn.dim_date (calendar_year);
CREATE INDEX idx_dim_date_month_number       ON churn.dim_date (month_number);
CREATE INDEX idx_dim_date_quarter_number     ON churn.dim_date (quarter_number);
CREATE INDEX idx_dim_date_is_month_end       ON churn.dim_date (is_month_end) WHERE is_month_end = TRUE;

-- fact_usage (on each partition inherits automatically for PG 11+)
CREATE INDEX idx_fact_usage_customer_id      ON churn.fact_usage (customer_id);
CREATE INDEX idx_fact_usage_customer_sk      ON churn.fact_usage (customer_sk);
CREATE INDEX idx_fact_usage_geography_id     ON churn.fact_usage (geography_id);
CREATE INDEX idx_fact_usage_partner_id       ON churn.fact_usage (partner_id);
CREATE INDEX idx_fact_usage_snap_date_id     ON churn.fact_usage (snapshot_date_id);
CREATE INDEX idx_fact_usage_churn            ON churn.fact_usage (churn);
CREATE INDEX idx_fact_usage_is_low_eng       ON churn.fact_usage (is_low_engagement) WHERE is_low_engagement = 1;
CREATE INDEX idx_fact_usage_usage_score      ON churn.fact_usage (usage_score);
CREATE INDEX idx_fact_usage_tenure           ON churn.fact_usage (tenure_months);

-- fact_churn_predictions
CREATE INDEX idx_fcp_customer_id             ON churn.fact_churn_predictions (customer_id);
CREATE INDEX idx_fcp_customer_sk             ON churn.fact_churn_predictions (customer_sk);
CREATE INDEX idx_fcp_snap_date_id            ON churn.fact_churn_predictions (snapshot_date_id);
CREATE INDEX idx_fcp_predicted_prob          ON churn.fact_churn_predictions (predicted_prob DESC);
CREATE INDEX idx_fcp_model_version           ON churn.fact_churn_predictions (model_version);
CREATE INDEX idx_fcp_high_risk               ON churn.fact_churn_predictions (predicted_prob)
    WHERE predicted_prob > 0.7;
CREATE INDEX idx_fcp_batch_id                ON churn.fact_churn_predictions (prediction_batch_id);

-- audit_churn_predictions
CREATE INDEX idx_audit_fcp_prediction_id     ON churn.audit_churn_predictions (prediction_id);
CREATE INDEX idx_audit_fcp_customer_id       ON churn.audit_churn_predictions (customer_id);
CREATE INDEX idx_audit_fcp_action_at         ON churn.audit_churn_predictions (action_at DESC);

