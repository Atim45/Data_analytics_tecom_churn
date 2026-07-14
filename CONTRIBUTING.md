# Contributing to Telecom Customer Churn Prediction

First off, **thank you** for considering contributing to this project! 🎉

Every contribution — whether it's fixing a typo, adding a feature, improving documentation, or reporting a bug — helps make this project better for everyone learning ML engineering.

---

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [What Can I Contribute?](#what-can-i-contribute)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Pull Request Process](#pull-request-process)
- [Commit Message Format](#commit-message-format)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)
- [Documentation](#documentation)
- [Community](#community)

---

## 📜 Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). By participating, you agree to uphold this code.

In summary:
- **Be respectful** and inclusive in all interactions
- **Provide constructive feedback** on code and ideas
- **Focus on what is best** for the community and the project
- **Assume good intent** from other contributors

---

## 🤝 What Can I Contribute?

We welcome contributions in these areas:

| Area | Examples |
|------|----------|
| 🐛 **Bug Fixes** | Fix data processing errors, API response issues, model loading bugs |
| ✨ **New Features** | Add new ML models, new API endpoints, new dashboard charts |
| 📊 **ML Experiments** | Compare new balancing techniques, add new feature engineering ideas |
| 📖 **Documentation** | Improve README, add docstrings, write tutorials |
| 🧪 **Tests** | Add unit tests, integration tests, API tests |
| 🎨 **UI/UX** | Improve Streamlit dashboard, add new visualizations |
| ⚡ **Performance** | Optimize inference speed, reduce memory usage |
| 🔧 **DevOps** | Improve Dockerfile, CI/CD pipeline, monitoring |

---

## 🚀 Getting Started

### 1. Fork & Clone

```bash
# Fork the repo on GitHub, then:
git clone https://github.com/YOUR_USERNAME/telecom-churn-prediction.git
cd telecom-churn-prediction

# Add upstream remote
git remote add upstream https://github.com/ORIGINAL_OWNER/telecom-churn-prediction.git
```

### 2. Set Up Development Environment

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install development dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Includes: black, flake8, pytest, mypy

# Install pre-commit hooks
pip install pre-commit
pre-commit install
```

### 3. Verify Setup

```bash
# Run tests to make sure everything works
pytest tests/ -v

# Start the API
uvicorn api.main:app --reload

# Access docs at http://localhost:8000/docs
```

---

## 🔄 Development Workflow

We use the **GitHub Flow** branching strategy:

```
main ──────────────────────────────────────── (always deployable)
  │
  ├── feature/add-catboost-model
  ├── fix/smote-memory-leak
  ├── docs/improve-api-documentation
  └── perf/optimize-batch-inference
```

### Step-by-Step

```bash
# 1. Sync with upstream
git fetch upstream
git rebase upstream/main

# 2. Create a feature branch
git checkout -b feature/your-feature-name

# 3. Make your changes (commit often!)
git add .
git commit -m "feat: add CatBoost to model comparison pipeline"

# 4. Push to your fork
git push origin feature/your-feature-name

# 5. Open a Pull Request on GitHub
```

---

## 🎨 Coding Standards

### Python Style

We follow **PEP 8** with these tools:

```bash
# Format code (required before PR)
black . --line-length 100

# Lint
flake8 . --max-line-length 100 --extend-ignore E203,W503

# Type checking
mypy api/ --ignore-missing-imports

# Sort imports
isort . --profile black
```

### Python Best Practices

```python
# ✅ Good: Type hints, docstrings, clear names
def calculate_churn_probability(
    customer_features: pd.DataFrame,
    model: lgb.LGBMClassifier,
    threshold: float = 0.42
) -> tuple[np.ndarray, np.ndarray]:
    """
    Calculate churn probability for one or more customers.
    
    Args:
        customer_features: DataFrame with preprocessed features.
                           Must match training feature schema.
        model: Fitted LightGBM classifier.
        threshold: Classification threshold (default 0.42, business-tuned).
    
    Returns:
        Tuple of (probabilities, binary_predictions).
    
    Raises:
        ValueError: If customer_features has missing required columns.
    """
    required_cols = model.feature_name_
    missing = set(required_cols) - set(customer_features.columns)
    if missing:
        raise ValueError(f"Missing required features: {missing}")
    
    proba = model.predict_proba(customer_features)[:, 1]
    predictions = (proba >= threshold).astype(int)
    return proba, predictions

# ❌ Bad: No types, no docs, magic numbers
def get_pred(df, mdl):
    p = mdl.predict_proba(df)[:, 1]
    return p, (p >= 0.42).astype(int)
```

### SQL Style

```sql
-- ✅ Good: Uppercase keywords, aliases, comments
SELECT
    c.customer_id,
    c.telecom_partner,
    COUNT(cl.call_id)                     AS total_calls,
    SUM(CASE WHEN cl.status = 'FAILED'    -- Count only failed calls
              THEN 1 ELSE 0 END)          AS failed_calls,
    -- Derived metric: failure rate
    ROUND(
        SUM(CASE WHEN cl.status = 'FAILED' THEN 1 ELSE 0 END)::NUMERIC
        / NULLIF(COUNT(cl.call_id), 0),
        4
    )                                     AS call_failure_rate
FROM customers c
JOIN call_logs cl ON c.customer_id = cl.customer_id
WHERE cl.call_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY c.customer_id, c.telecom_partner;
```

---

## 🧪 Testing Guidelines

### Test Structure

```
tests/
├── unit/
│   ├── test_feature_engineering.py
│   ├── test_model_predictor.py
│   └── test_data_validation.py
├── integration/
│   ├── test_api_endpoints.py
│   └── test_database_queries.py
└── conftest.py
```

### Writing Tests

```python
# tests/unit/test_feature_engineering.py
import pytest
import pandas as pd
from src.features import calculate_call_failure_rate

class TestCallFailureRate:
    """Tests for call failure rate feature engineering."""
    
    def test_normal_case(self):
        """Basic functionality: 2 failures in 10 calls."""
        df = pd.DataFrame({
            'total_calls': [10, 20],
            'failed_calls': [2, 4]
        })
        result = calculate_call_failure_rate(df)
        assert result.tolist() == [0.2, 0.2], "Failure rate should be 0.2"
    
    def test_zero_calls(self):
        """Edge case: customer with no calls should return 0.0, not NaN."""
        df = pd.DataFrame({'total_calls': [0], 'failed_calls': [0]})
        result = calculate_call_failure_rate(df)
        assert result.iloc[0] == 0.0
        assert not result.isna().any(), "Should not produce NaN values"
    
    def test_all_failed(self):
        """Edge case: 100% failure rate."""
        df = pd.DataFrame({'total_calls': [5], 'failed_calls': [5]})
        result = calculate_call_failure_rate(df)
        assert result.iloc[0] == 1.0

    @pytest.mark.parametrize("total,failed,expected", [
        (100, 0, 0.0),
        (100, 50, 0.5),
        (100, 100, 1.0),
    ])
    def test_parametrized(self, total, failed, expected):
        df = pd.DataFrame({'total_calls': [total], 'failed_calls': [failed]})
        assert calculate_call_failure_rate(df).iloc[0] == expected
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run only fast unit tests
pytest tests/unit/ -v -m "not slow"

# Run API tests (requires running server)
pytest tests/integration/test_api_endpoints.py -v
```

### Coverage Requirements

- **Minimum 70% coverage** for new code
- **All new API endpoints** must have integration tests
- **All feature engineering functions** must have unit tests

---

## 📥 Pull Request Process

### Before Submitting

- [ ] Tests pass: `pytest tests/ -v`
- [ ] Code formatted: `black . --line-length 100`
- [ ] Linting passes: `flake8 . --max-line-length 100`
- [ ] No large data files committed (check `.gitignore`)
- [ ] Documentation updated if adding new features
- [ ] CHANGELOG.md updated with your changes

### PR Title Format

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

```
feat: add CatBoost to model comparison pipeline
fix: resolve SMOTE memory issue with large datasets
docs: add deployment guide for AWS ECS
perf: optimize batch prediction endpoint (50% speed improvement)
test: add unit tests for feature engineering module
chore: update LightGBM to v4.0
refactor: extract predictor logic into separate module
```

### PR Description Template

```markdown
## What does this PR do?
Brief description of the change and its motivation.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update
- [ ] Performance improvement

## How was this tested?
Describe the tests you ran.

## Screenshots (if applicable)
Add screenshots for UI changes.

## Checklist
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
```

### Review Process

1. **Automated checks** must pass (tests, linting)
2. **At least 1 reviewer** approval required
3. **Reviewer may request changes** — please respond within 5 business days
4. **Maintainer merges** after approval (squash merge preferred)

---

## 📝 Commit Message Format

```
<type>(<scope>): <short description>

[optional body]

[optional footer]
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`

**Scopes:** `model`, `api`, `dashboard`, `sql`, `data`, `docker`, `docs`

**Examples:**
```
feat(model): add ADASYN as balancing option alongside SMOTE
fix(api): handle missing customer_id in /predict endpoint
docs(readme): add architecture mermaid diagram
perf(model): cache model artifact in memory (3x faster inference)
test(api): add integration tests for batch prediction endpoint
```

---

## 🐛 Reporting Bugs

Please use the [Bug Report template](https://github.com/yourusername/telecom-churn-prediction/issues/new?template=bug_report.md).

Include:
1. **Environment** (OS, Python version, library versions)
2. **Steps to reproduce** (minimal reproducible example)
3. **Expected behavior**
4. **Actual behavior** (error message, stack trace)
5. **Screenshots** if applicable

---

## 💡 Suggesting Features

Please use the [Feature Request template](https://github.com/yourusername/telecom-churn-prediction/issues/new?template=feature_request.md).

Include:
1. **Problem** — what gap does this fill?
2. **Proposed solution** — how should it work?
3. **Alternatives considered** — why is your approach better?
4. **Additional context** — links, papers, examples

---

## 📖 Documentation

Documentation improvements are always welcome!

- **Code docstrings** — follow NumPy docstring format
- **README updates** — keep accurate and current
- **docs/ files** — improve any markdown in the docs folder
- **Inline comments** — explain *why*, not *what*

---

## 🌐 Community

- **Discussions**: Use [GitHub Discussions](https://github.com/yourusername/telecom-churn-prediction/discussions) for questions
- **Issues**: Use [GitHub Issues](https://github.com/yourusername/telecom-churn-prediction/issues) for bugs and features
- **Twitter/X**: Follow [@yourusername](https://twitter.com/yourusername) for updates

---

*Thank you for making this project better! Every contribution counts.* 🙏
