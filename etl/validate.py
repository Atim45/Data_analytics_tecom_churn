"""
etl/validate.py
================
VALIDATE stage: structural and business-rule validation of the raw
dataframe, run BEFORE cleaning/transformation.

This stage never silently mutates data — it only *classifies* rows as
valid/invalid and produces a validation report. The caller (main.py)
decides, based on configuration (``DROP_INVALID_ROWS``), whether to drop
invalid rows or abort the pipeline.

Validation checks performed
----------------------------
1. customer_id: present, non-null, unique (natural key).
2. gender: present, one of the allowed raw values ('M', 'F') — anything
   else is flagged.
3. age: numeric, within a plausible human range (0-120, matching the
   dim_customers CHECK constraint).
4. num_dependents: numeric, >= 0.
5. estimated_salary: numeric, >= 0.
6. date_of_registration: parseable date, not in the future.
7. pincode: numeric, exactly 6 digits (Indian PIN code format).
8. state / city / telecom_partner: present (non-null, non-blank).
9. calls_made / sms_sent / data_used: numeric (sign is handled later in
   the CLEAN stage — negative values are a cleaning concern, not a
   structural-validity concern).
10. churn: numeric, in {0, 1}.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

import numpy as np
import pandas as pd

logger = logging.getLogger("telecom_churn_etl.validate")

ALLOWED_GENDER_RAW = {"M", "F"}
MIN_AGE, MAX_AGE = 0, 120
MIN_SALARY = 0


@dataclass
class ValidationReport:
    """Structured record of what validation found, for the JSON report."""

    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    issue_counts: dict = field(default_factory=dict)
    sample_issues: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "invalid_rows": self.invalid_rows,
            "issue_counts": self.issue_counts,
            "sample_issues": self.sample_issues[:50],
        }


def _numeric_or_nan(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def validate_raw(df: pd.DataFrame) -> tuple[pd.DataFrame, ValidationReport]:
    """
    Validate the raw extracted dataframe.

    Parameters
    ----------
    df : pd.DataFrame
        Raw dataframe as returned by ``extract.extract_csv``.

    Returns
    -------
    (pd.DataFrame, ValidationReport)
        The same dataframe with an added boolean ``_is_valid`` column and a
        ``_validation_issues`` column (comma-separated issue codes), plus
        the aggregate ValidationReport.
    """
    report = ValidationReport(total_rows=len(df))
    issues = pd.Series([[] for _ in range(len(df))], index=df.index, dtype=object)

    def flag(mask: pd.Series, code: str) -> None:
        """Append an issue code to every row where mask is True."""
        count = int(mask.sum())
        if count:
            report.issue_counts[code] = report.issue_counts.get(code, 0) + count
            for idx in df.index[mask]:
                issues.at[idx].append(code)

    # --- customer_id ---
    customer_id_num = _numeric_or_nan(df["customer_id"])
    flag(customer_id_num.isna(), "customer_id_missing_or_nonnumeric")
    duplicate_mask = df["customer_id"].duplicated(keep="first") & customer_id_num.notna()
    flag(duplicate_mask, "customer_id_duplicate")

    # --- gender ---
    gender_clean = df["gender"].astype(str).str.strip().str.upper()
    flag(~gender_clean.isin(ALLOWED_GENDER_RAW), "gender_invalid")

    # --- age ---
    age_num = _numeric_or_nan(df["age"])
    flag(age_num.isna(), "age_nonnumeric")
    flag(age_num.notna() & ((age_num < MIN_AGE) | (age_num > MAX_AGE)), "age_out_of_range")

    # --- num_dependents ---
    dependents_num = _numeric_or_nan(df["num_dependents"])
    flag(dependents_num.isna(), "num_dependents_nonnumeric")
    flag(dependents_num.notna() & (dependents_num < 0), "num_dependents_negative")

    # --- estimated_salary ---
    salary_num = _numeric_or_nan(df["estimated_salary"])
    flag(salary_num.isna(), "estimated_salary_nonnumeric")
    flag(salary_num.notna() & (salary_num < MIN_SALARY), "estimated_salary_negative")

    # --- date_of_registration ---
    reg_date = pd.to_datetime(df["date_of_registration"], errors="coerce", format="mixed")
    flag(reg_date.isna(), "date_of_registration_invalid")
    today = pd.Timestamp.today().normalize()
    flag(reg_date.notna() & (reg_date > today), "date_of_registration_in_future")

    # --- pincode ---
    pincode_str = df["pincode"].astype(str).str.strip()
    pincode_num = _numeric_or_nan(df["pincode"])
    flag(pincode_num.isna(), "pincode_nonnumeric")
    valid_len_mask = pincode_str.str.fullmatch(r"\d{6}")
    flag(pincode_num.notna() & ~valid_len_mask, "pincode_not_six_digits")

    # --- state / city / telecom_partner presence ---
    for col, code in [
        ("state", "state_missing"),
        ("city", "city_missing"),
        ("telecom_partner", "telecom_partner_missing"),
    ]:
        blank_mask = df[col].isna() | (df[col].astype(str).str.strip() == "")
        flag(blank_mask, code)

    # --- usage metrics: must be numeric (sign is a CLEAN-stage concern) ---
    for col, code in [
        ("calls_made", "calls_made_nonnumeric"),
        ("sms_sent", "sms_sent_nonnumeric"),
        ("data_used", "data_used_nonnumeric"),
    ]:
        numeric_series = _numeric_or_nan(df[col])
        flag(numeric_series.isna(), code)

    # --- churn ---
    churn_num = _numeric_or_nan(df["churn"])
    flag(churn_num.isna(), "churn_nonnumeric")
    flag(churn_num.notna() & ~churn_num.isin([0, 1]), "churn_invalid_value")

    df = df.copy()
    df["_validation_issues"] = issues.apply(lambda x: ",".join(x) if x else "")
    df["_is_valid"] = df["_validation_issues"] == ""

    report.valid_rows = int(df["_is_valid"].sum())
    report.invalid_rows = int((~df["_is_valid"]).sum())

    invalid_examples = df.loc[~df["_is_valid"], ["customer_id", "_validation_issues"]].head(50)
    report.sample_issues = [
        f"customer_id={row.customer_id}: {row._validation_issues}"
        for row in invalid_examples.itertuples()
    ]

    logger.info(
        "Validation complete: %s/%s rows valid, %s rows flagged with issues.",
        report.valid_rows,
        report.total_rows,
        report.invalid_rows,
    )
    if report.issue_counts:
        for code, count in sorted(report.issue_counts.items(), key=lambda kv: -kv[1]):
            logger.warning("Validation issue '%s' affected %s row(s).", code, count)

    return df, report
