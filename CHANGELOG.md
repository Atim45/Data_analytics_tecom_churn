# Changelog

All notable changes to the **Telecom Customer Churn Prediction** project are documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/) (MAJOR.MINOR.PATCH) and the [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format.

---

## [Unreleased]

### Planned
- Real-time Kafka stream processing for live churn scoring
- Model retraining pipeline with data drift detection
- A/B testing framework for model versioning
- AWS SageMaker deployment option
- CatBoost and TabNet model additions
- Customer lifetime value (CLV) integration

---

## [2.1.0] — 2026-07-10

### 🚀 Major Release: Production Deployment

#### Added
- **FastAPI REST API** with 6 endpoints including real-time prediction, batch scoring, SHAP explanations, and model metadata
- **Streamlit interactive dashboard** with SHAP waterfall plots, risk distribution charts, and live prediction explorer
- **Docker & Docker Compose** configuration for one-command full-stack deployment
- **PostgreSQL integration** with SQLAlchemy ORM, connection pooling, and async support
- **SHAP explainability endpoint** (`/explain`) returning per-customer feature attributions
- **Batch prediction endpoint** supporting up to 10,000 records per request
- **Health check endpoint** with model status, version, and uptime metrics
- Full **OpenAPI/Swagger documentation** auto-generated at `/docs`

#### Changed
- API response now includes `risk_tier` (LOW/MEDIUM/HIGH/CRITICAL) based on probability bands
- Prediction endpoint returns `top_risk_factors` with SHAP values and `recommended_action`
- Model artifact version bumped to `lgbm_v2.1` with optimized threshold (0.42)

#### Fixed
- Memory leak in batch SMOTE when processing >100K records
- SHAP TreeExplainer compatibility issue with LightGBM v3.3.5
- Docker container startup race condition between API and model loading

---

## [2.0.0] — 2026-06-15

### 🧠 Major Release: Model Upgrade & Explainability

#### Added
- **Optuna hyperparameter optimization** — 100-trial TPE search replacing manual GridSearchCV
- **SHAP analysis** — global feature importance plots (bar, beeswarm) and local waterfall plots
- **8 balancing technique comparison** — SMOTE, ADASYN, BorderlineSMOTE, SMOTEENN, SMOTETomek, ROS, NearMiss, RUS
- **10-model comparison leaderboard** — LR, RF, XGB, LGB, CatBoost, SVM, KNN, NB, DT, MLP
- **Threshold optimization** — F1-maximizing threshold search over [0.1, 0.9] range
- **Power BI dashboard** — executive KPI cards, churn by partner, time-series trends
- **Tableau dashboard** — cohort analysis, RFM segmentation, churn funnel
- `docs/technical_report.md` — comprehensive ML methodology documentation
- `docs/business_report.md` — executive summary with ROI analysis

#### Changed
- **Winner model upgraded** from Random Forest (v1.x) to LightGBM
  - F1: 0.489 → 0.623 (+27.4% improvement)
  - AUC: 0.812 → 0.871 (+7.3% improvement)
- Balancing method changed from class_weight to SMOTE (better generalization)
- Feature set expanded from 5 original to 16 (5 original + 11 engineered)
- Train/test split changed from 80/20 to stratified 80/20 with cross-validation

#### Fixed
- Data leakage bug in feature engineering (target encoding was using test data)
- Incorrect calculation of `data_usage_ratio` for unlimited plan subscribers
- Missing value imputation now uses training set statistics, not full dataset

#### Breaking Changes
- Model API changed: input schema now requires 16 features (was 5)
- Old model artifacts (`.pkl` v1.x) are incompatible with v2.x predictor

---

## [1.2.0] — 2026-05-01

### Added
- **SQL data warehouse** — `create_tables.sql`, `feature_views.sql`, `churn_analysis_queries.sql`
- **Excel dashboard** — operational tracking with pivot tables and conditional formatting
- **Stored procedures** for batch scoring from SQL (`stored_procedures.sql`)
- PostgreSQL window functions for rolling averages and rank calculations
- Customer segmentation query (RFM-style: Recency, Frequency, Monetary)

#### Changed
- EDA section of notebook expanded with 12 new visualization charts
- Correlation heatmap now uses Cramér's V for categorical-categorical pairs
- Added partner-wise churn rate breakdown (Jio: 15.1%, Airtel: 18.7%, Vodafone: 22.4%, BSNL: 28.3%)

#### Fixed
- Duplicate records discovered and removed (reducing dataset from 251,840 → 243,553 rows)
- Date parsing bug affecting `tenure_months` calculation for customers joining in December

---

## [1.1.0] — 2026-04-05

### Added
- **Feature engineering module** — 11 derived features with business justification
  - `call_failure_rate`, `data_usage_ratio`, `avg_monthly_spend`
  - `payment_delay_count`, `service_call_frequency`, `recharge_consistency`
  - `competitor_network_exposure`, `plan_downgrade_flag`
  - `night_call_ratio`, `international_call_flag`, `loyalty_tier`
- **Class imbalance analysis** — visualization of 20.05% minority class
- Label encoding for telecom partner and state variables
- StandardScaler pipeline for tree-based model compatibility (used in SVM, MLP)

#### Changed
- Notebook restructured into clear sections: Data Loading → EDA → Feature Eng. → Modeling → Evaluation
- Missing value report added (summary table: column, dtype, missing %, strategy)

---

## [1.0.0] — 2026-03-15

### 🎉 Initial Release

#### Added
- Initial project structure with notebook-first approach
- **Dataset**: 243,553 Indian telecom subscribers, 28 raw features
- **Exploratory Data Analysis**:
  - Univariate distributions for all 28 features
  - Bivariate analysis: feature vs. churn label
  - Churn rate analysis by telecom partner, age group, state
  - Correlation heatmap
- **Baseline models**: Logistic Regression and Random Forest (no balancing)
  - LR: F1=0.44, AUC=0.771
  - RF: F1=0.489, AUC=0.812
- `README.md` with project overview
- `requirements.txt` with pinned dependency versions
- `LICENSE` (MIT)
- `.gitignore` for Python data science projects

---

## Version Comparison Summary

| Version | F1-Score | AUC | Key Milestone |
|---------|----------|-----|---------------|
| 1.0.0 | 0.489 | 0.812 | Baseline Random Forest |
| 1.1.0 | 0.531 | 0.829 | Feature Engineering |
| 1.2.0 | 0.547 | 0.838 | SQL Integration |
| 2.0.0 | 0.623 | 0.871 | LightGBM + SMOTE + Optuna |
| 2.1.0 | 0.623 | 0.871 | Production API + Docker |

---

## How to Read This Changelog

- **Added** — new features or files
- **Changed** — changes to existing functionality
- **Deprecated** — features that will be removed in future versions
- **Removed** — features removed in this version
- **Fixed** — bug fixes
- **Security** — security-related fixes
- **Breaking Changes** — changes that break backward compatibility

[Unreleased]: https://github.com/yourusername/telecom-churn-prediction/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/yourusername/telecom-churn-prediction/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/yourusername/telecom-churn-prediction/compare/v1.2.0...v2.0.0
[1.2.0]: https://github.com/yourusername/telecom-churn-prediction/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/yourusername/telecom-churn-prediction/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/yourusername/telecom-churn-prediction/releases/tag/v1.0.0
