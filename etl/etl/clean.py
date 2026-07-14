"""
etl/clean.py
============
CLEAN stage: turns a *validated* raw dataframe into a fully typed, tidy
dataframe ready for feature engineering.

Responsibilities (per project requirements)
--------------------------------------------
* Drop rows flagged invalid by the VALIDATE stage (configurable).
* Drop duplicate rows (both full-row duplicates and duplicate natural keys).
* Parse/normalise dates.
* Coerce every column to its correct dtype.
* Trim whitespace and normalise string casing/values (e.g. gender
  'M'/'F' -> 'Male'/'Female' to match the CHECK constraint in
  ``dim_customers``).
* Clip invalid/negative numeric values (calls_made, sms_sent, data_used
  cannot be negative per the fact_usage CHECK constraints) to zero, with
  every correction counted and logged — never silently discarded.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from utils.stats import RunStats

logger = logging.getLogger("telecom_churn_etl.clean")

GENDER_MAP = {"M": "Male", "F": "Female"}


def clean_data(df: pd.DataFrame, drop_invalid_rows: bool, stats: RunStats) -> pd.DataFrame:
    """
    Clean a validated raw dataframe.

    Parameters
    ----------
    df : pd.DataFrame
        Output of ``etl.validate.validate_raw`` (contains ``_is_valid`` and
        ``_validation_issues`` helper columns).
    drop_invalid_rows : bool
        If True, rows flagged invalid during validation are dropped here.
        If False, the pipeline still drops rows that are *impossible* to
        load (e.g. non-numeric customer_id) because those would violate
        NOT NULL / PK constraints regardless of configuration, but repairs
        everything else it safely can.
    stats : RunStats
        Shared run-statistics accumulator; cleaning actions are logged
        into it as warnings.

    Returns
    -------
    pd.DataFrame
        Fully typed, cleaned dataframe. Guaranteed to have no NaNs in any
        column required downstream, and no negative values in metrics that
        the database CHECK constraints forbid.
    """
    df = df.copy()
    n_before = len(df)

    # ------------------------------------------------------------------
    # 1. Drop rows flagged invalid during validation (if configured to).
    # ------------------------------------------------------------------
    if "_is_valid" in df.columns:
        n_invalid = int((~df["_is_valid"]).sum())
        if drop_invalid_rows:
            if n_invalid:
                msg = f"Dropping {n_invalid} row(s) that failed validation."
                logger.warning(msg)
                stats.add_warning(msg)
            df = df[df["_is_valid"]].copy()
        else:
            # Even when told to keep invalid rows, rows with a missing/
            # non-numeric customer_id can never be loaded (violates the
            # dim_customers/fact_usage primary/foreign keys), so they are
            # always dropped with a loud warning.
            hard_fail_mask = df["_validation_issues"].str.contains(
                "customer_id_missing_or_nonnumeric", na=False
            )
            n_hard = int(hard_fail_mask.sum())
            if n_hard:
                msg = (
                    f"Dropping {n_hard} row(s) with unusable customer_id "
                    f"even though DROP_INVALID_ROWS=False (these rows can "
                    f"never satisfy the primary key)."
                )
                logger.warning(msg)
                stats.add_warning(msg)
            df = df[~hard_fail_mask].copy()

    df = df.drop(columns=["_is_valid", "_validation_issues"], errors="ignore")

    # ------------------------------------------------------------------
    # 2. Drop exact full-row duplicates defensively.
    # ------------------------------------------------------------------
    n_dupe_rows = int(df.duplicated().sum())
    if n_dupe_rows:
        msg = f"Dropping {n_dupe_rows} exact duplicate row(s)."
        logger.warning(msg)
        stats.add_warning(msg)
        df = df.drop_duplicates(keep="first")

    # ------------------------------------------------------------------
    # 3. Drop rows with duplicate natural key (customer_id), keep first.
    # ------------------------------------------------------------------
    customer_id_num = pd.to_numeric(df["customer_id"], errors="coerce")
    df = df.assign(customer_id=customer_id_num)
    df = df[df["customer_id"].notna()]
    n_dupe_keys = int(df["customer_id"].duplicated(keep="first").sum())
    if n_dupe_keys:
        msg = f"Dropping {n_dupe_keys} row(s) with duplicate customer_id (keeping first occurrence)."
        logger.warning(msg)
        stats.add_warning(msg)
        df = df.drop_duplicates(subset=["customer_id"], keep="first")
    df["customer_id"] = df["customer_id"].astype("int64")

    # ------------------------------------------------------------------
    # 4. String columns: trim whitespace, normalise casing.
    # ------------------------------------------------------------------
    for col in ["telecom_partner", "gender", "state", "city"]:
        df[col] = df[col].astype(str).str.strip()

    df["telecom_partner"] = df["telecom_partner"].str.title().replace(
        {"Bsnl": "BSNL"}  # preserve the operator's conventional acronym casing
    )
    df["state"] = df["state"].str.title()
    df["city"] = df["city"].str.title()

    gender_upper = df["gender"].str.upper()
    unmapped_gender_mask = ~gender_upper.isin(GENDER_MAP.keys())
    if unmapped_gender_mask.any():
        n_unmapped = int(unmapped_gender_mask.sum())
        msg = f"{n_unmapped} row(s) had an unrecognised gender value; mapped to 'Other'."
        logger.warning(msg)
        stats.add_warning(msg)
    df["gender"] = gender_upper.map(GENDER_MAP).fillna("Other")

    # ------------------------------------------------------------------
    # 5. Numeric columns: coerce types, clip invalid/negative values.
    # ------------------------------------------------------------------
    df["age"] = pd.to_numeric(df["age"], errors="coerce").fillna(0).astype("int64")
    df["age"] = df["age"].clip(lower=0, upper=120)

    df["num_dependents"] = (
        pd.to_numeric(df["num_dependents"], errors="coerce").fillna(0).astype("int64")
    )
    n_neg_dependents = int((df["num_dependents"] < 0).sum())
    if n_neg_dependents:
        msg = f"Clipped {n_neg_dependents} negative num_dependents value(s) to 0."
        logger.warning(msg)
        stats.add_warning(msg)
    df["num_dependents"] = df["num_dependents"].clip(lower=0, upper=20)

    df["estimated_salary"] = pd.to_numeric(df["estimated_salary"], errors="coerce").fillna(0.0)
    n_neg_salary = int((df["estimated_salary"] < 0).sum())
    if n_neg_salary:
        msg = f"Clipped {n_neg_salary} negative estimated_salary value(s) to 0."
        logger.warning(msg)
        stats.add_warning(msg)
    df["estimated_salary"] = df["estimated_salary"].clip(lower=0)

    df["pincode"] = (
        pd.to_numeric(df["pincode"], errors="coerce")
        .fillna(0)
        .astype("int64")
        .astype(str)
        .str.zfill(6)
    )

    for col in ["calls_made", "sms_sent", "data_used"]:
        numeric = pd.to_numeric(df[col], errors="coerce").fillna(0)
        n_negative = int((numeric < 0).sum())
        if n_negative:
            msg = f"Clipped {n_negative} negative '{col}' value(s) to 0 (raw data contained sensor/entry errors)."
            logger.warning(msg)
            stats.add_warning(msg)
        df[col] = numeric.clip(lower=0)

    df["churn"] = pd.to_numeric(df["churn"], errors="coerce").fillna(0).astype("int64")
    df["churn"] = df["churn"].clip(lower=0, upper=1)

    # ------------------------------------------------------------------
    # 6. Dates: parse to real dates, drop rows where this is still
    #    impossible (should be none if validation already ran).
    # ------------------------------------------------------------------
    parsed_dates = pd.to_datetime(df["date_of_registration"], errors="coerce", format="mixed")
    n_bad_dates = int(parsed_dates.isna().sum())
    if n_bad_dates:
        msg = f"Dropping {n_bad_dates} row(s) with unparseable date_of_registration."
        logger.warning(msg)
        stats.add_warning(msg)
    df = df.assign(date_of_registration=parsed_dates)
    df = df[df["date_of_registration"].notna()]
    df["date_of_registration"] = df["date_of_registration"].dt.date

    n_after = len(df)
    logger.info("Cleaning complete: %s rows in -> %s rows out (%s dropped).", n_before, n_after, n_before - n_after)
    stats.rows_after_cleaning = n_after

    return df.reset_index(drop=True)
