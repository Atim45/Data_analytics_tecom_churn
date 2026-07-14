"""
etl/transform.py
=================
TRANSFORM stage: derives every engineered feature required by
``churn.fact_usage``, using the exact formulas documented as SQL column
comments in ``01_schema.sql`` (the schema is the source of truth).

This stage does NOT touch the database. It only adds new, deterministic,
pure-function columns to the cleaned dataframe. Dimension surrogate-key
resolution happens later, in ``etl.load_dimensions`` /
``etl.load_facts``, once the dimension tables have been populated.

Formulas (from 01_schema.sql column comments)
------------------------------------------------
tenure_months        : months between date_of_registration and snapshot_date
calls_per_month       : calls_made / tenure_months            (0 if tenure_months = 0)
data_per_month        : data_used  / tenure_months            (0 if tenure_months = 0)
sms_per_month         : sms_sent   / tenure_months            (0 if tenure_months = 0)
data_per_call         : data_used  / calls_made               (0 if calls_made = 0)
sms_to_call_ratio     : sms_sent   / calls_made               (0 if calls_made = 0)
age_x_dependents      : age * num_dependents
estimated_salary_log  : LOG(1 + estimated_salary)             (natural log, i.e. log1p)
usage_score           : (calls_made/100 + data_used + sms_sent/100) / 3
is_low_engagement     : 1 if calls_made < 10 AND data_used < 1 AND sms_sent < 5 else 0
low_usage_high_tenure : 1 if is_low_engagement = 1 AND tenure_months > 12 else 0
"""

from __future__ import annotations

import logging
from datetime import date

import numpy as np
import pandas as pd

from etl.reference_data import get_region_for_state
from utils.stats import RunStats

logger = logging.getLogger("telecom_churn_etl.transform")

MIN_VALID_DATE_ID = 20150101  # matches dim_date lower bound in 01_schema.sql
MAX_VALID_DATE_ID = 20301231  # matches dim_date upper bound in 01_schema.sql

AVG_DAYS_PER_MONTH = 30.44  # standard average used for day->month conversion


def _date_to_date_id(d: date) -> int:
    """Compute the YYYYMMDD surrogate key used by dim_date, without a DB round-trip."""
    return int(d.strftime("%Y%m%d"))


def transform_data(df: pd.DataFrame, snapshot_date: date, stats: RunStats) -> pd.DataFrame:
    """
    Add all engineered fact_usage columns to the cleaned dataframe.

    Parameters
    ----------
    df : pd.DataFrame
        Output of ``etl.clean.clean_data``.
    snapshot_date : date
        The "as of" reporting date for this load; used to compute
        tenure_months and to resolve ``fact_usage.snapshot_date_id``.
    stats : RunStats
        Shared run-statistics accumulator.

    Returns
    -------
    pd.DataFrame
        The input dataframe with engineered columns appended.
    """
    df = df.copy()

    # ------------------------------------------------------------------
    # Date surrogate keys
    # ------------------------------------------------------------------
    df["registration_date_id"] = df["date_of_registration"].apply(_date_to_date_id)
    snapshot_date_id = _date_to_date_id(snapshot_date)
    df["snapshot_date_id"] = snapshot_date_id

    out_of_range_mask = (df["registration_date_id"] < MIN_VALID_DATE_ID) | (
        df["registration_date_id"] > MAX_VALID_DATE_ID
    )
    n_out_of_range = int(out_of_range_mask.sum())
    if n_out_of_range:
        msg = (
            f"Dropping {n_out_of_range} row(s) whose date_of_registration falls "
            f"outside the populated dim_date range (2015-01-01 to 2030-12-31)."
        )
        logger.warning(msg)
        stats.add_warning(msg)
        df = df[~out_of_range_mask].copy()

    if not (MIN_VALID_DATE_ID <= snapshot_date_id <= MAX_VALID_DATE_ID):
        raise ValueError(
            f"Configured SNAPSHOT_DATE ({snapshot_date}) falls outside the populated "
            f"dim_date range (2015-01-01 to 2030-12-31). Choose a different snapshot date."
        )

    # ------------------------------------------------------------------
    # Tenure (months)
    # ------------------------------------------------------------------
    reg_dates = pd.to_datetime(df["date_of_registration"])
    snap_ts = pd.Timestamp(snapshot_date)
    tenure_days = (snap_ts - reg_dates).dt.days

    n_future_registrations = int((tenure_days < 0).sum())
    if n_future_registrations:
        msg = (
            f"{n_future_registrations} row(s) had a date_of_registration after the "
            f"snapshot date; tenure_months clipped to 0 for these rows."
        )
        logger.warning(msg)
        stats.add_warning(msg)

    tenure_days = tenure_days.clip(lower=0)
    df["tenure_months"] = (tenure_days / AVG_DAYS_PER_MONTH).round(2)

    # ------------------------------------------------------------------
    # Normalised usage rates (guard against division by zero)
    # ------------------------------------------------------------------
    safe_tenure = df["tenure_months"].replace(0, np.nan)

    df["calls_per_month"] = (df["calls_made"] / safe_tenure).fillna(0).round(2)
    df["data_per_month"] = (df["data_used"] / safe_tenure).fillna(0).round(4)
    df["sms_per_month"] = (df["sms_sent"] / safe_tenure).fillna(0).round(2)

    safe_calls = df["calls_made"].replace(0, np.nan)
    df["data_per_call"] = (df["data_used"] / safe_calls).fillna(0).round(4)
    df["sms_to_call_ratio"] = (df["sms_sent"] / safe_calls).fillna(0).round(4)

    # ------------------------------------------------------------------
    # Interaction / transformed features
    # ------------------------------------------------------------------
    df["age_x_dependents"] = (df["age"] * df["num_dependents"]).astype(float).round(2)
    df["estimated_salary_log"] = np.log1p(df["estimated_salary"]).round(6)

    # ------------------------------------------------------------------
    # Composite engagement score & binary flags
    # ------------------------------------------------------------------
    df["usage_score"] = (
        (df["calls_made"] / 100.0) + df["data_used"] + (df["sms_sent"] / 100.0)
    ) / 3.0
    df["usage_score"] = df["usage_score"].round(4)

    df["is_low_engagement"] = (
        (df["calls_made"] < 10) & (df["data_used"] < 1) & (df["sms_sent"] < 5)
    ).astype("int64")

    df["low_usage_high_tenure"] = (
        (df["is_low_engagement"] == 1) & (df["tenure_months"] > 12)
    ).astype("int64")

    # ------------------------------------------------------------------
    # Geography enrichment (region has no source column)
    # ------------------------------------------------------------------
    df["region"] = df["state"].apply(get_region_for_state)
    n_unknown_region = int((df["region"] == "Unknown").sum())
    if n_unknown_region:
        msg = (
            f"{n_unknown_region} row(s) map to a state not present in the "
            f"STATE_TO_REGION reference table; region set to 'Unknown'."
        )
        logger.warning(msg)
        stats.add_warning(msg)

    stats.rows_transformed = len(df)
    logger.info("Transformation complete: %s rows with engineered features.", len(df))

    return df.reset_index(drop=True)
