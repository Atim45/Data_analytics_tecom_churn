"""
etl/load_dimensions.py
=======================
LOAD DIMENSIONS stage: populates ``dim_telecom_partner``, ``dim_geography``,
and ``dim_customers`` (SCD Type-2), and returns the surrogate-key mappings
required to load ``fact_usage`` afterwards.

``dim_date`` is intentionally NOT loaded here — it is already fully
pre-populated (2015-01-01 to 2030-12-31) by ``01_schema.sql`` at DDL time.
The pipeline only resolves date surrogate keys against it (see
``etl.transform``).

Design notes
------------
* All dimension upserts use ``INSERT ... ON CONFLICT ... DO UPDATE ...
  RETURNING`` so a single round-trip both writes the row (if new/changed)
  and returns the surrogate key needed for the fact load — for both
  brand-new and pre-existing rows.
* Bulk operations use ``psycopg2.extras.execute_values`` for throughput,
  batched per ``settings.bulk_insert_batch_size``.
* ``dim_customers`` implements true SCD Type-2 semantics equivalent to the
  ``churn.sp_load_customer`` stored procedure, but set-based (via a
  temporary staging table) so it scales to hundreds of thousands of rows
  instead of looping row-by-row.
"""

from __future__ import annotations

import logging
from typing import Dict, Tuple

import pandas as pd
from psycopg2.extras import execute_values
from sqlalchemy import text
from sqlalchemy.engine import Connection

from etl.reference_data import get_partner_reference
from utils.stats import RunStats

logger = logging.getLogger("telecom_churn_etl.load_dimensions")


def _psycopg2_cursor(conn: Connection):
    """Get the underlying psycopg2 cursor from a SQLAlchemy Connection."""
    return conn.connection.cursor()


def _chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


# =============================================================================
# dim_telecom_partner
# =============================================================================
def load_dim_telecom_partner(
    conn: Connection, df: pd.DataFrame, schema: str, batch_size: int, stats: RunStats
) -> Dict[str, int]:
    """
    Upsert every distinct telecom_partner name found in the source data,
    enriched with static reference attributes (see ``reference_data``).

    Returns
    -------
    Dict[str, int]
        Mapping of partner_name -> partner_id.
    """
    unique_partners = sorted(df["telecom_partner"].dropna().unique().tolist())
    rows = []
    for name in unique_partners:
        ref = get_partner_reference(name)
        rows.append(
            (
                name,
                ref["partner_code"],
                ref["market_share"],
                ref["technology"],
                ref["hq_city"],
                ref["founded_year"],
                ref["is_active"],
            )
        )

    sql = f"""
        INSERT INTO {schema}.dim_telecom_partner (
            partner_name, partner_code, market_share, technology,
            hq_city, founded_year, is_active
        )
        VALUES %s
        ON CONFLICT (partner_name) DO UPDATE SET
            market_share = EXCLUDED.market_share,
            technology   = EXCLUDED.technology,
            hq_city      = EXCLUDED.hq_city,
            founded_year = EXCLUDED.founded_year,
            is_active    = EXCLUDED.is_active,
            updated_at   = NOW()
        RETURNING partner_id, partner_name;
    """

    cursor = _psycopg2_cursor(conn)
    mapping: Dict[str, int] = {}
    result_rows = execute_values(cursor, sql, rows, page_size=batch_size, fetch=True)
    for partner_id, partner_name in result_rows:
        mapping[partner_name] = partner_id

    stats.record_dimension_insert("dim_telecom_partner", len(mapping))
    logger.info("dim_telecom_partner: upserted %s partner(s).", len(mapping))
    return mapping


# =============================================================================
# dim_geography
# =============================================================================
def load_dim_geography(
    conn: Connection, df: pd.DataFrame, schema: str, batch_size: int, stats: RunStats
) -> Dict[Tuple[str, str, str], int]:
    """
    Upsert every distinct (pincode, city, state) combination.

    Returns
    -------
    Dict[Tuple[str, str, str], int]
        Mapping of (pincode, city, state) -> geography_id.
    """
    unique_geo = (
        df[["pincode", "city", "state", "region"]]
        .drop_duplicates(subset=["pincode", "city", "state"])
        .itertuples(index=False)
    )
    rows = [(pincode, city, state, region, "India") for pincode, city, state, region in unique_geo]

    sql = f"""
        INSERT INTO {schema}.dim_geography (
            pincode, city, state, region, country
        )
        VALUES %s
        ON CONFLICT (pincode, city, state) DO UPDATE SET
            region = EXCLUDED.region
        RETURNING geography_id, pincode, city, state;
    """

    cursor = _psycopg2_cursor(conn)
    mapping: Dict[Tuple[str, str, str], int] = {}
    for batch in _chunks(rows, batch_size):
        result_rows = execute_values(cursor, sql, batch, page_size=batch_size, fetch=True)
        for geography_id, pincode, city, state in result_rows:
            mapping[(pincode, city, state)] = geography_id

    stats.record_dimension_insert("dim_geography", len(mapping))
    logger.info("dim_geography: upserted %s unique location(s).", len(mapping))
    return mapping


# =============================================================================
# dim_customers (SCD Type-2)
# =============================================================================
def load_dim_customers(
    conn: Connection, df: pd.DataFrame, schema: str, batch_size: int, stats: RunStats
) -> Dict[int, int]:
    """
    Set-based SCD Type-2 upsert of dim_customers, equivalent to running
    ``churn.sp_load_customer`` for every customer, but batched via a
    staging table for performance on large datasets.

    Logic (mirrors sp_load_customer)
    ---------------------------------
    * Brand-new customer_id           -> INSERT a fresh current row.
    * Existing current row, attributes
      unchanged                       -> no-op (row is left as-is).
    * Existing current row, attributes
      changed                         -> expire the old row
                                          (is_current=FALSE,
                                          effective_end_date=yesterday),
                                          INSERT a new current row.

    Returns
    -------
    Dict[int, int]
        Mapping of customer_id -> customer_sk (current row) for every
        customer_id present in ``df``.
    """
    customer_cols = [
        "customer_id",
        "gender",
        "age",
        "num_dependents",
        "estimated_salary",
        "date_of_registration",
    ]
    unique_customers = df[customer_cols].drop_duplicates(subset=["customer_id"])

    cursor = _psycopg2_cursor(conn)

    # 1. Staging table: session-scoped temp table, dropped automatically at
    #    the end of the transaction/session.
    cursor.execute(
        """
        CREATE TEMPORARY TABLE stg_dim_customers (
            customer_id           BIGINT,
            gender                VARCHAR(10),
            age                   SMALLINT,
            num_dependents        SMALLINT,
            estimated_salary      NUMERIC(14, 2),
            date_of_registration  DATE
        ) ON COMMIT DROP;
        """
    )

    rows = list(unique_customers.itertuples(index=False, name=None))
    insert_sql = """
        INSERT INTO stg_dim_customers (
            customer_id, gender, age, num_dependents,
            estimated_salary, date_of_registration
        ) VALUES %s;
    """
    for batch in _chunks(rows, batch_size):
        execute_values(cursor, insert_sql, batch, page_size=batch_size)

    logger.info("Staged %s unique customer record(s) for SCD2 upsert.", len(rows))

    # 2. Expire current rows whose attributes changed.
    expire_sql = f"""
        UPDATE {schema}.dim_customers dc
        SET    effective_end_date = CURRENT_DATE - 1,
               is_current         = FALSE,
               updated_at         = NOW()
        FROM   stg_dim_customers stg
        WHERE  dc.customer_id = stg.customer_id
          AND  dc.is_current  = TRUE
          AND (
                dc.gender             IS DISTINCT FROM stg.gender
             OR dc.age                IS DISTINCT FROM stg.age
             OR dc.num_dependents     IS DISTINCT FROM stg.num_dependents
             OR dc.estimated_salary   IS DISTINCT FROM stg.estimated_salary
             OR dc.date_of_registration IS DISTINCT FROM stg.date_of_registration
          );
    """
    cursor.execute(expire_sql)
    n_expired = cursor.rowcount
    if n_expired:
        logger.info("dim_customers: expired %s changed row(s) (SCD2).", n_expired)
        stats.add_warning(f"dim_customers: {n_expired} existing customer row(s) changed attributes and were versioned (SCD2).")

    # 3. Insert a fresh current row for: brand-new customers AND customers
    #    whose current row was just expired above.
    insert_new_sql = f"""
        INSERT INTO {schema}.dim_customers (
            customer_id, gender, age, num_dependents,
            estimated_salary, date_of_registration,
            effective_start_date, effective_end_date, is_current
        )
        SELECT
            stg.customer_id, stg.gender, stg.age, stg.num_dependents,
            stg.estimated_salary, stg.date_of_registration,
            CURRENT_DATE, DATE '9999-12-31', TRUE
        FROM stg_dim_customers stg
        WHERE NOT EXISTS (
            SELECT 1 FROM {schema}.dim_customers dc
            WHERE dc.customer_id = stg.customer_id
              AND dc.is_current  = TRUE
        );
    """
    cursor.execute(insert_new_sql)
    n_inserted = cursor.rowcount
    logger.info("dim_customers: inserted %s new current row(s).", n_inserted)

    stats.record_dimension_insert("dim_customers", n_inserted)

    # 4. Build the customer_id -> customer_sk mapping for all customers in
    #    this load (new, updated, and unchanged alike).
    cursor.execute(
        f"""
        SELECT dc.customer_id, dc.customer_sk
        FROM   {schema}.dim_customers dc
        JOIN   stg_dim_customers stg ON stg.customer_id = dc.customer_id
        WHERE  dc.is_current = TRUE;
        """
    )
    mapping = {customer_id: customer_sk for customer_id, customer_sk in cursor.fetchall()}

    if len(mapping) != len(unique_customers):
        missing = set(unique_customers["customer_id"]) - set(mapping.keys())
        msg = (
            f"dim_customers mapping incomplete: {len(missing)} customer_id(s) have no "
            f"current row after upsert (sample: {list(missing)[:10]})."
        )
        logger.error(msg)
        stats.add_error(msg)

    return mapping
