"""
etl/validate_db.py
===================
POST-LOAD VALIDATION stage: runs a battery of read-only SQL checks against
the warehouse after loading to confirm the load is structurally sound, and
writes both a JSON report (machine readable) and a human-readable summary
to the console/log.

Checks performed
-----------------
* Row counts for every dimension and fact table.
* Duplicate natural-key checks (dim_customers current rows, dim_geography,
  dim_telecom_partner).
* Foreign-key orphan checks for fact_usage (belt-and-braces — the DB's own
  FK constraints already guarantee this at insert time, but an explicit
  check catches any drift from manual data edits between runs).
* NULL checks on NOT NULL business columns (defence in depth).
* Row-count reconciliation: source rows extracted vs. rows loaded into
  fact_usage for the snapshot just processed.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List

from sqlalchemy import text
from sqlalchemy.engine import Connection
from tabulate import tabulate

from utils.stats import RunStats

logger = logging.getLogger("telecom_churn_etl.validate_db")


@dataclass
class DbValidationReport:
    table_row_counts: dict = field(default_factory=dict)
    duplicate_key_findings: dict = field(default_factory=dict)
    orphan_fk_findings: dict = field(default_factory=dict)
    null_check_findings: dict = field(default_factory=dict)
    reconciliation: dict = field(default_factory=dict)
    passed: bool = True
    issues: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "table_row_counts": self.table_row_counts,
            "duplicate_key_findings": self.duplicate_key_findings,
            "orphan_fk_findings": self.orphan_fk_findings,
            "null_check_findings": self.null_check_findings,
            "reconciliation": self.reconciliation,
            "passed": self.passed,
            "issues": self.issues,
        }


def _scalar(conn: Connection, sql: str, **params) -> int:
    result = conn.execute(text(sql), params).scalar()
    return int(result) if result is not None else 0


def validate_database(
    conn: Connection,
    schema: str,
    snapshot_date_id: int,
    source_row_count: int,
) -> DbValidationReport:
    """Run all post-load checks and return a structured report."""
    report = DbValidationReport()

    # --- Row counts ---
    for table in [
        "dim_customers",
        "dim_geography",
        "dim_telecom_partner",
        "dim_date",
        "fact_usage",
        "fact_churn_predictions",
    ]:
        report.table_row_counts[table] = _scalar(conn, f"SELECT COUNT(*) FROM {schema}.{table}")

    report.table_row_counts["dim_customers_current"] = _scalar(
        conn, f"SELECT COUNT(*) FROM {schema}.dim_customers WHERE is_current = TRUE"
    )
    report.table_row_counts["fact_usage_current_snapshot"] = _scalar(
        conn,
        f"SELECT COUNT(*) FROM {schema}.fact_usage WHERE snapshot_date_id = :snap",
        snap=snapshot_date_id,
    )

    # --- Duplicate key checks ---
    dup_customers = _scalar(
        conn,
        f"""
        SELECT COUNT(*) FROM (
            SELECT customer_id FROM {schema}.dim_customers
            WHERE is_current = TRUE
            GROUP BY customer_id HAVING COUNT(*) > 1
        ) d;
        """,
    )
    dup_geography = _scalar(
        conn,
        f"""
        SELECT COUNT(*) FROM (
            SELECT pincode, city, state FROM {schema}.dim_geography
            GROUP BY pincode, city, state HAVING COUNT(*) > 1
        ) d;
        """,
    )
    dup_partner = _scalar(
        conn,
        f"""
        SELECT COUNT(*) FROM (
            SELECT partner_name FROM {schema}.dim_telecom_partner
            GROUP BY partner_name HAVING COUNT(*) > 1
        ) d;
        """,
    )
    report.duplicate_key_findings = {
        "dim_customers_duplicate_current_customer_id": dup_customers,
        "dim_geography_duplicate_pincode_city_state": dup_geography,
        "dim_telecom_partner_duplicate_name": dup_partner,
    }
    if dup_customers or dup_geography or dup_partner:
        report.passed = False
        report.issues.append("Duplicate natural keys detected in one or more dimension tables.")

    # --- Orphan FK checks (defence in depth; DB constraints already block these) ---
    orphan_customer = _scalar(
        conn,
        f"""
        SELECT COUNT(*) FROM {schema}.fact_usage fu
        LEFT JOIN {schema}.dim_customers dc ON dc.customer_sk = fu.customer_sk
        WHERE dc.customer_sk IS NULL;
        """,
    )
    orphan_geography = _scalar(
        conn,
        f"""
        SELECT COUNT(*) FROM {schema}.fact_usage fu
        LEFT JOIN {schema}.dim_geography dg ON dg.geography_id = fu.geography_id
        WHERE dg.geography_id IS NULL;
        """,
    )
    orphan_partner = _scalar(
        conn,
        f"""
        SELECT COUNT(*) FROM {schema}.fact_usage fu
        LEFT JOIN {schema}.dim_telecom_partner tp ON tp.partner_id = fu.partner_id
        WHERE tp.partner_id IS NULL;
        """,
    )
    orphan_reg_date = _scalar(
        conn,
        f"""
        SELECT COUNT(*) FROM {schema}.fact_usage fu
        LEFT JOIN {schema}.dim_date dd ON dd.date_id = fu.registration_date_id
        WHERE dd.date_id IS NULL;
        """,
    )
    orphan_snap_date = _scalar(
        conn,
        f"""
        SELECT COUNT(*) FROM {schema}.fact_usage fu
        LEFT JOIN {schema}.dim_date dd ON dd.date_id = fu.snapshot_date_id
        WHERE dd.date_id IS NULL;
        """,
    )
    report.orphan_fk_findings = {
        "fact_usage_orphan_customer_sk": orphan_customer,
        "fact_usage_orphan_geography_id": orphan_geography,
        "fact_usage_orphan_partner_id": orphan_partner,
        "fact_usage_orphan_registration_date_id": orphan_reg_date,
        "fact_usage_orphan_snapshot_date_id": orphan_snap_date,
    }
    if any(report.orphan_fk_findings.values()):
        report.passed = False
        report.issues.append("Orphaned foreign keys detected in fact_usage.")

    # --- NULL checks on critical NOT NULL business columns ---
    null_checks = {
        "dim_customers.gender": f"SELECT COUNT(*) FROM {schema}.dim_customers WHERE gender IS NULL",
        "dim_customers.date_of_registration": f"SELECT COUNT(*) FROM {schema}.dim_customers WHERE date_of_registration IS NULL",
        "fact_usage.churn": f"SELECT COUNT(*) FROM {schema}.fact_usage WHERE churn IS NULL",
        "fact_usage.usage_score": f"SELECT COUNT(*) FROM {schema}.fact_usage WHERE usage_score IS NULL",
    }
    for label, sql in null_checks.items():
        report.null_check_findings[label] = _scalar(conn, sql)
    if any(report.null_check_findings.values()):
        report.passed = False
        report.issues.append("Unexpected NULLs found in NOT NULL business columns.")

    # --- Reconciliation: extracted source rows vs. loaded fact rows ---
    loaded_for_snapshot = report.table_row_counts["fact_usage_current_snapshot"]
    report.reconciliation = {
        "source_rows_extracted": source_row_count,
        "fact_rows_loaded_for_snapshot": loaded_for_snapshot,
        "difference": source_row_count - loaded_for_snapshot,
    }
    if loaded_for_snapshot > source_row_count:
        report.passed = False
        report.issues.append(
            "More fact_usage rows loaded than source rows extracted — investigate duplicate loads."
        )

    return report


def print_validation_summary(report: DbValidationReport) -> None:
    """Pretty-print the validation report to the log/console."""
    logger.info("=" * 78)
    logger.info("DATABASE VALIDATION SUMMARY")
    logger.info("=" * 78)

    table_rows = [[k, v] for k, v in report.table_row_counts.items()]
    logger.info("\n%s", tabulate(table_rows, headers=["Table", "Row Count"], tablefmt="github"))

    dup_rows = [[k, v] for k, v in report.duplicate_key_findings.items()]
    logger.info("\n%s", tabulate(dup_rows, headers=["Duplicate Key Check", "Count"], tablefmt="github"))

    orphan_rows = [[k, v] for k, v in report.orphan_fk_findings.items()]
    logger.info("\n%s", tabulate(orphan_rows, headers=["Orphan FK Check", "Count"], tablefmt="github"))

    null_rows = [[k, v] for k, v in report.null_check_findings.items()]
    logger.info("\n%s", tabulate(null_rows, headers=["NULL Check", "Count"], tablefmt="github"))

    recon_rows = [[k, v] for k, v in report.reconciliation.items()]
    logger.info("\n%s", tabulate(recon_rows, headers=["Reconciliation", "Value"], tablefmt="github"))

    status = "PASSED" if report.passed else "FAILED"
    logger.info("Overall validation status: %s", status)
    if report.issues:
        for issue in report.issues:
            logger.warning("Validation issue: %s", issue)
    logger.info("=" * 78)


def write_run_report(
    reports_dir: Path,
    run_id: str,
    run_stats: RunStats,
    validation_report,
    db_validation_report: DbValidationReport,
) -> Path:
    """Write the full end-to-end run report (stats + validations) to JSON."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"etl_report_{run_id}.json"

    payload = {
        "run_id": run_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_stats": run_stats.to_dict(),
        "raw_validation": validation_report.to_dict(),
        "database_validation": db_validation_report.to_dict(),
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    logger.info("Full ETL run report written to: %s", report_path)
    return report_path
