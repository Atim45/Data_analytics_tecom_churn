"""
etl/extract.py
===============
EXTRACT stage: read the raw denormalised telecom churn CSV into a pandas
DataFrame with predictable dtypes.

The extraction step deliberately does NOT clean or validate data — it only
guarantees the file exists, is readable, has the expected columns, and is
loaded with sane (mostly string/object) dtypes so that later cleaning steps
have full control over type coercion and error handling.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger("telecom_churn_etl.extract")


# The exact set of columns the pipeline expects from the source CSV, per
# the project's README / data dictionary.
EXPECTED_COLUMNS = [
    "customer_id",
    "telecom_partner",
    "gender",
    "age",
    "state",
    "city",
    "pincode",
    "date_of_registration",
    "num_dependents",
    "estimated_salary",
    "calls_made",
    "sms_sent",
    "data_used",
    "churn",
]


class ExtractionError(RuntimeError):
    """Raised when the source CSV cannot be read or is structurally invalid."""


def extract_csv(csv_path: Path) -> pd.DataFrame:
    """
    Read the raw telecom churn CSV from disk.

    Parameters
    ----------
    csv_path : Path
        Path to the source CSV file.

    Returns
    -------
    pd.DataFrame
        Raw dataframe, all columns read as strings (dtype=str) except where
        pandas infers numerics naturally; downstream cleaning is responsible
        for authoritative type coercion.

    Raises
    ------
    ExtractionError
        If the file is missing, empty, or does not contain the expected
        columns.
    """
    if not csv_path.exists():
        raise ExtractionError(f"Source CSV not found at: {csv_path.resolve()}")

    logger.info("Extracting raw data from: %s", csv_path.resolve())

    try:
        df = pd.read_csv(
            csv_path,
            dtype=str,  # read everything as string first; clean.py coerces types
            keep_default_na=True,
            na_values=["", "NA", "N/A", "null", "NULL", "None", "?"],
        )
    except pd.errors.EmptyDataError as exc:
        raise ExtractionError(f"Source CSV is empty: {csv_path}") from exc
    except pd.errors.ParserError as exc:
        raise ExtractionError(f"Source CSV could not be parsed: {csv_path}. {exc}") from exc

    if df.empty:
        raise ExtractionError(f"Source CSV contains no data rows: {csv_path}")

    missing_columns = set(EXPECTED_COLUMNS) - set(df.columns)
    if missing_columns:
        raise ExtractionError(
            f"Source CSV is missing expected column(s): {sorted(missing_columns)}. "
            f"Found columns: {list(df.columns)}"
        )

    extra_columns = set(df.columns) - set(EXPECTED_COLUMNS)
    if extra_columns:
        logger.warning(
            "Source CSV contains unexpected extra column(s) that will be ignored: %s",
            sorted(extra_columns),
        )

    # Keep only the expected columns, in a stable, known order.
    df = df[EXPECTED_COLUMNS].copy()

    logger.info("Extracted %s raw rows, %s columns.", len(df), len(df.columns))
    return df
