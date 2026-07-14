"""
etl/load_facts.py
==================
LOAD FACTS stage: resolves dimension surrogate keys and bulk-loads
``churn.fact_usage``.

Referential integrity
----------------------
Every row is resolved against the dimension mappings produced by
``etl.load_dimensions`` (customer_sk, geography_id, partner_id). Any row
that cannot be fully resolved is dropped and logged as an error rather
than being sent to the database, where it would violate a FOREIGN KEY
constraint and abort the whole batch.

Idempotency
-----------
``fact_usage`` has no natural unique constraint on (customer_id,
snapshot_date_id) in the supplied schema, so re-running the pipeline for
the same snapshot date would otherwise create duplicate fact rows. To keep
re-runs safe, this stage deletes any existing fact rows for the customers
and snapshot_date_id being loaded before inserting — i.e. each snapshot
load is a full replace for that date, which matches the "one row per
customer per monthly snapshot" grain documented in the schema.
"""

from __future__ import annotations

import logging
from typing import Dict, Tuple

import pandas as pd
from psycopg2.extras import execute_values
from sqlalchemy.engine import Connection

from utils.stats import RunStats

logger = logging.getLogger("telecom_churn_etl.load_facts")

FACT_COLUMNS = [
    "customer_sk",
    "customer_id",
    "geography_id",
    "partner_id",
    "registration_date_id",
    "snapshot_date_id",
    "calls_made",
    "sms_sent",
    "data_used",
    "churn",
    "tenure_months",
    "calls_per_month",
    "data_per_month",
    "sms_per_month",
    "data_per_call",
    "sms_to_call_ratio",
    "age_x_dependents",
    "estimated_salary_log",
    "usage_score",
    "is_low_engagement",
    "low_usage_high_tenure",
]


def _chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def build_fact_rows(
    df: pd.DataFrame,
    customer_sk_map: Dict[int, int],
    geography_id_map: Dict[Tuple[str, str, str], int],
    partner_id_map: Dict[str, int],
    stats: RunStats,
) -> pd.DataFrame:
    """
    Attach resolved surrogate keys to the transformed dataframe and drop
    any row that cannot be fully resolved against a dimension.

    Returns
    -------
    pd.DataFrame
        Rows ready to load into fact_usage, with customer_sk, geography_id,
        and partner_id columns populated.
    """
    df = df.copy()

    df["customer_sk"] = df["customer_id"].map(customer_sk_map)
    df["geography_id"] = df.apply(
        lambda r: geography_id_map.get((r["pincode"], r["city"], r["state"])), axis=1
    )
    df["partner_id"] = df["telecom_partner"].map(partner_id_map)

    unresolved_mask = (
        df["customer_sk"].isna() | df["geography_id"].isna() | df["partner_id"].isna()
    )
    n_unresolved = int(unresolved_mask.sum())
    if n_unresolved:
        sample_ids = df.loc[unresolved_mask, "customer_id"].head(10).tolist()
        msg = (
            f"Dropping {n_unresolved} row(s) from fact_usage load because a dimension "
            f"key could not be resolved (sample customer_ids: {sample_ids})."
        )
        logger.error(msg)
        stats.add_error(msg)
        df = df[~unresolved_mask].copy()

    df["customer_sk"] = df["customer_sk"].astype("int64")
    df["geography_id"] = df["geography_id"].astype("int64")
    df["partner_id"] = df["partner_id"].astype("int64")

    return df


def load_fact_usage(
    conn: Connection, df: pd.DataFrame, schema: str, batch_size: int, stats: RunStats
) -> int:
    """
    Bulk-load ``fact_usage`` for every row in ``df`` (already resolved via
    ``build_fact_rows``).

    Returns
    -------
    int
        Number of rows inserted.
    """
    if df.empty:
        logger.warning("No rows to load into fact_usage — skipping.")
        return 0

    cursor = conn.connection.cursor()

    # --- Idempotent replace: clear any prior rows for this exact snapshot
    #     and set of customers before inserting fresh ones. ---
    snapshot_date_ids = df["snapshot_date_id"].unique().tolist()
    customer_ids = df["customer_id"].unique().tolist()

    for snap_batch in _chunks(snapshot_date_ids, batch_size):
        cursor.execute(
            f"""
            DELETE FROM {schema}.fact_usage
            WHERE snapshot_date_id = ANY(%s)
              AND customer_id = ANY(%s);
            """,
            (snap_batch, customer_ids),
        )
        if cursor.rowcount:
            logger.info(
                "fact_usage: removed %s pre-existing row(s) for snapshot_date_id(s) %s "
                "to keep the reload idempotent.",
                cursor.rowcount,
                snap_batch,
            )

    rows = list(df[FACT_COLUMNS].itertuples(index=False, name=None))

    insert_sql = f"""
        INSERT INTO {schema}.fact_usage (
            customer_sk, customer_id, geography_id, partner_id,
            registration_date_id, snapshot_date_id,
            calls_made, sms_sent, data_used, churn,
            tenure_months, calls_per_month, data_per_month, sms_per_month,
            data_per_call, sms_to_call_ratio, age_x_dependents,
            estimated_salary_log, usage_score,
            is_low_engagement, low_usage_high_tenure
        ) VALUES %s;
    """

    total_inserted = 0
    for batch in _chunks(rows, batch_size):
        execute_values(cursor, insert_sql, batch, page_size=batch_size)
        total_inserted += len(batch)
        logger.debug("fact_usage: inserted batch of %s rows (running total: %s).", len(batch), total_inserted)

    stats.fact_rows_inserted = total_inserted
    logger.info("fact_usage: inserted %s row(s) total.", total_inserted)
    return total_inserted
