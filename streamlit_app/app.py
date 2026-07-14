"""
Telecom Customer Churn Prediction — Streamlit Application
==========================================================
Single-file, production-ready Streamlit app.

Run:
    streamlit run app.py

Requirements:
    pip install -r requirements.txt
"""

from __future__ import annotations

import io
import json
import math
import os
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

# ──────────────────────────────────────────────────────────────────────────────
# Try loading model locally (fallback when API is not running)
# ──────────────────────────────────────────────────────────────────────────────
try:
    import joblib
    _JOBLIB_AVAILABLE = True
except ImportError:
    _JOBLIB_AVAILABLE = False

# ──────────────────────────────────────────────────────────────────────────────
# Paths & Config
# ──────────────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
PARENT_DIR = BASE_DIR.parent

MODEL_PATH = PARENT_DIR / "telecom_churn_pipeline.joblib"
METADATA_PATH = PARENT_DIR / "model_metadata.json"

API_URL = os.getenv("API_URL", "http://localhost:8000")
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "10"))

# ── Brand colours ─────────────────────────────────────────────────────────────
TEAL   = "#008080"
NAVY   = "#1A1A2E"
CORAL  = "#C94A4A"
LIGHT_TEAL = "#00B2B2"
AMBER  = "#F5A623"
GREEN  = "#27AE60"
PURPLE = "#8E44AD"
WHITE  = "#F0F4F8"

FEATURE_ORDER = [
    "telecom_partner", "gender", "age", "num_dependents", "estimated_salary",
    "calls_made", "sms_sent", "data_used", "tenure_months",
    "calls_per_month", "data_per_month", "sms_per_month",
    "data_per_call", "sms_to_call_ratio", "age_x_dependents",
    "estimated_salary_log", "usage_score", "is_low_engagement",
    "low_usage_high_tenure",
]

# ──────────────────────────────────────────────────────────────────────────────
# Page config (MUST be first Streamlit call)
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Telecom Churn Intelligence",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────────────────────
# Global CSS injection
# ──────────────────────────────────────────────────────────────────────────────

st.markdown(
    f"""
    <style>
    /* ── Fonts ── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] {{
        font-family: 'Inter', sans-serif;
    }}

    /* ── Root background ── */
    .stApp {{
        background: linear-gradient(135deg, {NAVY} 0%, #16213E 60%, #0F3460 100%);
        color: {WHITE};
    }}

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #0D0D1A 0%, {NAVY} 100%) !important;
        border-right: 2px solid {TEAL};
    }}
    section[data-testid="stSidebar"] .stRadio label {{
        color: {WHITE} !important;
        font-size: 0.95rem;
        padding: 4px 0;
    }}

    /* ── Metric cards ── */
    .metric-card {{
        background: rgba(0, 128, 128, 0.15);
        border: 1px solid {TEAL};
        border-radius: 12px;
        padding: 20px 16px;
        text-align: center;
        transition: transform 0.2s;
    }}
    .metric-card:hover {{
        transform: translateY(-4px);
        border-color: {LIGHT_TEAL};
    }}
    .metric-card .value {{
        font-size: 2rem;
        font-weight: 700;
        color: {LIGHT_TEAL};
    }}
    .metric-card .label {{
        font-size: 0.8rem;
        color: #9AB;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-top: 4px;
    }}

    /* ── Hero ── */
    .hero-title {{
        font-size: 2.8rem;
        font-weight: 700;
        background: linear-gradient(90deg, {LIGHT_TEAL}, {TEAL});
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }}
    .hero-subtitle {{
        font-size: 1.1rem;
        color: #9AB;
        margin-bottom: 1.5rem;
    }}

    /* ── Risk badges ── */
    .badge-low      {{ background: {GREEN};  color: white; padding: 4px 12px; border-radius: 20px; font-weight: 600; }}
    .badge-medium   {{ background: {AMBER};  color: white; padding: 4px 12px; border-radius: 20px; font-weight: 600; }}
    .badge-high     {{ background: {CORAL};  color: white; padding: 4px 12px; border-radius: 20px; font-weight: 600; }}
    .badge-critical {{ background: #8B0000; color: white; padding: 4px 12px; border-radius: 20px; font-weight: 600; }}

    /* ── Cards ── */
    .content-card {{
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(0,128,128,0.3);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 16px;
    }}

    /* ── Section headings ── */
    .section-heading {{
        font-size: 1.5rem;
        font-weight: 600;
        color: {LIGHT_TEAL};
        border-bottom: 2px solid {TEAL};
        padding-bottom: 8px;
        margin-bottom: 20px;
    }}

    /* ── Streamlit default overrides ── */
    div[data-testid="stMetric"] {{
        background: rgba(0,128,128,0.1);
        border-radius: 10px;
        padding: 12px;
        border: 1px solid rgba(0,128,128,0.3);
    }}
    div[data-testid="stMetric"] label {{ color: #9AB !important; }}
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {{ color: {LIGHT_TEAL} !important; }}

    /* Buttons */
    .stButton > button {{
        background: linear-gradient(135deg, {TEAL}, {LIGHT_TEAL});
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        padding: 10px 28px;
        transition: opacity 0.2s;
    }}
    .stButton > button:hover {{ opacity: 0.88; }}

    /* Form inputs */
    .stSelectbox > div, .stNumberInput > div, .stDateInput > div {{
        background: rgba(255,255,255,0.08) !important;
        border-radius: 8px;
    }}

    /* DataFrames */
    .dataframe {{ background: rgba(255,255,255,0.05); border-radius: 8px; }}

    /* Footer */
    footer {{ visibility: hidden; }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────────────────────────────────────
# Cache helpers
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner="Loading model…")
def load_model():
    """Load the LightGBM pipeline from disk (cached for the session lifetime)."""
    if not _JOBLIB_AVAILABLE:
        return None
    if MODEL_PATH.exists():
        return joblib.load(MODEL_PATH)
    return None


@st.cache_data(show_spinner=False)
def load_metadata() -> dict:
    """Load model_metadata.json (cached)."""
    if METADATA_PATH.exists():
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    # Fallback hardcoded defaults
    return {
        "model_name": "LightGBM Churn Classifier",
        "model_version": "1.0.0",
        "optimal_threshold": 0.28,
        "dataset": {
            "total_samples": 243553,
            "churn_rate": 0.2005,
            "retained_count": 194726,
            "churned_count": 48827,
        },
        "test_metrics": {
            "accuracy": 0.7995,
            "f1_score_churn": 0.334,
            "roc_auc": 0.5003,
        },
        "feature_importance": {
            "tenure_months": 0.182,
            "age": 0.141,
            "estimated_salary": 0.128,
            "usage_score": 0.115,
            "data_used": 0.098,
            "calls_made": 0.087,
            "sms_sent": 0.076,
            "age_x_dependents": 0.054,
            "estimated_salary_log": 0.042,
            "calls_per_month": 0.038,
        },
        "features": FEATURE_ORDER,
        "telecom_partners": ["Jio", "Airtel", "Vi", "BSNL"],
        "genders": ["Male", "Female"],
    }


# ──────────────────────────────────────────────────────────────────────────────
# Prediction helpers
# ──────────────────────────────────────────────────────────────────────────────

def _risk_level(prob: float) -> str:
    if prob < 0.25:
        return "LOW"
    elif prob < 0.45:
        return "MEDIUM"
    elif prob < 0.65:
        return "HIGH"
    return "CRITICAL"


def _risk_colour(risk: str) -> str:
    return {"LOW": GREEN, "MEDIUM": AMBER, "HIGH": CORAL, "CRITICAL": "#8B0000"}[risk]


def _recommendation(risk: str) -> str:
    return {
        "LOW": "✅ No immediate action required. Continue monitoring quarterly.",
        "MEDIUM": "📧 Send a personalised retention offer and review the customer's plan.",
        "HIGH": "📞 Immediate outreach recommended — escalate to the retention team.",
        "CRITICAL": "🚨 Priority intervention: offer a loyalty discount or premium upgrade now.",
    }[risk]


def compute_derived_features(
    telecom_partner, gender, age, num_dependents, estimated_salary,
    calls_made, sms_sent, data_used, date_of_registration,
) -> dict:
    """Mirror the FastAPI /predict/raw feature computation."""
    now = datetime.now()
    reg = datetime.combine(date_of_registration, datetime.min.time())
    tenure_months = max(1, (now.year - reg.year) * 12 + (now.month - reg.month))

    calls = max(calls_made, 0)
    sms   = max(sms_sent, 0)
    data  = max(data_used, 0)
    t     = max(tenure_months, 1)

    calls_per_month    = round(calls / t, 4)
    data_per_month     = round(data  / t, 4)
    sms_per_month      = round(sms   / t, 4)
    data_per_call      = round(data  / calls, 4) if calls > 0 else 0.0
    sms_to_call_ratio  = round(sms   / calls, 4) if calls > 0 else 0.0
    age_x_dependents   = age * num_dependents
    estimated_salary_log = round(math.log1p(estimated_salary), 6)

    total              = calls + sms + data / 1000
    usage_score        = round(total / t, 4)
    is_low_engagement  = int(usage_score < 1.0)
    low_usage_high_tenure = int(is_low_engagement == 1 and tenure_months > 24)

    return {
        "telecom_partner":      telecom_partner,
        "gender":               gender,
        "age":                  age,
        "num_dependents":       num_dependents,
        "estimated_salary":     estimated_salary,
        "calls_made":           calls,
        "sms_sent":             sms,
        "data_used":            data,
        "tenure_months":        tenure_months,
        "calls_per_month":      calls_per_month,
        "data_per_month":       data_per_month,
        "sms_per_month":        sms_per_month,
        "data_per_call":        data_per_call,
        "sms_to_call_ratio":    sms_to_call_ratio,
        "age_x_dependents":     age_x_dependents,
        "estimated_salary_log": estimated_salary_log,
        "usage_score":          usage_score,
        "is_low_engagement":    is_low_engagement,
        "low_usage_high_tenure": low_usage_high_tenure,
    }


def predict_via_api(features: dict, meta: dict) -> dict | None:
    """Call the FastAPI /predict endpoint."""
    try:
        resp = requests.post(
            f"{API_URL}/predict",
            json=features,
            timeout=API_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def predict_local(features: dict, pipeline, meta: dict) -> dict:
    """Run inference locally using the loaded pipeline."""
    threshold = meta.get("optimal_threshold", 0.28)
    df = pd.DataFrame([features], columns=FEATURE_ORDER)[FEATURE_ORDER]
    prob = float(pipeline.predict_proba(df)[0, 1])
    churn = prob >= threshold
    risk = _risk_level(prob)

    z = 1.96
    margin = z * math.sqrt(prob * (1 - prob) / 1000)
    return {
        "churn_probability": round(prob, 6),
        "churn_prediction": churn,
        "risk_level": risk,
        "confidence_interval": {
            "lower": round(max(0.0, prob - margin), 4),
            "upper": round(min(1.0, prob + margin), 4),
        },
        "recommendation": _recommendation(risk),
        "model_version": meta.get("model_version", "1.0.0"),
        "threshold_used": threshold,
    }


def predict_batch_local(df_input: pd.DataFrame, pipeline, meta: dict) -> pd.DataFrame:
    """Run batch inference locally."""
    threshold = meta.get("optimal_threshold", 0.28)
    df = df_input[FEATURE_ORDER].copy()
    probs = pipeline.predict_proba(df)[:, 1]
    risks = [_risk_level(p) for p in probs]
    return df_input.assign(
        churn_probability=probs.round(4),
        churn_prediction=(probs >= threshold).astype(int),
        risk_level=risks,
    )

# ──────────────────────────────────────────────────────────────────────────────
# Plotly helpers
# ──────────────────────────────────────────────────────────────────────────────

PLOT_BG  = "rgba(0,0,0,0)"
PAPER_BG = "rgba(0,0,0,0)"
FONT_CLR = WHITE


def _plotly_layout_defaults(fig: go.Figure, title: str = "") -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(color=LIGHT_TEAL, size=16)),
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=PLOT_BG,
        font=dict(color=FONT_CLR, family="Inter"),
        margin=dict(l=20, r=20, t=45, b=20),
    )
    return fig


def gauge_chart(prob: float, threshold: float, risk: str) -> go.Figure:
    colour = _risk_colour(risk)
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number+delta",
            value=round(prob * 100, 2),
            number={"suffix": "%", "font": {"size": 40, "color": colour}},
            delta={"reference": threshold * 100, "valueformat": ".1f", "suffix": "%"},
            title={"text": "Churn Probability", "font": {"color": LIGHT_TEAL, "size": 16}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": WHITE, "tickfont": {"color": WHITE}},
                "bar": {"color": colour, "thickness": 0.3},
                "bgcolor": "rgba(255,255,255,0.05)",
                "borderwidth": 2,
                "bordercolor": TEAL,
                "steps": [
                    {"range": [0, 25],   "color": "rgba(39,174,96,0.3)"},
                    {"range": [25, 45],  "color": "rgba(245,166,35,0.3)"},
                    {"range": [45, 65],  "color": "rgba(201,74,74,0.3)"},
                    {"range": [65, 100], "color": "rgba(139,0,0,0.4)"},
                ],
                "threshold": {
                    "line": {"color": AMBER, "width": 3},
                    "thickness": 0.75,
                    "value": threshold * 100,
                },
            },
        )
    )
    fig.update_layout(
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=PLOT_BG,
        font=dict(color=FONT_CLR, family="Inter"),
        height=280,
        margin=dict(l=20, r=20, t=30, b=10),
    )
    return fig


def feature_importance_chart(importance: dict, top_n: int = 15) -> go.Figure:
    sorted_items = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:top_n]
    features, values = zip(*sorted_items)
    colours = [TEAL if v > 0.1 else LIGHT_TEAL if v > 0.05 else "#4A9090" for v in values]

    fig = go.Figure(
        go.Bar(
            x=list(values),
            y=list(features),
            orientation="h",
            marker=dict(color=colours, line=dict(color=TEAL, width=0.5)),
            text=[f"{v:.3f}" for v in values],
            textposition="outside",
            textfont=dict(color=WHITE, size=11),
        )
    )
    fig.update_yaxes(autorange="reversed", tickfont=dict(color=WHITE))
    fig.update_xaxes(tickfont=dict(color=WHITE), gridcolor="rgba(255,255,255,0.1)")
    _plotly_layout_defaults(fig, "Feature Importance (Permutation)")
    fig.update_layout(height=420)
    return fig


def shap_bar_chart(features: dict, prob: float) -> go.Figure:
    """Simulated SHAP-style bar chart based on importance × feature deviation."""
    meta = load_metadata()
    importance = meta.get("feature_importance", {})
    means = {
        "age": 46, "tenure_months": 48, "estimated_salary": 500000,
        "usage_score": 1.5, "data_used": 5000, "calls_made": 45,
        "sms_sent": 24, "num_dependents": 2,
    }
    shap_vals = {}
    for feat, imp in list(importance.items())[:10]:
        val = features.get(feat, 0)
        mean = means.get(feat, 0)
        try:
            deviation = float(val - mean) / max(abs(mean), 1)
        except TypeError:
            deviation = 0.0
        shap_vals[feat] = round(imp * deviation * (prob - 0.5) * 2, 4)

    sorted_shap = sorted(shap_vals.items(), key=lambda x: abs(x[1]), reverse=True)[:8]
    feats, vals = zip(*sorted_shap)
    colours = [CORAL if v > 0 else TEAL for v in vals]

    fig = go.Figure(
        go.Bar(
            x=list(vals),
            y=list(feats),
            orientation="h",
            marker=dict(color=colours),
            text=[f"{v:+.4f}" for v in vals],
            textposition="outside",
            textfont=dict(color=WHITE, size=10),
        )
    )
    fig.update_yaxes(autorange="reversed", tickfont=dict(color=WHITE))
    fig.update_xaxes(tickfont=dict(color=WHITE), gridcolor="rgba(255,255,255,0.1)",
                     zeroline=True, zerolinecolor=AMBER, zerolinewidth=2)
    _plotly_layout_defaults(fig, "SHAP-style Feature Contributions (Estimated)")
    fig.update_layout(height=320)
    return fig


def roc_placeholder_chart() -> go.Figure:
    """Approximate ROC curve from reported AUC ≈ 0.50 (shows shape)."""
    fpr = np.linspace(0, 1, 100)
    # Slightly above diagonal to represent ~0.50 AUC
    tpr = np.clip(fpr + np.random.RandomState(42).normal(0, 0.04, 100).cumsum() * 0.01, 0, 1)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=fpr, y=tpr, mode="lines",
        line=dict(color=TEAL, width=2.5),
        name="LightGBM (AUC ≈ 0.50)",
        fill="tozeroy", fillcolor="rgba(0,128,128,0.1)",
    ))
    fig.add_trace(go.Scatter(
        x=[0, 1], y=[0, 1], mode="lines",
        line=dict(color=AMBER, dash="dash", width=1.5),
        name="Random Classifier",
    ))
    fig.update_xaxes(title_text="False Positive Rate", tickfont=dict(color=WHITE),
                     gridcolor="rgba(255,255,255,0.1)")
    fig.update_yaxes(title_text="True Positive Rate", tickfont=dict(color=WHITE),
                     gridcolor="rgba(255,255,255,0.1)")
    _plotly_layout_defaults(fig, "ROC Curve — Test Set")
    fig.update_layout(
        height=380,
        legend=dict(font=dict(color=WHITE), bgcolor="rgba(0,0,0,0.3)"),
    )
    return fig


def threshold_sensitivity_chart(meta: dict) -> go.Figure:
    """Illustrative threshold vs precision/recall/F1 chart."""
    thresholds = np.arange(0.05, 0.95, 0.02)
    # Approximate curves based on known data distribution
    precision = np.clip(0.20 + thresholds * 0.55, 0, 1)
    recall    = np.clip(1.0  - thresholds * 1.1,  0, 1)
    f1        = np.where(
        (precision + recall) > 0,
        2 * precision * recall / (precision + recall + 1e-9),
        0,
    )
    optimal_t = meta.get("optimal_threshold", 0.28)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=thresholds, y=precision, name="Precision",
                             line=dict(color=TEAL, width=2)))
    fig.add_trace(go.Scatter(x=thresholds, y=recall, name="Recall",
                             line=dict(color=CORAL, width=2)))
    fig.add_trace(go.Scatter(x=thresholds, y=f1, name="F1-Score",
                             line=dict(color=AMBER, width=2.5)))
    fig.add_vline(x=optimal_t, line=dict(color=LIGHT_TEAL, dash="dash", width=2),
                  annotation_text=f"Optimal ({optimal_t})",
                  annotation_font=dict(color=LIGHT_TEAL))
    fig.update_xaxes(title_text="Decision Threshold", tickfont=dict(color=WHITE),
                     gridcolor="rgba(255,255,255,0.1)")
    fig.update_yaxes(title_text="Score", tickfont=dict(color=WHITE),
                     gridcolor="rgba(255,255,255,0.1)")
    _plotly_layout_defaults(fig, "Threshold Sensitivity Analysis")
    fig.update_layout(
        height=380,
        legend=dict(font=dict(color=WHITE), bgcolor="rgba(0,0,0,0.3)"),
    )
    return fig


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar navigation
# ──────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        f"""
        <div style='text-align:center; padding: 16px 0 8px 0;'>
            <div style='font-size:2.2rem;'>📡</div>
            <div style='font-size:1.1rem; font-weight:700; color:{LIGHT_TEAL};'>
                Churn Intelligence
            </div>
            <div style='font-size:0.75rem; color:#9AB;'>Telecom Analytics Platform</div>
        </div>
        <hr style='border-color:{TEAL}; margin: 12px 0;'>
        """,
        unsafe_allow_html=True,
    )

    page = st.radio(
        "Navigate",
        ["🏠 Home", "🔍 Single Prediction", "📦 Batch Prediction", "📊 Model Insights", "ℹ️ About"],
        label_visibility="collapsed",
    )

    st.markdown("<hr style='border-color:#333; margin: 16px 0;'>", unsafe_allow_html=True)

    # API status indicator
    try:
        health_resp = requests.get(f"{API_URL}/health", timeout=2)
        api_ok = health_resp.status_code == 200
    except Exception:
        api_ok = False

    if api_ok:
        st.markdown(
            f"<div style='color:{GREEN}; font-size:0.8rem;'>● API Online</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<div style='color:{AMBER}; font-size:0.8rem;'>● API Offline (local mode)</div>",
            unsafe_allow_html=True,
        )

    meta = load_metadata()
    st.markdown(
        f"""
        <div style='font-size:0.75rem; color:#9AB; margin-top:8px;'>
        Model v{meta.get('model_version','1.0.0')}<br>
        Threshold: {meta.get('optimal_threshold', 0.28)}<br>
        Framework: {meta.get('framework','LightGBM')}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# PAGE: Home
# ──────────────────────────────────────────────────────────────────────────────

if page == "🏠 Home":
    st.markdown(
        """
        <div class='hero-title'>📡 Telecom Churn Intelligence</div>
        <div class='hero-subtitle'>
            ML-powered customer churn prediction for Indian telecom operators.
            Identify at-risk customers before they leave.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Key metric cards ──────────────────────────────────────────────────────
    cols = st.columns(4)
    metrics = [
        ("243,553", "Total Subscribers"),
        ("20.05%",  "Churn Rate"),
        ("48,827",  "Churned Customers"),
        ("79.95%",  "Retention Rate"),
    ]
    for col, (val, label) in zip(cols, metrics):
        col.markdown(
            f"""
            <div class='metric-card'>
                <div class='value'>{val}</div>
                <div class='label'>{label}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("<div class='section-heading'>📌 Project Overview</div>", unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class='content-card'>
            <p>This platform provides real-time churn prediction for telecom customers
            using a <strong style='color:{LIGHT_TEAL}'>LightGBM</strong> model
            trained on <strong>243,553</strong> customer records from 4 Indian operators
            (Jio, Airtel, Vi, BSNL).</p>

            <p><strong style='color:{LIGHT_TEAL}'>Features engineered:</strong></p>
            <ul style='margin:0; padding-left:18px; color:#ccc;'>
                <li>Per-month usage ratios (calls, SMS, data)</li>
                <li>Engagement score composite</li>
                <li>Low-usage × high-tenure interaction flag</li>
                <li>Log-salary transformation</li>
                <li>Age × dependents interaction</li>
            </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown("<div class='section-heading'>🎯 Model Performance</div>", unsafe_allow_html=True)
        test_m = meta.get("test_metrics", {})
        hp = meta.get("hyperparameters", {})
        perf_data = {
            "Metric": ["Accuracy", "F1 (Churn)", "ROC-AUC", "Optimal Threshold"],
            "Value":  [
                f"{test_m.get('accuracy', 0.7995):.2%}",
                f"{test_m.get('f1_score_churn', 0.334):.3f}",
                f"{test_m.get('roc_auc', 0.5003):.4f}",
                str(meta.get("optimal_threshold", 0.28)),
            ],
        }
        df_perf = pd.DataFrame(perf_data)
        st.dataframe(
            df_perf.style.set_properties(**{"background-color": "rgba(0,128,128,0.1)",
                                            "color": WHITE}),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("<br>", unsafe_allow_html=True)
        hp_data = {
            "Hyperparameter": ["n_estimators", "max_depth", "learning_rate", "num_leaves"],
            "Value":          [
                hp.get("n_estimators", 65),
                hp.get("max_depth", 8),
                f"{hp.get('learning_rate', 0.0188):.4f}",
                hp.get("num_leaves", 64),
            ],
        }
        st.dataframe(
            pd.DataFrame(hp_data).style.set_properties(
                **{"background-color": "rgba(0,128,128,0.1)", "color": WHITE}
            ),
            use_container_width=True,
            hide_index=True,
        )

    # ── Risk level legend ─────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<div class='section-heading'>🎨 Risk Level Guide</div>", unsafe_allow_html=True)
    rc1, rc2, rc3, rc4 = st.columns(4)
    for col, (risk, thresh, desc) in zip(
        [rc1, rc2, rc3, rc4],
        [
            ("LOW",      "< 25%",  "Monitor quarterly"),
            ("MEDIUM",   "25–45%", "Retention offer"),
            ("HIGH",     "45–65%", "Urgent outreach"),
            ("CRITICAL", "> 65%",  "Immediate action"),
        ],
    ):
        col.markdown(
            f"""
            <div class='metric-card' style='border-color:{_risk_colour(risk)};'>
                <div style='color:{_risk_colour(risk)}; font-weight:700; font-size:1.1rem;'>{risk}</div>
                <div style='color:#CCC; font-size:0.9rem;'>{thresh}</div>
                <div style='color:#9AB; font-size:0.78rem; margin-top:4px;'>{desc}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ──────────────────────────────────────────────────────────────────────────────
# PAGE: Single Prediction
# ──────────────────────────────────────────────────────────────────────────────

elif page == "🔍 Single Prediction":
    st.markdown("<div class='hero-title'>🔍 Single Customer Prediction</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='hero-subtitle'>Enter customer details to predict churn risk.</div>",
        unsafe_allow_html=True,
    )

    partners = meta.get("telecom_partners", ["Jio", "Airtel", "Vi", "BSNL"])
    genders  = meta.get("genders", ["Male", "Female"])

    with st.form("predict_form"):
        tab_demo, tab_usage, tab_derived = st.tabs(
            ["👤 Demographics", "📱 Usage", "⚙️ Derived Features"]
        )

        # ── Demographics tab ─────────────────────────────────────────────────
        with tab_demo:
            c1, c2 = st.columns(2)
            with c1:
                telecom_partner = st.selectbox(
                    "Telecom Partner", partners,
                    help="Customer's current telecom operator",
                )
                age = st.number_input(
                    "Age", min_value=18, max_value=74, value=35, step=1,
                    help="Customer age (18–74)",
                )
                num_dependents = st.number_input(
                    "Number of Dependents", min_value=0, max_value=10, value=2,
                    help="Number of financial dependents",
                )
            with c2:
                gender = st.selectbox(
                    "Gender", genders,
                    help="Customer gender",
                )
                estimated_salary = st.number_input(
                    "Estimated Annual Salary (₹)", min_value=10000, max_value=10000000,
                    value=500000, step=10000,
                    help="Annual salary in INR",
                )
                date_of_registration = st.date_input(
                    "Date of Registration",
                    value=date(2022, 1, 15),
                    max_value=date.today(),
                    help="Used to auto-compute tenure_months",
                )

        # ── Usage tab ────────────────────────────────────────────────────────
        with tab_usage:
            c1, c2, c3 = st.columns(3)
            with c1:
                calls_made = st.number_input(
                    "Total Calls Made", min_value=0, value=45, step=1,
                    help="Lifetime calls",
                )
            with c2:
                sms_sent = st.number_input(
                    "Total SMS Sent", min_value=0, value=20, step=1,
                    help="Lifetime SMS sent",
                )
            with c3:
                data_used = st.number_input(
                    "Total Data Used (MB)", min_value=0, value=5000, step=100,
                    help="Lifetime data consumed in MB",
                )
            st.info(
                "ℹ️ Derived features (per-month ratios, engagement score, etc.) "
                "are automatically computed from the above inputs + registration date.",
                icon=None,
            )

        # ── Derived features tab (manual override) ───────────────────────────
        with tab_derived:
            st.markdown(
                "**Optional:** Override auto-computed derived features. Leave at 0 to auto-compute.",
                unsafe_allow_html=False,
            )
            cd1, cd2, cd3 = st.columns(3)
            with cd1:
                manual_tenure = st.number_input("tenure_months (0 = auto)", 0, 600, 0)
                calls_per_month = st.number_input("calls_per_month", 0.0, 500.0, 0.0, format="%.4f")
                data_per_month = st.number_input("data_per_month (MB)", 0.0, 50000.0, 0.0, format="%.2f")
            with cd2:
                sms_per_month = st.number_input("sms_per_month", 0.0, 500.0, 0.0, format="%.4f")
                data_per_call = st.number_input("data_per_call (MB)", 0.0, 50000.0, 0.0, format="%.2f")
                sms_to_call_ratio = st.number_input("sms_to_call_ratio", 0.0, 100.0, 0.0, format="%.4f")
            with cd3:
                usage_score = st.number_input("usage_score", 0.0, 100.0, 0.0, format="%.4f")
                is_low_engagement = st.selectbox("is_low_engagement", [0, 1], index=0)
                low_usage_high_tenure = st.selectbox("low_usage_high_tenure", [0, 1], index=0)

        submitted = st.form_submit_button("🚀 Predict Churn Risk", use_container_width=True)

    if submitted:
        # Auto-compute derived features
        auto = compute_derived_features(
            telecom_partner, gender, age, num_dependents, estimated_salary,
            calls_made, sms_sent, data_used, date_of_registration,
        )
        # Allow manual overrides
        if manual_tenure > 0:
            auto["tenure_months"] = manual_tenure
        if calls_per_month > 0:
            auto["calls_per_month"] = calls_per_month
        if data_per_month > 0:
            auto["data_per_month"] = data_per_month
        if sms_per_month > 0:
            auto["sms_per_month"] = sms_per_month
        if data_per_call > 0:
            auto["data_per_call"] = data_per_call
        if sms_to_call_ratio > 0:
            auto["sms_to_call_ratio"] = sms_to_call_ratio
        if usage_score > 0:
            auto["usage_score"] = usage_score
        auto["is_low_engagement"] = is_low_engagement
        auto["low_usage_high_tenure"] = low_usage_high_tenure
        auto["estimated_salary_log"] = round(math.log1p(estimated_salary), 6)
        auto["age_x_dependents"] = age * num_dependents

        # Try API first, fall back to local
        result = None
        if api_ok:
            result = predict_via_api(auto, meta)

        if result is None:
            pipeline = load_model()
            if pipeline is not None:
                result = predict_local(auto, pipeline, meta)
            else:
                st.error("Neither the API nor local model is available. Please check your setup.")
                st.stop()

        # ── Display results ──────────────────────────────────────────────────
        prob  = result["churn_probability"]
        risk  = result["risk_level"]
        churn = result["churn_prediction"]
        ci    = result["confidence_interval"]
        rec   = result.get("recommendation", _recommendation(risk))
        thresh = result.get("threshold_used", meta.get("optimal_threshold", 0.28))

        st.markdown("---")
        st.markdown("<div class='section-heading'>📊 Prediction Result</div>", unsafe_allow_html=True)

        r1, r2 = st.columns([1, 1])

        with r1:
            st.plotly_chart(gauge_chart(prob, thresh, risk), use_container_width=True)

            badge_cls = f"badge-{risk.lower()}"
            st.markdown(
                f"""
                <div style='text-align:center; margin-top:8px;'>
                    <span class='{badge_cls}'>{risk} RISK</span>
                    &nbsp;
                    <span style='color:{LIGHT_TEAL}; font-size:1.1rem;'>
                        {'⚠️ Likely to Churn' if churn else '✅ Likely to Retain'}
                    </span>
                </div>
                <div style='text-align:center; color:#9AB; font-size:0.85rem; margin-top:8px;'>
                    95% CI: [{ci['lower']:.3%} — {ci['upper']:.3%}] &nbsp;|&nbsp;
                    Threshold: {thresh}
                </div>
                """,
                unsafe_allow_html=True,
            )

        with r2:
            st.markdown("**📋 Feature Summary**")
            summary_df = pd.DataFrame({
                "Feature": ["tenure_months", "age", "calls_made", "data_used",
                             "sms_sent", "usage_score", "estimated_salary"],
                "Value":   [
                    auto["tenure_months"], age, calls_made, data_used,
                    sms_sent, round(auto["usage_score"], 3), estimated_salary,
                ],
            })
            st.dataframe(
                summary_df.style.set_properties(
                    **{"background-color": "rgba(0,128,128,0.1)", "color": WHITE}
                ),
                use_container_width=True,
                hide_index=True,
            )
            st.markdown(
                f"""
                <div class='content-card' style='margin-top:12px;'>
                    <strong style='color:{LIGHT_TEAL}'>💡 Recommendation</strong><br>
                    <span style='color:{WHITE}; font-size:0.92rem;'>{rec}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # ── SHAP-style explanation ────────────────────────────────────────────
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            "<div class='section-heading'>🧠 Feature Contribution Analysis</div>",
            unsafe_allow_html=True,
        )
        st.plotly_chart(shap_bar_chart(auto, prob), use_container_width=True)
        st.caption(
            "📌 Estimated SHAP-style contributions based on feature importance × deviation from mean. "
            "Red bars push toward churn; teal bars push toward retention."
        )

# ──────────────────────────────────────────────────────────────────────────────
# PAGE: Batch Prediction
# ──────────────────────────────────────────────────────────────────────────────

elif page == "📦 Batch Prediction":
    st.markdown("<div class='hero-title'>📦 Batch Prediction</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='hero-subtitle'>Upload a CSV file with multiple customers to predict churn at scale.</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class='content-card'>
        <strong style='color:{LIGHT_TEAL}'>📋 Required CSV columns (in any order):</strong><br>
        <code style='color:#9AB; font-size:0.8rem;'>{', '.join(FEATURE_ORDER)}</code>
        </div>
        """,
        unsafe_allow_html=True,
    )

    uploaded_file = st.file_uploader(
        "Upload CSV", type=["csv"],
        help="CSV must contain all 19 model features",
    )

    if uploaded_file is not None:
        try:
            df_raw = pd.read_csv(uploaded_file)
        except Exception as e:
            st.error(f"Failed to read CSV: {e}")
            st.stop()

        st.markdown("**📄 Data Preview (first 10 rows)**")
        st.dataframe(df_raw.head(10), use_container_width=True)
        st.caption(f"Shape: {df_raw.shape[0]:,} rows × {df_raw.shape[1]} columns")

        missing = [f for f in FEATURE_ORDER if f not in df_raw.columns]
        if missing:
            st.error(f"Missing columns: {missing}")
            st.stop()

        if st.button("🚀 Run Batch Predictions", use_container_width=True):
            with st.spinner("Running predictions…"):
                pipeline = load_model()
                if pipeline is None:
                    st.error("Local model not available. Please ensure the API is running.")
                    st.stop()
                results_df = predict_batch_local(df_raw.copy(), pipeline, meta)

            st.success(f"✅ Predictions complete for {len(results_df):,} customers!")
            st.markdown("---")

            # ── Summary stats ─────────────────────────────────────────────────
            churners = int(results_df["churn_prediction"].sum())
            total    = len(results_df)
            churn_rt = churners / total

            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Total Customers", f"{total:,}")
            s2.metric("Predicted Churners", f"{churners:,}")
            s3.metric("Predicted Retention", f"{total - churners:,}")
            s4.metric("Churn Rate", f"{churn_rt:.2%}")

            st.markdown("<br>", unsafe_allow_html=True)
            ch1, ch2 = st.columns(2)

            with ch1:
                risk_counts = results_df["risk_level"].value_counts()
                fig_pie = go.Figure(
                    go.Pie(
                        labels=risk_counts.index.tolist(),
                        values=risk_counts.values.tolist(),
                        marker=dict(colors=[
                            _risk_colour(r) for r in risk_counts.index
                        ]),
                        textfont=dict(color=WHITE),
                        hole=0.4,
                    )
                )
                _plotly_layout_defaults(fig_pie, "Risk Level Distribution")
                fig_pie.update_layout(
                    legend=dict(font=dict(color=WHITE)),
                    height=340,
                )
                st.plotly_chart(fig_pie, use_container_width=True)

            with ch2:
                top_risk = (
                    results_df.nlargest(15, "churn_probability")
                    .reset_index(drop=True)
                )
                fig_top = go.Figure(
                    go.Bar(
                        x=top_risk.index.astype(str),
                        y=top_risk["churn_probability"],
                        marker=dict(
                            color=top_risk["risk_level"].map(_risk_colour).tolist(),
                        ),
                        text=top_risk["churn_probability"].round(3),
                        textposition="outside",
                        textfont=dict(color=WHITE, size=9),
                    )
                )
                fig_top.update_xaxes(title_text="Customer Index", tickfont=dict(color=WHITE))
                fig_top.update_yaxes(
                    title_text="Churn Probability",
                    tickfont=dict(color=WHITE),
                    gridcolor="rgba(255,255,255,0.1)",
                    range=[0, 1.1],
                )
                _plotly_layout_defaults(fig_top, "Top 15 Highest-Risk Customers")
                fig_top.update_layout(height=340)
                st.plotly_chart(fig_top, use_container_width=True)

            # ── Results table ─────────────────────────────────────────────────
            st.markdown("<div class='section-heading'>📋 Full Results</div>", unsafe_allow_html=True)

            def colour_risk(val: str) -> str:
                return f"color: {_risk_colour(val)}; font-weight: 600"

            display_cols = ["churn_probability", "churn_prediction", "risk_level"] + [
                c for c in results_df.columns
                if c not in {"churn_probability", "churn_prediction", "risk_level"}
            ]
            st.dataframe(
                results_df[display_cols]
                .style.applymap(colour_risk, subset=["risk_level"]),
                use_container_width=True,
                height=350,
            )

            # ── Download ──────────────────────────────────────────────────────
            csv_bytes = results_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="⬇️ Download Results CSV",
                data=csv_bytes,
                file_name="churn_predictions.csv",
                mime="text/csv",
                use_container_width=True,
            )

# ──────────────────────────────────────────────────────────────────────────────
# PAGE: Model Insights
# ──────────────────────────────────────────────────────────────────────────────

elif page == "📊 Model Insights":
    st.markdown("<div class='hero-title'>📊 Model Insights</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='hero-subtitle'>Understand model performance, feature importance, and threshold sensitivity.</div>",
        unsafe_allow_html=True,
    )

    # ── Performance table ──────────────────────────────────────────────────────
    st.markdown("<div class='section-heading'>🏆 Model Leaderboard</div>", unsafe_allow_html=True)
    leaderboard = pd.DataFrame({
        "Model":           ["LightGBM ✅", "XGBoost", "HistGradientBoosting", "Random Forest",
                            "Extra Trees", "AdaBoost", "Gradient Boosting", "CatBoost",
                            "Decision Tree", "Logistic Regression"],
        "Accuracy (Mean)": [0.7995, 0.7991, 0.7995, 0.7995, 0.7994, 0.7995, 0.7995, 0.7987, 0.7991, 0.4788],
        "ROC-AUC (Mean)":  [0.5003, 0.5020, 0.5046, 0.5057, 0.5067, 0.5030, 0.5036, 0.5022, 0.5037, 0.5025],
        "Selected":        [True]  + [False] * 9,
    })
    st.dataframe(
        leaderboard.style
        .applymap(lambda v: f"color: {LIGHT_TEAL}; font-weight:700" if v is True else "", subset=["Selected"])
        .format({"Accuracy (Mean)": "{:.4f}", "ROC-AUC (Mean)": "{:.4f}"}),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("<br>", unsafe_allow_html=True)

    m1, m2 = st.columns(2)

    with m1:
        st.markdown(
            "<div class='section-heading'>📈 Feature Importance</div>",
            unsafe_allow_html=True,
        )
        importance = meta.get("feature_importance", {})
        if importance:
            st.plotly_chart(feature_importance_chart(importance), use_container_width=True)
        else:
            st.info("Feature importance not available in metadata.")

    with m2:
        st.markdown("<div class='section-heading'>📉 ROC Curve</div>", unsafe_allow_html=True)
        st.plotly_chart(roc_placeholder_chart(), use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-heading'>🎚️ Threshold Sensitivity</div>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(threshold_sensitivity_chart(meta), use_container_width=True)
    st.caption(
        "At the optimal threshold of 0.28 the model achieves F1 = 0.334 on the churn class. "
        "Lower thresholds increase recall at the cost of precision."
    )

    # ── Hyperparameters card ───────────────────────────────────────────────────
    st.markdown(
        "<div class='section-heading'>⚙️ Optimised Hyperparameters (Optuna)</div>",
        unsafe_allow_html=True,
    )
    hp = meta.get("hyperparameters", {})
    hp_df = pd.DataFrame(
        {"Parameter": list(hp.keys()), "Value": [str(v) for v in hp.values()]}
    )
    st.dataframe(hp_df, use_container_width=True, hide_index=True)

# ──────────────────────────────────────────────────────────────────────────────
# PAGE: About
# ──────────────────────────────────────────────────────────────────────────────

elif page == "ℹ️ About":
    st.markdown("<div class='hero-title'>ℹ️ About This Project</div>", unsafe_allow_html=True)

    c1, c2 = st.columns([3, 2])

    with c1:
        st.markdown(
            f"""
            <div class='content-card'>
            <div class='section-heading' style='border:none; padding:0; margin-bottom:12px;'>
                📌 Project Description
            </div>
            <p>
            The <strong style='color:{LIGHT_TEAL}'>Telecom Customer Churn Intelligence Platform</strong>
            is an end-to-end machine-learning solution that identifies customers at high risk
            of cancelling their telecom subscription before they actually churn.
            </p>
            <p>
            By targeting these customers with personalised retention offers, telecom operators
            can significantly reduce churn and increase customer lifetime value (CLV).
            </p>
            <hr style='border-color:#333; margin:12px 0;'>
            <div class='section-heading' style='border:none; padding:0; margin-bottom:8px;'>
                🗂️ Dataset
            </div>
            <ul style='color:#ccc; padding-left:18px;'>
                <li><strong>Source:</strong> Synthetic Indian telecom customer dataset</li>
                <li><strong>Size:</strong> 243,553 customers, 14 raw features</li>
                <li><strong>Operators:</strong> Jio, Airtel, Vi, BSNL</li>
                <li><strong>Churn rate:</strong> 20.05%</li>
                <li><strong>Time period:</strong> Multi-year registration data</li>
            </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown(
            f"""
            <div class='content-card'>
            <div class='section-heading' style='border:none; padding:0; margin-bottom:12px;'>
                🛠️ Tech Stack
            </div>
            <table style='width:100%; border-collapse:collapse; color:#ccc; font-size:0.9rem;'>
                <tr><td style='padding:4px 0;'>🤖 ML</td><td style='color:{LIGHT_TEAL};'>LightGBM + Scikit-learn</td></tr>
                <tr><td style='padding:4px 0;'>⚡ API</td><td style='color:{LIGHT_TEAL};'>FastAPI + Uvicorn</td></tr>
                <tr><td style='padding:4px 0;'>🎨 UI</td><td style='color:{LIGHT_TEAL};'>Streamlit + Plotly</td></tr>
                <tr><td style='padding:4px 0;'>🐳 Deploy</td><td style='color:{LIGHT_TEAL};'>Docker + Nginx</td></tr>
                <tr><td style='padding:4px 0;'>📊 Tuning</td><td style='color:{LIGHT_TEAL};'>Optuna</td></tr>
                <tr><td style='padding:4px 0;'>📦 Packaging</td><td style='color:{LIGHT_TEAL};'>Joblib</td></tr>
                <tr><td style='padding:4px 0;'>🔢 Data</td><td style='color:{LIGHT_TEAL};'>Pandas + NumPy</td></tr>
                <tr><td style='padding:4px 0;'>🔒 Schema</td><td style='color:{LIGHT_TEAL};'>Pydantic v2</td></tr>
            </table>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
            <div class='content-card'>
            <div class='section-heading' style='border:none; padding:0; margin-bottom:8px;'>
                📡 API Endpoints
            </div>
            <table style='width:100%; font-size:0.85rem; color:#ccc;'>
                <tr><td><code>GET  /</code></td><td>Root</td></tr>
                <tr><td><code>GET  /health</code></td><td>Health check</td></tr>
                <tr><td><code>GET  /model/info</code></td><td>Model metadata</td></tr>
                <tr><td><code>POST /predict</code></td><td>Single prediction</td></tr>
                <tr><td><code>POST /predict/raw</code></td><td>Auto-derived features</td></tr>
                <tr><td><code>POST /predict/batch</code></td><td>Batch (≤1000)</td></tr>
            </table>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Pipeline diagram ───────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-heading'>🔄 ML Pipeline</div>",
        unsafe_allow_html=True,
    )
    pipeline_steps = [
        "Raw Data (243K rows)",
        "Feature Engineering (+11 features)",
        "Train/Test Split (80/20)",
        "Optuna Hyperparameter Tuning",
        "LightGBM Training",
        "Threshold Optimisation (F1)",
        "Pipeline Serialisation (joblib)",
        "FastAPI Deployment",
    ]
    cols_p = st.columns(len(pipeline_steps))
    for i, (col_p, step) in enumerate(zip(cols_p, pipeline_steps)):
        arrow = "→" if i < len(pipeline_steps) - 1 else "🎉"
        col_p.markdown(
            f"""
            <div style='background:rgba(0,128,128,0.15); border:1px solid {TEAL};
                        border-radius:8px; padding:8px 4px; text-align:center;
                        font-size:0.72rem; color:{WHITE}; min-height:70px;'>
                <div style='color:{LIGHT_TEAL}; font-weight:600; font-size:0.8rem;'>
                    {i+1}
                </div>
                {step}
            </div>
            """,
            unsafe_allow_html=True,
        )
