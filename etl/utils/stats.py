"""
utils/stats.py
===============
A lightweight, in-memory run-statistics collector.

Every ETL stage records timings, row counts, warnings, and errors into a
single ``RunStats`` object which is dumped to a JSON report at the end of
the pipeline (see ``etl.validate_db.write_run_report``).
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, Iterator, List


@dataclass
class StageTiming:
    stage: str
    seconds: float


@dataclass
class RunStats:
    """Accumulates counters and messages across the whole pipeline run."""

    rows_extracted: int = 0
    rows_after_validation: int = 0
    rows_after_cleaning: int = 0
    rows_transformed: int = 0

    dimension_rows_inserted: Dict[str, int] = field(default_factory=dict)
    fact_rows_inserted: int = 0

    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    stage_timings: List[StageTiming] = field(default_factory=list)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def record_dimension_insert(self, table_name: str, row_count: int) -> None:
        self.dimension_rows_inserted[table_name] = (
            self.dimension_rows_inserted.get(table_name, 0) + row_count
        )

    @contextmanager
    def timed_stage(self, stage_name: str) -> Iterator[None]:
        """Context manager that records the wall-clock duration of a stage."""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self.stage_timings.append(StageTiming(stage=stage_name, seconds=round(elapsed, 3)))

    def total_seconds(self) -> float:
        return round(sum(t.seconds for t in self.stage_timings), 3)

    def to_dict(self) -> dict:
        return {
            "rows_extracted": self.rows_extracted,
            "rows_after_validation": self.rows_after_validation,
            "rows_after_cleaning": self.rows_after_cleaning,
            "rows_transformed": self.rows_transformed,
            "dimension_rows_inserted": self.dimension_rows_inserted,
            "fact_rows_inserted": self.fact_rows_inserted,
            "warning_count": len(self.warnings),
            "error_count": len(self.errors),
            "warnings": self.warnings,
            "errors": self.errors,
            "stage_timings_seconds": {t.stage: t.seconds for t in self.stage_timings},
            "total_seconds": self.total_seconds(),
        }
