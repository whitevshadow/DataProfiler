"""
Layer 6 — DuckDB Statistics Engine

DuckDB is the only execution engine for row statistics, cardinality, nulls,
duplicates, distributions, quantiles, entropy inputs, top values, and overlap
support metrics. Python only maps query results into profile models.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import duckdb

from .profiling_models import ColumnStatistics, PhysicalType


def quote_ident(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def quote_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int:
    if value is None:
        return 0
    return int(value)


def _clamp_ratio(value: float) -> float:
    return max(0.0, min(1.0, value))


def _empty_statistics(total_count: int = 0) -> ColumnStatistics:
    return ColumnStatistics(
        total_count=total_count,
        non_null_count=0,
        distinct_non_null_count=0,
        coverage_ratio=0.0,
        duplicate_ratio=0.0,
        null_count=total_count,
        null_ratio=1.0 if total_count else 0.0,
        distinct_count=0,
        uniqueness_ratio=0.0,
        cardinality_ratio=0.0,
        duplicate_count=0,
        entropy=0.0,
        entropy_normalized=0.0,
        top_values=[],
        frequency_distribution=[],
        duplicate_density=0.0,
    )


class DuckDBProfileContext:
    """Temporary DuckDB profiling session over a canonical source."""

    def __init__(self, canonical_dict: Dict[str, Any], source_path: Optional[str] = None):
        self.canonical_dict = canonical_dict
        self.source_path = source_path
        self.conn = duckdb.connect(database=":memory:")
        self.view_name = "table_view"
        self.column_map = {
            col.get("normalized_name"): col.get("original_name") or col.get("normalized_name")
            for col in canonical_dict.get("columns", [])
            if col.get("normalized_name")
        }
        self._load_source()

    def close(self) -> None:
        self.conn.close()

    def _load_source(self) -> None:
        source = self.canonical_dict.get("source") or {}
        fmt = str(source.get("format") or "").lower()
        path = source.get("path")

        if not path and self.source_path:
            path = str(Path(self.source_path))
        if not path:
            raise ValueError("DuckDB profiling requires canonical source.path")

        source_sql = self._source_sql(fmt, path, source)
        self.conn.execute(f"CREATE OR REPLACE VIEW {quote_ident(self.view_name)} AS SELECT * FROM {source_sql}")

    def _source_sql(self, fmt: str, path: str, source: Dict[str, Any]) -> str:
        literal_path = quote_literal(path)
        if fmt == "parquet":
            return f"read_parquet({literal_path})"
        if fmt in {"json", "ndjson"}:
            return f"read_json_auto({literal_path})"
        delimiter = source.get("delimiter")
        args = [literal_path]
        if delimiter:
            args.append(f"delim={quote_literal(delimiter)}")
        return f"read_csv_auto({', '.join(args)})"

    def source_column(self, normalized_name: str) -> str:
        return self.column_map.get(normalized_name) or normalized_name

    def get_sample_values(self, normalized_name: str, limit: int = 1000) -> List[Any]:
        source_col = self.source_column(normalized_name)
        sql = (
            f"SELECT {quote_ident(source_col)} AS value "
            f"FROM {quote_ident(self.view_name)} "
            f"LIMIT {int(limit)}"
        )
        return [row[0] for row in self.conn.execute(sql).fetchall()]

    def total_rows(self) -> int:
        row = self.conn.execute(f"SELECT COUNT(*) FROM {quote_ident(self.view_name)}").fetchone()
        return _safe_int(row[0] if row else 0)

    def compute_column_statistics(self, normalized_name: str, physical_type: PhysicalType) -> ColumnStatistics:
        source_col = self.source_column(normalized_name)
        col = quote_ident(source_col)
        view = quote_ident(self.view_name)

        counts = self.conn.execute(
            f"""
            SELECT
              COUNT(*) AS total_rows,
              COUNT({col}) AS non_null_count,
              COUNT(*) - COUNT({col}) AS null_count,
              COUNT(DISTINCT {col}) AS distinct_count,
              GREATEST(COUNT({col}) - COUNT(DISTINCT {col}), 0) AS duplicate_count,
              COUNT(DISTINCT {col}) * 1.0 / NULLIF(COUNT({col}), 0) AS uniqueness_ratio,
              COUNT({col}) * 1.0 / NULLIF(COUNT(*), 0) AS coverage_ratio,
              1.0 - (COUNT(DISTINCT {col}) * 1.0 / NULLIF(COUNT({col}), 0)) AS duplicate_ratio
            FROM {view}
            """
        ).fetchone()

        if not counts:
            return _empty_statistics()

        total_count = _safe_int(counts[0])
        non_null_count = _safe_int(counts[1])
        null_count = _safe_int(counts[2])
        distinct_count = _safe_int(counts[3])
        duplicate_count = _safe_int(counts[4])
        uniqueness_ratio = _clamp_ratio(_safe_float(counts[5]) or 0.0)
        coverage_ratio = _clamp_ratio(_safe_float(counts[6]) or 0.0)
        duplicate_ratio = _clamp_ratio(_safe_float(counts[7]) or 0.0)
        null_ratio = null_count / total_count if total_count else 0.0

        entropy, entropy_normalized = self._entropy(source_col, non_null_count)
        top_values = self._top_values(source_col)
        frequency_distribution = [
            {"value": value, "frequency": freq}
            for value, freq in top_values
        ]

        numeric_stats = self._numeric_stats(source_col, physical_type)
        string_stats = self._string_stats(source_col, physical_type)

        return ColumnStatistics(
            total_count=total_count,
            non_null_count=non_null_count,
            distinct_non_null_count=distinct_count,
            coverage_ratio=coverage_ratio,
            duplicate_ratio=duplicate_ratio,
            null_count=null_count,
            null_ratio=null_ratio,
            distinct_count=distinct_count,
            uniqueness_ratio=uniqueness_ratio,
            cardinality_ratio=_clamp_ratio(distinct_count / total_count) if total_count else 0.0,
            duplicate_count=duplicate_count,
            entropy=entropy,
            entropy_normalized=entropy_normalized,
            min_length=string_stats.get("min_length"),
            max_length=string_stats.get("max_length"),
            avg_length=string_stats.get("avg_length"),
            min_value=numeric_stats.get("min_value"),
            max_value=numeric_stats.get("max_value"),
            mean=numeric_stats.get("mean"),
            median=numeric_stats.get("median"),
            std_dev=numeric_stats.get("std_dev"),
            variance=numeric_stats.get("variance"),
            quantiles=numeric_stats.get("quantiles"),
            skewness=numeric_stats.get("skewness"),
            kurtosis=numeric_stats.get("kurtosis"),
            top_values=top_values,
            frequency_distribution=frequency_distribution,
            duplicate_density=duplicate_ratio,
        )

    def _top_values(self, source_col: str) -> List[Tuple[str, int]]:
        col = quote_ident(source_col)
        view = quote_ident(self.view_name)
        counts = self.conn.execute(
            f"""
            SELECT
              COUNT({col}) AS non_null_count,
              COUNT(DISTINCT {col}) AS distinct_non_null_count
            FROM {view}
            """
        ).fetchone()
        non_null_count = _safe_int(counts[0] if counts else 0)
        distinct_count = _safe_int(counts[1] if counts else 0)
        if non_null_count > 5_000_000 or distinct_count > 10_000:
            return []
        rows = self.conn.execute(
            f"""
            SELECT CAST({col} AS VARCHAR) AS value, COUNT(*) AS freq
            FROM {view}
            WHERE {col} IS NOT NULL
            GROUP BY {col}
            ORDER BY freq DESC, value ASC
            LIMIT 10
            """
        ).fetchall()
        return [(str(value), int(freq)) for value, freq in rows]

    def _entropy(self, source_col: str, non_null_count: int) -> tuple[float, float]:
        if non_null_count <= 0:
            return 0.0, 0.0
        col = quote_ident(source_col)
        view = quote_ident(self.view_name)
        entropy = self.conn.execute(
            f"""
            WITH freq AS (
              SELECT COUNT(*) AS freq
              FROM {view}
              WHERE {col} IS NOT NULL
              GROUP BY {col}
            )
            SELECT -SUM((freq * 1.0 / ?) * (ln(freq * 1.0 / ?) / ln(2)))
            FROM freq
            """,
            [non_null_count, non_null_count],
        ).fetchone()[0]
        entropy = _safe_float(entropy) or 0.0
        max_entropy = self.conn.execute("SELECT ln(NULLIF(?, 0)) / ln(2)", [non_null_count]).fetchone()[0]
        max_entropy = _safe_float(max_entropy) or 0.0
        normalized = entropy / max_entropy if max_entropy > 0 else 0.0
        return entropy, max(0.0, min(1.0, normalized))

    def _numeric_stats(self, source_col: str, physical_type: PhysicalType) -> Dict[str, Any]:
        if physical_type not in {PhysicalType.INTEGER, PhysicalType.FLOAT, PhysicalType.DECIMAL}:
            return {}
        col = f"TRY_CAST({quote_ident(source_col)} AS DOUBLE)"
        view = quote_ident(self.view_name)
        row = self.conn.execute(
            f"""
            SELECT
              MIN({col}),
              MAX({col}),
              AVG({col}),
              MEDIAN({col}),
              STDDEV({col}),
              VAR_SAMP({col}),
              QUANTILE_CONT({col}, 0.25),
              QUANTILE_CONT({col}, 0.50),
              QUANTILE_CONT({col}, 0.75),
              QUANTILE_CONT({col}, 0.90),
              QUANTILE_CONT({col}, 0.99),
              SKEWNESS({col}),
              KURTOSIS({col})
            FROM {view}
            """
        ).fetchone()
        if not row:
            return {}
        if all(value is None for value in row[:11]):
            return {}
        return {
            "min_value": _safe_float(row[0]),
            "max_value": _safe_float(row[1]),
            "mean": _safe_float(row[2]),
            "median": _safe_float(row[3]),
            "std_dev": _safe_float(row[4]),
            "variance": _safe_float(row[5]),
            "quantiles": {
                "p25": _safe_float(row[6]),
                "p50": _safe_float(row[7]),
                "p75": _safe_float(row[8]),
                "p90": _safe_float(row[9]),
                "p99": _safe_float(row[10]),
            },
            "skewness": _safe_float(row[11]),
            "kurtosis": _safe_float(row[12]),
        }

    def _string_stats(self, source_col: str, physical_type: PhysicalType) -> Dict[str, Any]:
        if physical_type not in {PhysicalType.STRING, PhysicalType.UNKNOWN}:
            return {}
        col = quote_ident(source_col)
        view = quote_ident(self.view_name)
        row = self.conn.execute(
            f"""
            SELECT
              MIN(LENGTH(CAST({col} AS VARCHAR))),
              MAX(LENGTH(CAST({col} AS VARCHAR))),
              AVG(LENGTH(CAST({col} AS VARCHAR)))
            FROM {view}
            WHERE {col} IS NOT NULL
            """
        ).fetchone()
        if not row:
            return {}
        return {
            "min_length": _safe_int(row[0]) if row[0] is not None else None,
            "max_length": _safe_int(row[1]) if row[1] is not None else None,
            "avg_length": _safe_float(row[2]),
        }

def compute_statistics(
    sample_values: List[Any],
    physical_type: PhysicalType,
    existing_stats: Optional[Dict[str, Any]] = None,
) -> ColumnStatistics:
    """Compatibility API: DuckDB still owns statistics for raw column calls."""
    conn = duckdb.connect(database=":memory:")
    try:
        conn.execute("CREATE TEMP TABLE value_table(value VARCHAR)")
        if sample_values:
            conn.executemany("INSERT INTO value_table VALUES (?)", [(None if v is None else str(v),) for v in sample_values])
        context = _ValueTableContext(conn)
        return context.compute_column_statistics("value", physical_type)
    finally:
        conn.close()


class _ValueTableContext(DuckDBProfileContext):
    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self.conn = conn
        self.view_name = "value_table"
        self.column_map = {"value": "value"}
