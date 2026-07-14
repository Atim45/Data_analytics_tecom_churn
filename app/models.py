"""
Pydantic v2 models for the Telecom Churn Prediction API.

All request/response schemas are defined here to keep main.py clean.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ──────────────────────────────────────────────────────────────────────────────
# Request models
# ──────────────────────────────────────────────────────────────────────────────

class CustomerInput(BaseModel):
    """
    19 features expected by the LightGBM pipeline.
    Derived ratio/log features are accepted or can be auto-computed by the API.
    """

    # ── Categorical ────────────────────────────────────────────────────────
    telecom_partner: str = Field(
        ...,
        description="Telecom operator name (Jio, Airtel, Vi, BSNL)",
        examples=["Jio"],
    )
    gender: str = Field(
        ...,
        description="Customer gender (Male / Female)",
        examples=["Male"],
    )

    # ── Demographics ───────────────────────────────────────────────────────
    age: Annotated[int, Field(ge=18, le=74, description="Customer age in years", examples=[35])]
    num_dependents: Annotated[
        int,
        Field(ge=0, le=10, description="Number of dependents (0–10)", examples=[2]),
    ]
    estimated_salary: Annotated[
        int,
        Field(gt=0, description="Estimated annual salary in INR", examples=[500000]),
    ]

    # ── Raw usage ─────────────────────────────────────────────────────────
    calls_made: Annotated[int, Field(ge=0, description="Total calls made", examples=[45])]
    sms_sent: Annotated[int, Field(ge=0, description="Total SMS sent", examples=[20])]
    data_used: Annotated[int, Field(ge=0, description="Total data used (MB)", examples=[5000])]
    tenure_months: Annotated[
        int,
        Field(ge=0, description="Customer tenure in months", examples=[24]),
    ]

    # ── Engineered per-month features ─────────────────────────────────────
    calls_per_month: Annotated[
        float,
        Field(ge=0.0, description="Average calls per month", examples=[1.875]),
    ]
    data_per_month: Annotated[
        float,
        Field(ge=0.0, description="Average data used per month (MB)", examples=[208.33]),
    ]
    sms_per_month: Annotated[
        float,
        Field(ge=0.0, description="Average SMS per month", examples=[0.833]),
    ]

    # ── Engineered ratio features ──────────────────────────────────────────
    data_per_call: Annotated[
        float,
        Field(ge=0.0, description="Average data per call (MB)", examples=[111.11]),
    ]
    sms_to_call_ratio: Annotated[
        float,
        Field(ge=0.0, description="SMS-to-call ratio", examples=[0.444]),
    ]

    # ── Interaction features ───────────────────────────────────────────────
    age_x_dependents: Annotated[
        int,
        Field(ge=0, description="age × num_dependents interaction term", examples=[70]),
    ]

    # ── Log-transformed salary ─────────────────────────────────────────────
    estimated_salary_log: Annotated[
        float,
        Field(description="log1p of estimated_salary", examples=[13.12]),
    ]

    # ── Composite score features ───────────────────────────────────────────
    usage_score: Annotated[
        float,
        Field(ge=0.0, description="Composite usage engagement score", examples=[1.5]),
    ]
    is_low_engagement: Annotated[
        int,
        Field(ge=0, le=1, description="Binary: 1 if low-engagement customer", examples=[0]),
    ]
    low_usage_high_tenure: Annotated[
        int,
        Field(
            ge=0,
            le=1,
            description="Binary: 1 if low usage but long tenure",
            examples=[0],
        ),
    ]

    # ── Validators ────────────────────────────────────────────────────────
    @field_validator("telecom_partner")
    @classmethod
    def validate_partner(cls, v: str) -> str:
        allowed = {"Jio", "Airtel", "Vi", "BSNL"}
        if v not in allowed:
            raise ValueError(f"telecom_partner must be one of {allowed}; got '{v}'")
        return v

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str) -> str:
        allowed = {"Male", "Female"}
        if v.capitalize() not in allowed:
            raise ValueError(f"gender must be 'Male' or 'Female'; got '{v}'")
        return v.capitalize()

    @model_validator(mode="after")
    def validate_cross_fields(self) -> "CustomerInput":
        if self.tenure_months > 0:
            computed_calls = round(self.calls_made / self.tenure_months, 4)
            if abs(computed_calls - self.calls_per_month) > 1.0:
                # Soft warning — we allow the provided value to take precedence
                pass
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "telecom_partner": "Jio",
                "gender": "Male",
                "age": 35,
                "num_dependents": 2,
                "estimated_salary": 500000,
                "calls_made": 45,
                "sms_sent": 20,
                "data_used": 5000,
                "tenure_months": 24,
                "calls_per_month": 1.875,
                "data_per_month": 208.33,
                "sms_per_month": 0.833,
                "data_per_call": 111.11,
                "sms_to_call_ratio": 0.444,
                "age_x_dependents": 70,
                "estimated_salary_log": 13.12,
                "usage_score": 1.5,
                "is_low_engagement": 0,
                "low_usage_high_tenure": 0,
            }
        }
    }


# ──────────────────────────────────────────────────────────────────────────────
# Response models
# ──────────────────────────────────────────────────────────────────────────────

class ChurnResponse(BaseModel):
    """Prediction result for a single customer."""

    customer_index: int = Field(default=0, description="Index in batch (0 for single predictions)")
    churn_probability: float = Field(
        ..., ge=0.0, le=1.0, description="Raw probability of churn (0.0–1.0)"
    )
    churn_prediction: bool = Field(..., description="True if predicted to churn")
    risk_level: str = Field(
        ..., description="Risk tier: LOW / MEDIUM / HIGH / CRITICAL"
    )
    confidence_interval: dict[str, float] = Field(
        ..., description="95% Wald confidence interval for the probability estimate"
    )
    recommendation: str = Field(..., description="Human-readable intervention suggestion")
    model_version: str = Field(..., description="Model version that produced this prediction")
    threshold_used: float = Field(..., description="Decision threshold applied")
    prediction_timestamp: str = Field(..., description="ISO-8601 UTC timestamp")


class BatchInput(BaseModel):
    """Wrapper for multiple customer predictions."""

    customers: list[CustomerInput] = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="List of 1–1000 customer records",
    )


class BatchResponse(BaseModel):
    """Batch prediction result."""

    total_customers: int
    churners_predicted: int
    churn_rate_predicted: float
    predictions: list[ChurnResponse]
    model_version: str
    batch_timestamp: str


class HealthResponse(BaseModel):
    """API health check payload."""

    status: str
    model_loaded: bool
    model_version: str
    uptime_seconds: float
    timestamp: str


class ModelInfoResponse(BaseModel):
    """Metadata about the loaded model."""

    model_name: str
    model_version: str
    framework: str
    optimal_threshold: float
    features: list[str]
    feature_importance: dict[str, float]
    dataset_info: dict[str, Any]
    test_metrics: dict[str, Any]
    description: str


class PredictRawInput(BaseModel):
    """
    Simplified raw input — the API will compute all derived features automatically.
    Useful for callers that only have demographic + raw usage data.
    """

    telecom_partner: str
    gender: str
    age: int = Field(ge=18, le=74)
    num_dependents: int = Field(ge=0, le=10)
    estimated_salary: int = Field(gt=0)
    calls_made: int = Field(ge=0)
    sms_sent: int = Field(ge=0)
    data_used: int = Field(ge=0)
    date_of_registration: str = Field(
        description="ISO date (YYYY-MM-DD) used to compute tenure_months",
        examples=["2022-01-15"],
    )

    @field_validator("telecom_partner")
    @classmethod
    def validate_partner(cls, v: str) -> str:
        allowed = {"Jio", "Airtel", "Vi", "BSNL"}
        if v not in allowed:
            raise ValueError(f"telecom_partner must be one of {allowed}")
        return v

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str) -> str:
        if v.capitalize() not in {"Male", "Female"}:
            raise ValueError("gender must be 'Male' or 'Female'")
        return v.capitalize()

    @field_validator("date_of_registration")
    @classmethod
    def validate_date(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("date_of_registration must be YYYY-MM-DD")
        return v
