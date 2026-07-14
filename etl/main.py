#!/usr/bin/env python3
"""
main.py
=======
Entry point for the Telecom Churn ETL pipeline.

Pipeline stages (per project spec)
------------------------------------
Read CSV -> Validate -> Clean -> Transform -> Load Dimension Tables ->
Load Fact Table -> Validate Database -> Log Results

Usage
-----
    python main.py

Configuration is entirely environment-driven — see .env.example.

Exit codes
----------
0  Success (pipeline completed and passed validation)
1  Configuration error (missing/invalid environment variables)
2  Extraction error (CSV missing/unreadable/malformed)
3  Pipeline/database error (transaction rolled back, nothing was
   committed to the warehouse)
4  Completed, but post-load validation found issues (data was loaded;
   review the validation report)
"""

from __future__ import annotations

import sys
import time
from datetime import datetime

from config.settings import ConfigError, load_settings
from etl import db
from etl.clean import clean_data
from etl.extract import ExtractionError, extract_csv
from etl.load_dimensions import (
    load_dim_customers,
    load_dim_geography,
    load_dim_telecom_partner,
)
from etl.load_facts import build_fact_rows, load_fact_usage
from etl.transform import transform_data
from etl.validate import validate_raw
from etl.validate_db import print_validation_summary, validate_database, write_run_report
from utils.logger import setup_logger
from utils.stats import RunStats


def run_pipeline() -> int:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    stats = RunStats()

    # ------------------------------------------------------------------
    # 0. Configuration & logging
    # ------------------------------------------------------------------
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"[CONFIG ERROR] {exc}", file=sys.stderr)
        return 1

    logger = setup_logger(settings.logs_dir, settings.log_level, run_id=run_id)
    logger.info("=" * 78)
    logger.info("TELECOM CHURN ETL PIPELINE — run_id=%s", run_id)
    logger.info("Target database : %s", settings.masked_url())
    logger.info("Source CSV      : %s", settings.csv_path)
    logger.info("Snapshot date   : %s", settings.snapshot_date)
    logger.info("=" * 78)

    pipeline_start = time.perf_counter()

    # ------------------------------------------------------------------
    # 1. EXTRACT
    # ------------------------------------------------------------------
    try:
        with stats.timed_stage("extract"):
            raw_df = extract_csv(settings.csv_path)
            stats.rows_extracted = len(raw_df)
    except ExtractionError as exc:
        logger.error("Extraction failed: %s", exc)
        return 2

    # ------------------------------------------------------------------
    # 2. VALIDATE (raw)
    # ------------------------------------------------------------------
    with stats.timed_stage("validate"):
        validated_df, validation_report = validate_raw(raw_df)
        stats.rows_after_validation = validation_report.valid_rows

    if validation_report.invalid_rows and not settings.drop_invalid_rows:
        logger.warning(
            "DROP_INVALID_ROWS is False: %s invalid row(s) will be repaired where "
            "possible during cleaning instead of being dropped outright.",
            validation_report.invalid_rows,
        )

    # ------------------------------------------------------------------
    # 3. CLEAN
    # ------------------------------------------------------------------
    with stats.timed_stage("clean"):
        clean_df = clean_data(validated_df, settings.drop_invalid_rows, stats)

    if clean_df.empty:
        logger.error("No rows remain after cleaning — aborting pipeline. Nothing was loaded.")
        return 3

    # ------------------------------------------------------------------
    # 4. TRANSFORM
    # ------------------------------------------------------------------
    try:
        with stats.timed_stage("transform"):
            transformed_df = transform_data(clean_df, settings.snapshot_date, stats)
    except ValueError as exc:
        logger.error("Transformation failed: %s", exc)
        return 3

    if transformed_df.empty:
        logger.error("No rows remain after transformation — aborting pipeline. Nothing was loaded.")
        return 3

    # ------------------------------------------------------------------
    # 5-6. LOAD DIMENSIONS + LOAD FACT (single transaction, all-or-nothing)
    # ------------------------------------------------------------------
    engine = db.build_engine(settings)
    try:
        db.verify_connection(engine)
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not connect to the database: %s", exc)
        return 3

    try:
        with stats.timed_stage("load"):
            with engine.begin() as conn:  # single transaction: commit at the end, rollback on any exception
                logger.info("Beginning database transaction for dimension + fact load.")

                partner_id_map = load_dim_telecom_partner(
                    conn, transformed_df, settings.db_schema, settings.bulk_insert_batch_size, stats
                )
                geography_id_map = load_dim_geography(
                    conn, transformed_df, settings.db_schema, settings.bulk_insert_batch_size, stats
                )
                customer_sk_map = load_dim_customers(
                    conn, transformed_df, settings.db_schema, settings.bulk_insert_batch_size, stats
                )

                fact_ready_df = build_fact_rows(
                    transformed_df, customer_sk_map, geography_id_map, partner_id_map, stats
                )

                if stats.errors:
                    # Unresolved dimension keys mean the data is not safe to load;
                    # raise to trigger a full rollback rather than a partial load.
                    raise RuntimeError(
                        f"Aborting load due to {len(stats.errors)} unresolved-dimension error(s): "
                        f"{stats.errors}"
                    )

                load_fact_usage(
                    conn, fact_ready_df, settings.db_schema, settings.bulk_insert_batch_size, stats
                )

                logger.info("Committing transaction...")
            logger.info("Transaction committed successfully.")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Load stage failed — transaction rolled back. Nothing was written. Error: %s", exc)
        stats.add_error(f"Load stage failed and was rolled back: {exc}")
        _finalize_and_report(settings, run_id, stats, validation_report, None)
        return 3

    # ------------------------------------------------------------------
    # 7. VALIDATE DATABASE (post-load, read-only)
    # ------------------------------------------------------------------
    snapshot_date_id = int(settings.snapshot_date.strftime("%Y%m%d"))
    with stats.timed_stage("validate_database"):
        with engine.connect() as conn:
            db_validation_report = validate_database(
                conn, settings.db_schema, snapshot_date_id, stats.rows_extracted
            )
    print_validation_summary(db_validation_report)

    # ------------------------------------------------------------------
    # 8. LOG RESULTS
    # ------------------------------------------------------------------
    total_elapsed = round(time.perf_counter() - pipeline_start, 2)
    _finalize_and_report(settings, run_id, stats, validation_report, db_validation_report)

    logger.info("Pipeline finished in %s seconds.", total_elapsed)
    logger.info(
        "Summary: extracted=%s, cleaned=%s, transformed=%s, fact_rows_loaded=%s, warnings=%s, errors=%s",
        stats.rows_extracted,
        stats.rows_after_cleaning,
        stats.rows_transformed,
        stats.fact_rows_inserted,
        len(stats.warnings),
        len(stats.errors),
    )

    if db_validation_report is not None and not db_validation_report.passed:
        logger.warning("Pipeline completed but post-load validation reported issues. Exit code 4.")
        return 4

    logger.info("Pipeline completed successfully with no validation issues.")
    return 0


def _finalize_and_report(settings, run_id, stats, validation_report, db_validation_report) -> None:
    """Always persist a JSON run report, even on failure paths."""
    from etl.validate_db import DbValidationReport  # local import to avoid unused-import warnings on failure path

    report_to_write = db_validation_report if db_validation_report is not None else DbValidationReport(
        passed=False, issues=["Pipeline aborted before database validation could run."]
    )
    write_run_report(settings.reports_dir, run_id, stats, validation_report, report_to_write)


if __name__ == "__main__":
    sys.exit(run_pipeline())
