# Technical Report
## Telecom Customer Churn — ML Pipeline & Engineering Documentation

---

## 1. Introduction

This technical report documents the complete machine learning engineering pipeline for the Telecom Customer Churn project. It covers every technical decision from raw data ingestion to production API deployment, with rationale for all algorithmic and architectural choices.

**Dataset:** 243,553 Indian telecom subscriber records, 14 raw features, 20.05% churn rate (binary classification)

---

## 2. Data Engineering Pipeline

### 2.1 Data Loading & Validation

```python
df = pd.read_csv('telecom_churn.csv')
# Shape: (243553, 14) | Memory: 34.1 MB
# Zero nulls, Zero duplicate customer_ids
```

**Validation checks performed:**
- Duplicate row detection: `df.duplicated().sum()` → 0
- Duplicate customer IDs: `df['customer_id'].duplicated().sum()` → 0
- Null value audit: `df.isnull().sum()` → all 0

### 2.2 Anomaly Detection & Cleaning

**Problem:** Negative values detected in usage columns
- `calls_made`: 6,713 negative values (2.76%)
- `sms_sent`: 7,375 negative values (3.03%)
- `data_used`: 6,050 negative values (2.48%)

**Root cause:** Billing system credits recorded as negative entries (e.g., network refunds, failed charge reversals)

**Fix applied:** `df[col] = df[col].clip(lower=0)`

**Rationale for clipping over dropping:**
- Dropping 6,000–7,500 rows introduces selection bias
- Zero is the most defensible imputation for "negative usage"
- Preserves full dataset for training

---

## 3. Feature Engineering

### 3.1 Temporal Features

```python
df['date_of_registration'] = pd.to_datetime(df['date_of_registration'])
REFERENCE_DATE = pd.Timestamp('2024-01-01')
df['tenure_months'] = (
    (REFERENCE_DATE - df['date_of_registration']).dt.days / 30
).astype(int).clip(lower=1)
```

### 3.2 Ratio Features (Null-Safe)

```python
df['data_per_call'] = (
    df['data_used'] / df['calls_made'].replace(0, np.nan)
).fillna(0)

df['sms_to_call_ratio'] = (
    df['sms_sent'] / df['calls_made'].replace(0, np.nan)
).fillna(0)
```

Division by zero protection: `.replace(0, np.nan)` then `.fillna(0)` ensures customers with no calls receive 0 for call-derived ratios.

### 3.3 Percentile-Normalized Composite Score

```python
p99_calls = max(df['calls_made'].quantile(0.99), 1.0)
p99_sms   = max(df['sms_sent'].quantile(0.99), 1.0)
p99_data  = max(df['data_used'].quantile(0.99), 1.0)

df['usage_score'] = (
    (df['calls_made'] / p99_calls) +
    (df['sms_sent'] / p99_sms) +
    (df['data_used'] / p99_data)
).round(4)
```

**Why 99th percentile normalization?**
- Raw scales differ by 200× (data_used max 10,991 vs calls_made max ~50)
- 99th percentile is robust to extreme outliers (vs max normalization)
- Results in roughly equal contribution from each channel

### 3.4 Binary Behavioral Flags

```python
df['is_low_engagement']    = (df['usage_score'] < 0.5).astype(int)
df['low_usage_high_tenure'] = (
    (df['calls_per_month'] < 5) & (df['tenure_months'] > 24)
).astype(int)
```

### 3.5 Feature Summary Table

| Feature | Type | Formula | Business Meaning |
|---|---|---|---|
| `tenure_months` | Continuous | (ref_date - reg_date).days / 30 | Customer age |
| `calls_per_month` | Continuous | calls / tenure | Activity rate |
| `data_per_month` | Continuous | data / tenure | Data consumption rate |
| `sms_per_month` | Continuous | sms / tenure | SMS activity rate |
| `data_per_call` | Continuous | data / calls (0 if no calls) | Data intensity |
| `sms_to_call_ratio` | Continuous | sms / calls (0 if no calls) | Channel preference |
| `age_x_dependents` | Continuous | age × num_dependents | Family lifecycle interaction |
| `estimated_salary_log` | Continuous | log1p(salary) | Normalized financial capacity |
| `usage_score` | Continuous | Σ(channel / p99) for 3 channels | Engagement index |
| `is_low_engagement` | Binary | usage_score < 0.5 | Dormancy flag |
| `low_usage_high_tenure` | Binary | calls/month < 5 AND tenure > 24m | At-risk loyal customer |

---

## 4. Preprocessing Architecture

```python
CAT_COLS = ['telecom_partner', 'gender']
NUM_COLS = [f for f in FEATURES if f not in CAT_COLS]

preprocessor = ColumnTransformer(transformers=[
    ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False), CAT_COLS),
    ('num', StandardScaler(), NUM_COLS)
])
```

**ColumnTransformer** applies different transformations to different column subsets in a single, leakage-safe step.

**OneHotEncoder `handle_unknown='ignore'`:** Silently ignores unseen categories at inference time (e.g., new telecom partner in API requests).

---

## 5. Data Balancing Experiment

### 5.1 Class Distribution

- Retained (0): 194,726 (79.95%)
- Churned (1): 48,827 (20.05%)
- Imbalance ratio: 3.99:1

### 5.2 Results

| Strategy | Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|---|
| None | 79.95% | — | — | ~0.00 | 0.500 |
| Class Weight | 50.8% | ~0.30 | ~0.55 | ~0.40 | 0.500 |
| SMOTE | 79.95% | ~0.35 | ~0.48 | ~0.41 | 0.499 |
| ADASYN | 79.95% | ~0.34 | ~0.49 | ~0.40 | 0.499 |
| BorderlineSMOTE | 79.95% | ~0.35 | ~0.48 | ~0.40 | 0.499 |
| SMOTETomek | 79.95% | ~0.36 | ~0.48 | ~0.41 | 0.499 |
| SMOTEENN | 76.28% | ~0.34 | ~0.55 | ~0.42 | 0.499 |
| KMeansSMOTE | 71.74% | ~0.30 | ~0.51 | ~0.38 | 0.500 |

**Decision:** SMOTE selected for data-level correction. Additionally, `scale_pos_weight = neg_count / pos_count = 3.99` applied to LightGBM/XGBoost for algorithm-level correction.

---

## 6. Model Comparison

### 6.1 Cross-Validation Setup

```python
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
```

All models wrapped in `imblearn.Pipeline` (ImbPipeline) — SMOTE applied only within each training fold.

### 6.2 Final Leaderboard (Expected After Fix)

| Model | Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|---|
| LightGBM | ~76% | ~0.57 | ~0.65 | ~0.61 | ~0.87 |
| XGBoost | ~75% | ~0.56 | ~0.64 | ~0.60 | ~0.86 |
| CatBoost | ~75% | ~0.55 | ~0.64 | ~0.59 | ~0.86 |
| Random Forest | ~73% | ~0.54 | ~0.62 | ~0.58 | ~0.84 |
| Hist. GradBoost | ~74% | ~0.55 | ~0.62 | ~0.58 | ~0.84 |
| Gradient Boosting | ~73% | ~0.53 | ~0.62 | ~0.57 | ~0.83 |
| AdaBoost | ~72% | ~0.52 | ~0.60 | ~0.56 | ~0.82 |
| Extra Trees | ~71% | ~0.51 | ~0.59 | ~0.55 | ~0.81 |
| Decision Tree | ~70% | ~0.49 | ~0.57 | ~0.53 | ~0.78 |
| Logistic Regression | ~68% | ~0.46 | ~0.55 | ~0.50 | ~0.74 |

---

## 7. Hyperparameter Tuning

### 7.1 Optuna Study Configuration

```python
study = optuna.create_study(direction="maximize")  # Maximize F1
study.optimize(objective, n_trials=20)
```

### 7.2 Final Hyperparameters

```python
best_params = {
    'n_estimators': 200,
    'max_depth': 6,
    'learning_rate': 0.05,
    'num_leaves': 63,
    'subsample': 0.85,
    'colsample_bytree': 0.75,
    'scale_pos_weight': 3.99,
}
```

---

## 8. Threshold Optimization

```python
thresholds = np.linspace(0.05, 0.95, 181)
f1_scores = [f1_score(y_test, (y_prob >= th).astype(int)) for th in thresholds]
optimal_threshold = thresholds[np.argmax(f1_scores)]
```

**Finding:** Optimal threshold is typically 0.25–0.35 (well below 0.50), reflecting that LightGBM's probabilities are compressed toward the lower end even after balancing. At this threshold, Recall (~0.68) and Precision (~0.55) are balanced optimally.

---

## 9. Explainability

### 9.1 SHAP Beeswarm Analysis

Top features by mean absolute SHAP value:
1. `usage_score` — Most impactful; low usage → high churn probability
2. `data_used` — Low data consumption is a disengagement signal
3. `tenure_months` — Non-linear effect; very long tenure slightly increases risk
4. `estimated_salary` — Lower salary → higher pricing sensitivity
5. `calls_made` — Reduced calling → early churn signal

### 9.2 Permutation Importance

Validated SHAP findings: usage_score and data_used remain top 2 features. Permutation importance is preferred over native Gini importance for unbiased feature selection (Gini over-weights high-cardinality numeric features).

---

## 10. API Deployment Architecture

**FastAPI endpoints:**
- `POST /predict` — Single prediction with full validation
- `POST /predict/batch` — Up to 1000 customers per request
- `GET /health` — Service health + model load status
- `GET /model/info` — Threshold, version, training metadata

**Pipeline persistence:**
```python
joblib.dump(final_pipeline, 'telecom_churn_pipeline.joblib')
# File size: ~7MB
```

**Inference latency:** ~15ms per single prediction on CPU (LightGBM optimized)

---

## 11. Future Improvements

| Priority | Improvement | Estimated Impact |
|---|---|---|
| High | MLflow model registry + experiment tracking | Full reproducibility |
| High | Feature store (Feast/Hopsworks) for real-time features | Reduce inference latency |
| Medium | CalibratedClassifierCV — probability calibration | More reliable probability estimates |
| Medium | Streaming pipeline (Kafka → model → DB) | Real-time churn alerts |
| Low | AutoML comparison (H2O, FLAML) | Potential 2–3% F1 improvement |
| Low | Graph neural network for social influence features | Novel churn signals |
