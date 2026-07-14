"""
Production FastAPI service for Telecom Customer Churn Prediction.

Features
--------
- Lifespan context manager for model loading / teardown
- CORS middleware
- Custom request-logging middleware
- SlowAPI rate limiting (100 req/min per IP)
- Pydantic v2 request/response validation
- Structured JSON logging
- Single and batch prediction endpoints
- Auto-computation of derived features from raw input
"""



import json
import math
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from logger import configure_logging
from models import (
    BatchInput,
    BatchResponse,
    ChurnResponse,
    CustomerInput,
    HealthResponse,
    ModelInfoResponse,
    PredictRawInput,
)

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
PARENT_DIR = BASE_DIR.parent

MODEL_PATH = BASE_DIR / "telecom_churn_pipeline.joblib"
METADATA_PATH = Path(os.getenv("METADATA_PATH", PARENT_DIR / "model_metadata.json"))
RATE_LIMIT = os.getenv("RATE_LIMIT", "100/minute")

FEATURE_ORDER = [
    "telecom_partner", "gender", "age", "num_dependents", "estimated_salary",
    "calls_made", "sms_sent", "data_used", "tenure_months",
    "calls_per_month", "data_per_month", "sms_per_month",
    "data_per_call", "sms_to_call_ratio", "age_x_dependents",
    "estimated_salary_log", "usage_score", "is_low_engagement",
    "low_usage_high_tenure",
]

# ──────────────────────────────────────────────────────────────────────────────
# Global state (populated during lifespan)
# ──────────────────────────────────────────────────────────────────────────────

_state: dict[str, Any] = {
    "pipeline": None,
    "metadata": {},
    "threshold": 0.28,
    "model_version": "unknown",
    "start_time": time.monotonic(),
}

# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────

logger = configure_logging("churn_api")

# ──────────────────────────────────────────────────────────────────────────────
# Rate limiter
# ──────────────────────────────────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address, default_limits=[RATE_LIMIT])

# ──────────────────────────────────────────────────────────────────────────────
# Lifespan
# ──────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup, release resources on shutdown."""
    logger.info("Loading model …", extra={"model_path": str(MODEL_PATH)})

    if not MODEL_PATH.exists():
        logger.error("Model file not found", extra={"path": str(MODEL_PATH)})
        raise FileNotFoundError(f"Model not found: {MODEL_PATH}")

    _state["pipeline"] = joblib.load(MODEL_PATH)
    logger.info("Model loaded successfully")

    if METADATA_PATH.exists():
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            _state["metadata"] = json.load(f)
        _state["threshold"] = float(_state["metadata"].get("optimal_threshold", 0.28))
        _state["model_version"] = _state["metadata"].get("model_version", "1.0.0")
        logger.info(
            "Metadata loaded",
            extra={
                "threshold": _state["threshold"],
                "version": _state["model_version"],
            },
        )
    else:
        logger.warning("model_metadata.json not found — using defaults")

    _state["start_time"] = time.monotonic()
    yield

    logger.info("Shutting down API — releasing resources")
    _state["pipeline"] = None

# ──────────────────────────────────────────────────────────────────────────────
# App
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Telecom Churn Prediction API",
    description=(
        "Production-grade REST API for predicting customer churn in Indian telecom. "
        "Powered by a tuned LightGBM pipeline trained on 243 K customers."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Rate-limit error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────────────────────────────────────
# Request logging middleware
# ──────────────────────────────────────────────────────────────────────────────

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

    logger.info(
        "HTTP request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": elapsed_ms,
            "client_ip": request.client.host if request.client else "unknown",
        },
    )
    response.headers["X-Response-Time-Ms"] = str(elapsed_ms)
    return response

# ──────────────────────────────────────────────────────────────────────────────
# Helper utilities
# ──────────────────────────────────────────────────────────────────────────────

def _risk_level(prob: float) -> str:
    if prob < 0.25:
        return "LOW"
    elif prob < 0.45:
        return "MEDIUM"
    elif prob < 0.65:
        return "HIGH"
    return "CRITICAL"


def _recommendation(prob: float, risk: str) -> str:
    mapping = {
        "LOW": "No immediate action required. Monitor quarterly.",
        "MEDIUM": "Send a personalised retention offer and review plan suitability.",
        "HIGH": "Immediate outreach recommended — escalate to retention team.",
        "CRITICAL": "Priority intervention: offer a loyalty discount or premium plan upgrade.",
    }
    return mapping[risk]


def _confidence_interval(prob: float, n: int = 1000) -> dict[str, float]:
    """95 % Wald interval, clipped to [0, 1]."""
    z = 1.96
    margin = z * math.sqrt(prob * (1 - prob) / n)
    return {
        "lower": round(max(0.0, prob - margin), 4),
        "upper": round(min(1.0, prob + margin), 4),
    }


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _customer_to_df(customer: CustomerInput) -> pd.DataFrame:
    row = customer.model_dump()
    return pd.DataFrame([row], columns=FEATURE_ORDER)[FEATURE_ORDER]


def _predict_single(customer: CustomerInput, idx: int = 0) -> ChurnResponse:
    pipeline = _state["pipeline"]
    threshold = _state["threshold"]
    version = _state["model_version"]

    df = _customer_to_df(customer)
    prob = float(pipeline.predict_proba(df)[0, 1])
    churn = prob >= threshold
    risk = _risk_level(prob)

    return ChurnResponse(
        customer_index=idx,
        churn_probability=round(prob, 6),
        churn_prediction=churn,
        risk_level=risk,
        confidence_interval=_confidence_interval(prob),
        recommendation=_recommendation(prob, risk),
        model_version=version,
        threshold_used=threshold,
        prediction_timestamp=_now_iso(),
    )


def _compute_derived_features(raw: PredictRawInput) -> CustomerInput:
    """Auto-compute all engineered features from a PredictRawInput."""
    reg_date = datetime.strptime(raw.date_of_registration, "%Y-%m-%d")
    now = datetime.now()
    tenure_months = max(1, (now.year - reg_date.year) * 12 + (now.month - reg_date.month))

    calls = max(raw.calls_made, 0)
    sms = max(raw.sms_sent, 0)
    data = max(raw.data_used, 0)
    t = max(tenure_months, 1)

    calls_per_month = round(calls / t, 4)
    data_per_month = round(data / t, 4)
    sms_per_month = round(sms / t, 4)
    data_per_call = round(data / calls, 4) if calls > 0 else 0.0
    sms_to_call_ratio = round(sms / calls, 4) if calls > 0 else 0.0
    age_x_dependents = raw.age * raw.num_dependents
    estimated_salary_log = round(math.log1p(raw.estimated_salary), 6)

    total = calls + sms + data / 1000
    usage_score = round(total / t, 4) if t > 0 else 0.0
    is_low_engagement = int(usage_score < 1.0)
    low_usage_high_tenure = int(is_low_engagement == 1 and tenure_months > 24)

    return CustomerInput(
        telecom_partner=raw.telecom_partner,
        gender=raw.gender,
        age=raw.age,
        num_dependents=raw.num_dependents,
        estimated_salary=raw.estimated_salary,
        calls_made=calls,
        sms_sent=sms,
        data_used=data,
        tenure_months=tenure_months,
        calls_per_month=calls_per_month,
        data_per_month=data_per_month,
        sms_per_month=sms_per_month,
        data_per_call=data_per_call,
        sms_to_call_ratio=sms_to_call_ratio,
        age_x_dependents=age_x_dependents,
        estimated_salary_log=estimated_salary_log,
        usage_score=usage_score,
        is_low_engagement=is_low_engagement,
        low_usage_high_tenure=low_usage_high_tenure,
    )

# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@app.get(
    "/",
    summary="API root",
    tags=["General"],
    response_model=dict,
)
async def root():
    """Welcome message and link to docs."""
    return {
        "service": "Telecom Churn Prediction API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get(
    "/health",
    summary="Health check",
    tags=["General"],
    response_model=HealthResponse,
)
@limiter.limit("200/minute")
async def health(request: Request):
    """Liveness / readiness probe."""
    model_loaded = _state["pipeline"] is not None
    if not model_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not loaded",
        )
    return HealthResponse(
        status="healthy",
        model_loaded=model_loaded,
        model_version=_state["model_version"],
        uptime_seconds=round(time.monotonic() - _state["start_time"], 2),
        timestamp=_now_iso(),
    )


@app.get(
    "/model/info",
    summary="Model metadata",
    tags=["Model"],
    response_model=ModelInfoResponse,
)
@limiter.limit("60/minute")
async def model_info(request: Request):
    """Return metadata about the loaded model."""
    meta = _state["metadata"]
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="model_metadata.json not available",
        )
    return ModelInfoResponse(
        model_name=meta.get("model_name", "LightGBM Churn Classifier"),
        model_version=meta.get("model_version", "1.0.0"),
        framework=meta.get("framework", "LightGBM"),
        optimal_threshold=meta.get("optimal_threshold", 0.28),
        features=meta.get("features", FEATURE_ORDER),
        feature_importance=meta.get("feature_importance", {}),
        dataset_info=meta.get("dataset", {}),
        test_metrics=meta.get("test_metrics", {}),
        description=meta.get("description", ""),
    )


@app.post(
    "/predict",
    summary="Single customer churn prediction",
    tags=["Prediction"],
    response_model=ChurnResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit(RATE_LIMIT)
async def predict(request: Request, customer: CustomerInput):
    """
    Predict churn probability for a single customer.

    All 19 features must be provided. Use `/predict/raw` if you only have
    demographic and raw usage data and want the API to compute derived features.
    """
    if _state["pipeline"] is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not ready",
        )
    try:
        result = _predict_single(customer)
        logger.info(
            "Single prediction",
            extra={
                "prob": result.churn_probability,
                "risk": result.risk_level,
                "churn": result.churn_prediction,
            },
        )
        return result
    except Exception as exc:
        logger.exception("Prediction error", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prediction failed: {exc}",
        )


@app.post(
    "/predict/raw",
    summary="Predict from raw inputs (auto-compute derived features)",
    tags=["Prediction"],
    response_model=ChurnResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit(RATE_LIMIT)
async def predict_raw(request: Request, raw: PredictRawInput):
    """
    Accept simplified raw inputs (demographic + raw usage + date_of_registration).
    The API computes tenure_months and all engineered features automatically.
    """
    if _state["pipeline"] is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not ready",
        )
    try:
        customer = _compute_derived_features(raw)
        result = _predict_single(customer)
        logger.info(
            "Raw prediction",
            extra={"computed_tenure": customer.tenure_months, "prob": result.churn_probability},
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Raw prediction error", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prediction failed: {exc}",
        )


@app.post(
    "/predict/batch",
    summary="Batch churn prediction (up to 1 000 customers)",
    tags=["Prediction"],
    response_model=BatchResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("20/minute")
async def predict_batch(request: Request, batch: BatchInput):
    """
    Run predictions on up to 1 000 customers in a single call.
    Returns individual predictions plus aggregate statistics.
    """
    if _state["pipeline"] is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not ready",
        )
    try:
        pipeline = _state["pipeline"]
        threshold = _state["threshold"]
        version = _state["model_version"]

        rows = [c.model_dump() for c in batch.customers]
        df = pd.DataFrame(rows, columns=FEATURE_ORDER)[FEATURE_ORDER]
        probs = pipeline.predict_proba(df)[:, 1]

        predictions: list[ChurnResponse] = []
        for idx, (prob, customer) in enumerate(zip(probs, batch.customers)):
            prob_f = float(prob)
            churn = prob_f >= threshold
            risk = _risk_level(prob_f)
            predictions.append(
                ChurnResponse(
                    customer_index=idx,
                    churn_probability=round(prob_f, 6),
                    churn_prediction=churn,
                    risk_level=risk,
                    confidence_interval=_confidence_interval(prob_f),
                    recommendation=_recommendation(prob_f, risk),
                    model_version=version,
                    threshold_used=threshold,
                    prediction_timestamp=_now_iso(),
                )
            )

        churners = sum(1 for p in predictions if p.churn_prediction)
        total = len(predictions)

        logger.info(
            "Batch prediction complete",
            extra={
                "total": total,
                "churners": churners,
                "churn_rate": round(churners / total, 4),
            },
        )

        return BatchResponse(
            total_customers=total,
            churners_predicted=churners,
            churn_rate_predicted=round(churners / total, 4),
            predictions=predictions,
            model_version=version,
            batch_timestamp=_now_iso(),
        )
    except Exception as exc:
        logger.exception("Batch prediction error", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch prediction failed: {exc}",
        )


# ──────────────────────────────────────────────────────────────────────────────
# Global exception handler
# ──────────────────────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Please try again later."},
    )


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("RELOAD", "false").lower() == "true",
        workers=int(os.getenv("WORKERS", 1)),
        log_level="info",
    )
