"""
Layer 5 — Format Engines

Converts raw data sources into Canonical Table IR (Intermediate Representation).

Design Rule: Format engines ONLY parse, NEVER profile.
This prevents duplicated logic and keeps parsing separate from analysis.

Supported Formats:
- CSV/TSV
- JSON/NDJSON
- Excel (XLSX/XLS)
- Parquet
- SQLite/DuckDB
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Iterator
from enum import Enum

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical Table IR
# ---------------------------------------------------------------------------

class ColumnType(Enum):
    """Data types in canonical table."""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    TIME = "time"
    BINARY = "binary"
    NULL = "null"
    UNKNOWN = "unknown"


@dataclass
class Column:
    """Column metadata in canonical table."""
    name: str
    index: int
    data_type: ColumnType = ColumnType.UNKNOWN
    
    # CRITICAL: Use observed_nullable (not schema guarantee)
    observed_nullable: bool = True
    
    # Normalized names for lineage
    original_name: Optional[str] = None
    normalized_name: Optional[str] = None
    
    # Sample values (RAW ONLY - no statistics)
    # V2.0.0: CanonicalTable stores ONLY raw samples, NOT profiling outputs
    sample_values: Optional[List[Any]] = None


@dataclass
class CanonicalTable:
    """
    Canonical Table IR - Standardized representation of tabular data.
    
    Format engines produce this. Profiler consumes this.
    Keeps parsing separate from analysis.
    """
    # Metadata
    source_path: str
    source_type: str  # "csv", "parquet", "json", etc.
    
    # Schema
    columns: List[Column]
    column_count: int
    
    # Data access
    row_count: Optional[int] = None  # None if unknown (streaming)
    rows: Optional[List[List[Any]]] = None  # For small datasets
    
    # Iterator for large datasets (avoids loading everything into memory)
    _row_iterator: Optional[Iterator[List[Any]]] = field(default=None, repr=False)
    
    # Encoding & format info
    encoding: Optional[str] = None
    delimiter: Optional[str] = None  # CSV-specific
    compression: Optional[str] = None
    
    # Sampling info (from Layer 4)
    is_sample: bool = False
    sample_size: Optional[int] = None
    sampling_method: Optional[str] = None
    
    def iter_rows(self) -> Iterator[List[Any]]:
        """Iterate over rows. Works for both in-memory and streaming."""
        if self.rows is not None:
            yield from self.rows
        elif self._row_iterator is not None:
            yield from self._row_iterator
        else:
            return iter([])
    
    def get_column(self, name: str) -> Optional[Column]:
        """Get column by name."""
        for col in self.columns:
            if col.name == name:
                return col
        return None
    
    def get_column_names(self) -> List[str]:
        """Get list of column names."""
        return [col.name for col in self.columns]
    
    @staticmethod
    def normalize_column_name(name: str) -> str:
        """
        Normalize column name for execution consistency.
        
        Examples:
            "Customer ID" -> "customer_id"
            "First Name" -> "first_name"
            "Email-Address" -> "email_address"
            "Date/Time" -> "date_time"
        """
        import re
        # Convert to lowercase
        normalized = name.lower()
        # Replace spaces, hyphens, dots, slashes with underscore
        normalized = re.sub(r'[\s\-\./]+', '_', normalized)
        # Remove special characters
        normalized = re.sub(r'[^\w]', '', normalized)
        # Remove leading/trailing underscores
        normalized = normalized.strip('_')
        # Collapse multiple underscores
        normalized = re.sub(r'_+', '_', normalized)
        return normalized
    
    def compute_lightweight_statistics(self):
        """
        V2.0.0: Prepare canonical table metadata.
        
        CanonicalTable is ONLY responsible for:
        - Physical type detection (INTEGER, STRING, FLOAT, etc.)
        - Storing RAW sample values
        - Column name normalization
        - Null observation
        
        NOT responsible for:
        - Statistics (entropy, uniqueness, cardinality) → Layer 6
        - Semantic type inference → Layer 6
        - Quality analysis → Layer 6
        """
        if not self.rows:
            return
        
        for col in self.columns:
            col_idx = col.index
            
            # Extract column values
            values = [row[col_idx] for row in self.rows if col_idx < len(row)]
            
            # Count nulls (observed nullability only)
            null_count = sum(1 for v in values if v is None or v == '' or v == 'null' or v == 'NULL')
            col.observed_nullable = null_count > 0
            
            # Non-null values
            non_null_values = [v for v in values if v is not None and v != '' and v != 'null' and v != 'NULL']
            
            # Store ALL sample values (cap at 100 for JSON size)
            col.sample_values = list(set(non_null_values))[:100]
            
            # PHYSICAL TYPE INFERENCE ONLY
            col.data_type = self._infer_physical_type(non_null_values)
            
            # Store original and normalized names
            if not col.original_name:
                col.original_name = col.name
            if not col.normalized_name:
                col.normalized_name = self.normalize_column_name(col.name)
    
    @staticmethod
    def _infer_physical_type(values: List[Any]) -> ColumnType:
        """
        Infer physical type from sample values.
        
        Returns: INTEGER, FLOAT, STRING, DATETIME, BOOLEAN, etc.
        """
        if not values:
            return ColumnType.UNKNOWN
        
        # Sample up to 100 values for type inference
        sample = values[:100]
        
        # Check if all are integers
        int_count = 0
        float_count = 0
        bool_count = 0
        date_count = 0
        datetime_count = 0
        
        for v in sample:
            v_str = str(v).strip()
            
            # Boolean check
            if v_str.lower() in ('true', 'false', 'yes', 'no', '0', '1', 't', 'f'):
                bool_count += 1
            
            # Integer check
            try:
                int(v_str)
                int_count += 1
                continue
            except (ValueError, TypeError):
                pass
            
            # Float check
            try:
                float(v_str)
                float_count += 1
                continue
            except (ValueError, TypeError):
                pass
            
            # Datetime check (various formats)
            import re
            # ISO or day-first format: 2013-01-01 00:00:00 / 01-01-2013 00:00:00
            year_first_datetime = r'\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{1,2}:\d{1,2}'
            day_first_datetime = r'\d{1,2}[-/]\d{1,2}[-/]\d{4}[ T]\d{1,2}:\d{1,2}:\d{1,2}'
            if re.match(year_first_datetime, v_str) or re.match(day_first_datetime, v_str):
                datetime_count += 1
                continue
            # Date only: 2013-01-01 / 01-01-2013
            year_first_date = r'\d{4}[-/]\d{1,2}[-/]\d{1,2}$'
            day_first_date = r'\d{1,2}[-/]\d{1,2}[-/]\d{4}$'
            if re.match(year_first_date, v_str) or re.match(day_first_date, v_str):
                date_count += 1
                continue
        
        total = len(sample)
        threshold = 0.8  # 80% must match for type assignment
        
        # Boolean (highest priority for small sets)
        if bool_count >= total * threshold and total < 10:
            return ColumnType.BOOLEAN
        
        # Integer
        if int_count >= total * threshold:
            return ColumnType.INTEGER
        
        # Float
        if (int_count + float_count) >= total * threshold:
            return ColumnType.FLOAT
        
        # DateTime
        if datetime_count >= total * threshold:
            return ColumnType.DATETIME
        
        # Date
        if date_count >= total * threshold:
            return ColumnType.DATE
        
        # Default to STRING
        return ColumnType.STRING
    
    # V2.0.0: Removed _try_parse_number, _compute_entropy, _infer_semantic_type
    # These are profiling responsibilities moved to Layer 6
    
    def to_canonical_json(self, table_id: Optional[str] = None, table_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Export to Canonical JSON v2.0.0 format.
        
        V2.0.0 CHANGES:
        - Added schema_version, artifact_type
        - Added lineage block (created_at, engine, engine_version)
        - Added sampling block (strategy, deterministic_seed)
        - REMOVED statistics from columns (moved to Layer 6)
        - REMOVED semantic_type from columns (moved to Layer 6)
        - Keep ONLY: schema, raw samples, metadata
        
        This is the reusable intermediate artifact that enables:
        - Caching (avoid reparsing)
        - Lineage tracking
        - Deterministic replay
        - Input for downstream profiling layers
        
        Design: Lightweight, NOT the full dataset.
        """
        import os
        import hashlib
        from pathlib import Path
        from datetime import datetime
        
        # Generate table ID if not provided
        if not table_id:
            table_id = f"tbl_{hash(self.source_path) & 0xFFFFFF:06x}"
        
        # Derive table name from source if not provided
        if not table_name:
            table_name = Path(self.source_path).stem
        
        # Get file size
        size_mb = None
        if os.path.exists(self.source_path):
            size_bytes = os.path.getsize(self.source_path)
            size_mb = size_bytes / (1024 * 1024)
        
        # Deterministic seed for reproducibility
        sampling_strategy = self.sampling_method or "head"
        seed_input = f"{table_id}+{sampling_strategy}".encode('utf-8')
        deterministic_seed = hashlib.sha256(seed_input).hexdigest()[:16]
        
        # Build canonical JSON v2.0.0
        canonical = {
            # V2.0.0: Schema version
            "schema_version": "2.0.0",
            "artifact_type": "canonical_table",
            
            "table_id": table_id,
            "table_name": table_name,
            
            "source": {
                "source_type": "file",
                "format": self.source_type,
                "path": self.source_path,
                "size_mb": round(size_mb, 2) if size_mb else None,
                "encoding": self.encoding,
                "delimiter": self.delimiter,
                "compression": self.compression,
            },
            
            # V2.0.0: Lineage metadata
            "lineage": {
                "created_at": datetime.now().isoformat() + "Z",
                "engine": self.source_type + "_engine",
                "engine_version": "2.0.0",
            },
            
            # V2.0.0: Sampling metadata
            "sampling": {
                "strategy": sampling_strategy,
                "sample_size": self.row_count,
                "total_rows_estimate": None,  # Unknown for samples
                "is_sample": self.is_sample,
                "deterministic_seed": deterministic_seed,
            },
            
            "schema": {
                "column_count": self.column_count,
            },
            
            "columns": []
        }
        
        # Build column metadata (v2.0.0: RAW ONLY, no statistics)
        for col in self.columns:
            col_data = {
                "column_id": f"col_{col.index:03d}",
                "original_name": col.original_name or col.name,
                "normalized_name": col.normalized_name or self.normalize_column_name(col.name),
                "position": col.index,
                "physical_type": col.data_type.value.upper(),
                "observed_nullable": col.observed_nullable,
            }
            
            # Add ALL sample values (not truncated)
            if col.sample_values:
                col_data["sample_values"] = [str(v) for v in col.sample_values]
            
            canonical["columns"].append(col_data)
        
        return canonical
    
    def save_canonical_json(self, output_path: Path, table_id: Optional[str] = None, table_name: Optional[str] = None):
        """
        Save Canonical JSON to disk.
        
        This creates the reusable intermediate artifact.
        """
        import json
        
        # Compute lightweight statistics if not already done
        self.compute_lightweight_statistics()
        
        # Generate canonical JSON
        canonical = self.to_canonical_json(table_id, table_name)
        
        # Write to disk
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(canonical, f, indent=2, ensure_ascii=False)
        
        log.info(f"Saved Canonical JSON: {output_path}")
        return output_path


# ---------------------------------------------------------------------------
# Base Format Engine
# ---------------------------------------------------------------------------

class FormatEngine(ABC):
    """
    Abstract base class for format-specific parsers.
    
    Responsibility: Parse raw data → Canonical Table IR
    NOT responsible for: Profiling, statistics, type inference (that's Layer 6)
    """
    
    @abstractmethod
    def can_handle(self, file_path: Path, file_format: str) -> bool:
        """Check if this engine can handle the given file."""
        pass
    
    @abstractmethod
    def parse(
        self,
        file_path: Path,
        encoding: Optional[str] = None,
        compression: Optional[str] = None,
        sample_size: Optional[int] = None,
        **kwargs
    ) -> CanonicalTable:
        """
        Parse file into Canonical Table IR.
        
        Args:
            file_path: Path to file
            encoding: Character encoding
            compression: Compression format
            sample_size: Max rows to read (None = all)
            **kwargs: Format-specific options
            
        Returns:
            CanonicalTable with parsed data
        """
        pass


# ---------------------------------------------------------------------------
# CSV Engine
# ---------------------------------------------------------------------------

class CSVEngine(FormatEngine):
    """Parse CSV/TSV files."""
    
    def can_handle(self, file_path: Path, file_format: str) -> bool:
        return file_format in ("csv", "tsv", "txt")
    
    def parse(
        self,
        file_path: Path,
        encoding: Optional[str] = None,
        compression: Optional[str] = None,
        sample_size: Optional[int] = None,
        delimiter: Optional[str] = None,
        **kwargs
    ) -> CanonicalTable:
        """Parse CSV file."""
        import csv
        
        encoding = encoding or "utf-8"
        
        # Auto-detect delimiter if not provided
        if delimiter is None:
            delimiter = self._detect_delimiter(file_path, encoding)
        
        rows = []
        columns = []
        
        # Handle compression
        if compression == "gz":
            import gzip
            open_func = gzip.open
        elif compression == "zip":
            import zipfile
            # For zip, we need special handling
            with zipfile.ZipFile(file_path) as zf:
                first_file = zf.namelist()[0]
                with zf.open(first_file) as f:
                    return self._parse_csv_stream(f, encoding, delimiter, sample_size, file_path)
        else:
            open_func = open
        
        with open_func(file_path, 'rt', encoding=encoding, errors='replace') as f:
            reader = csv.reader(f, delimiter=delimiter)
            
            # Read header
            try:
                header = next(reader)
                columns = [
                    Column(name=name, index=i)
                    for i, name in enumerate(header)
                ]
            except StopIteration:
                raise ValueError(f"Empty CSV file: {file_path}")
            
            # Read data rows
            for i, row in enumerate(reader):
                if sample_size and i >= sample_size:
                    break
                rows.append(row)
        
        return CanonicalTable(
            source_path=str(file_path),
            source_type="csv",
            columns=columns,
            column_count=len(columns),
            row_count=len(rows),
            rows=rows,
            encoding=encoding,
            delimiter=delimiter,
            compression=compression,
            is_sample=sample_size is not None,
            sample_size=len(rows) if sample_size else None,
        )
    
    def _parse_csv_stream(self, stream, encoding, delimiter, sample_size, file_path):
        """Parse CSV from a binary stream."""
        import csv
        import io
        
        text_stream = io.TextIOWrapper(stream, encoding=encoding, errors='replace')
        reader = csv.reader(text_stream, delimiter=delimiter)
        
        header = next(reader)
        columns = [Column(name=name, index=i) for i, name in enumerate(header)]
        
        rows = []
        for i, row in enumerate(reader):
            if sample_size and i >= sample_size:
                break
            rows.append(row)
        
        return CanonicalTable(
            source_path=str(file_path),
            source_type="csv",
            columns=columns,
            column_count=len(columns),
            row_count=len(rows),
            rows=rows,
            encoding=encoding,
            delimiter=delimiter,
            is_sample=sample_size is not None,
            sample_size=len(rows) if sample_size else None,
        )
    
    def _detect_delimiter(self, file_path: Path, encoding: str) -> str:
        """Auto-detect CSV delimiter."""
        import csv
        
        with open(file_path, 'r', encoding=encoding, errors='replace') as f:
            sample = f.read(8192)
            try:
                sniffer = csv.Sniffer()
                dialect = sniffer.sniff(sample, delimiters=',\t;|:')
                return dialect.delimiter
            except csv.Error:
                return ','  # Default to comma


# ---------------------------------------------------------------------------
# JSON Engine
# ---------------------------------------------------------------------------

class JSONEngine(FormatEngine):
    """Parse JSON/NDJSON files."""
    
    def can_handle(self, file_path: Path, file_format: str) -> bool:
        return file_format in ("json", "jsonl", "ndjson")
    
    def parse(
        self,
        file_path: Path,
        encoding: Optional[str] = None,
        compression: Optional[str] = None,
        sample_size: Optional[int] = None,
        **kwargs
    ) -> CanonicalTable:
        """Parse JSON file."""
        import json
        
        encoding = encoding or "utf-8"
        
        with open(file_path, 'r', encoding=encoding) as f:
            content = f.read()
        
        # Try to parse as JSON array or NDJSON
        try:
            data = json.loads(content)
            if isinstance(data, list):
                return self._parse_json_array(data, file_path, sample_size)
            elif isinstance(data, dict):
                # Single object - wrap in array
                return self._parse_json_array([data], file_path, sample_size)
        except json.JSONDecodeError:
            # Try NDJSON (newline-delimited)
            return self._parse_ndjson(file_path, encoding, sample_size)
    
    def _parse_json_array(self, data: List[Dict], file_path: Path, sample_size: Optional[int]) -> CanonicalTable:
        """Parse JSON array into canonical table."""
        if not data:
            raise ValueError(f"Empty JSON array: {file_path}")
        
        # Sample if needed
        if sample_size and len(data) > sample_size:
            data = data[:sample_size]
        
        # Extract column names from first object
        first_obj = data[0]
        column_names = list(first_obj.keys())
        columns = [Column(name=name, index=i) for i, name in enumerate(column_names)]
        
        # Convert to rows
        rows = []
        for obj in data:
            row = [obj.get(col, None) for col in column_names]
            rows.append(row)
        
        return CanonicalTable(
            source_path=str(file_path),
            source_type="json",
            columns=columns,
            column_count=len(columns),
            row_count=len(rows),
            rows=rows,
            is_sample=sample_size is not None,
            sample_size=len(rows) if sample_size else None,
        )
    
    def _parse_ndjson(self, file_path: Path, encoding: str, sample_size: Optional[int]) -> CanonicalTable:
        """Parse NDJSON (newline-delimited JSON)."""
        import json
        
        rows_data = []
        with open(file_path, 'r', encoding=encoding) as f:
            for i, line in enumerate(f):
                if sample_size and i >= sample_size:
                    break
                if line.strip():
                    rows_data.append(json.loads(line))
        
        return self._parse_json_array(rows_data, file_path, None)


# ---------------------------------------------------------------------------
# Parquet Engine
# ---------------------------------------------------------------------------

class ParquetEngine(FormatEngine):
    """Parse Parquet files."""
    
    def can_handle(self, file_path: Path, file_format: str) -> bool:
        return file_format in ("parquet", "pq", "parq")
    
    def parse(
        self,
        file_path: Path,
        encoding: Optional[str] = None,
        compression: Optional[str] = None,
        sample_size: Optional[int] = None,
        **kwargs
    ) -> CanonicalTable:
        """Parse Parquet file using PyArrow."""
        try:
            import pyarrow.parquet as pq
        except ImportError:
            raise ImportError("pyarrow is required to read Parquet files: pip install pyarrow")
        
        # Read parquet file
        table = pq.read_table(file_path)
        
        # Sample if needed
        if sample_size and table.num_rows > sample_size:
            table = table.slice(0, sample_size)
        
        # Extract schema
        columns = [
            Column(name=field.name, index=i)
            for i, field in enumerate(table.schema)
        ]
        
        # Convert to list of lists
        rows = []
        for i in range(table.num_rows):
            row = [table.column(j)[i].as_py() for j in range(table.num_columns)]
            rows.append(row)
        
        return CanonicalTable(
            source_path=str(file_path),
            source_type="parquet",
            columns=columns,
            column_count=len(columns),
            row_count=len(rows),
            rows=rows,
            is_sample=sample_size is not None,
            sample_size=len(rows) if sample_size else None,
        )


# ---------------------------------------------------------------------------
# Excel Engine
# ---------------------------------------------------------------------------

class ExcelEngine(FormatEngine):
    """Parse Excel files (XLSX/XLS)."""
    
    def can_handle(self, file_path: Path, file_format: str) -> bool:
        return file_format in ("excel", "excel_xlsx", "excel_xls") or file_path.suffix.lower() in ('.xlsx', '.xls')
    
    def parse(
        self,
        file_path: Path,
        encoding: Optional[str] = None,
        compression: Optional[str] = None,
        sample_size: Optional[int] = None,
        sheet_name: Optional[str] = None,
        **kwargs
    ) -> CanonicalTable:
        """Parse Excel file using pandas."""
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas is required to read Excel files: pip install pandas openpyxl")
        
        # Read Excel file
        df = pd.read_excel(file_path, sheet_name=sheet_name or 0, nrows=sample_size)
        
        # Extract schema
        columns = [
            Column(name=str(col), index=i)
            for i, col in enumerate(df.columns)
        ]
        
        # Convert to list of lists
        rows = df.values.tolist()
        
        return CanonicalTable(
            source_path=str(file_path),
            source_type="excel",
            columns=columns,
            column_count=len(columns),
            row_count=len(rows),
            rows=rows,
            is_sample=sample_size is not None,
            sample_size=len(rows) if sample_size else None,
        )


# ---------------------------------------------------------------------------
# SQLite/DuckDB Engine
# ---------------------------------------------------------------------------

class SQLiteEngine(FormatEngine):
    """Parse SQLite/DuckDB database files."""
    
    def can_handle(self, file_path: Path, file_format: str) -> bool:
        return file_format in ("sqlite", "sqlite3", "db", "duckdb")
    
    def parse(
        self,
        file_path: Path,
        encoding: Optional[str] = None,
        compression: Optional[str] = None,
        sample_size: Optional[int] = None,
        table_name: Optional[str] = None,
        **kwargs
    ) -> CanonicalTable:
        """Parse database table using DuckDB."""
        import duckdb
        
        con = duckdb.connect(str(file_path), read_only=True)
        
        # If no table name, get first table
        if not table_name:
            tables = con.execute("SHOW TABLES").fetchall()
            if not tables:
                raise ValueError(f"No tables found in database: {file_path}")
            table_name = tables[0][0]
        
        # Build query
        query = f"SELECT * FROM {table_name}"
        if sample_size:
            query += f" LIMIT {sample_size}"
        
        # Execute query
        result = con.execute(query).fetchall()
        column_names = [desc[0] for desc in con.description]
        
        con.close()
        
        # Build canonical table
        columns = [Column(name=name, index=i) for i, name in enumerate(column_names)]
        
        return CanonicalTable(
            source_path=str(file_path),
            source_type="sqlite",
            columns=columns,
            column_count=len(columns),
            row_count=len(result),
            rows=result,
            is_sample=sample_size is not None,
            sample_size=len(result) if sample_size else None,
        )


# ---------------------------------------------------------------------------
# Format Engine Registry
# ---------------------------------------------------------------------------

class FormatEngineRegistry:
    """Registry of format engines."""
    
    def __init__(self):
        self.engines: List[FormatEngine] = []
        self._register_defaults()
    
    def _register_defaults(self):
        """Register built-in engines."""
        self.register(CSVEngine())
        self.register(JSONEngine())
        self.register(ParquetEngine())
        self.register(ExcelEngine())
        self.register(SQLiteEngine())
    
    def register(self, engine: FormatEngine):
        """Register a new format engine."""
        self.engines.append(engine)
    
    def get_engine(self, file_path: Path, file_format: str) -> Optional[FormatEngine]:
        """Get the appropriate engine for a file."""
        for engine in self.engines:
            if engine.can_handle(file_path, file_format):
                return engine
        return None
    
    def parse(
        self,
        file_path: Path,
        file_format: str,
        **kwargs
    ) -> CanonicalTable:
        """Parse file using appropriate engine."""
        engine = self.get_engine(file_path, file_format)
        if not engine:
            raise ValueError(f"No engine found for format: {file_format}")
        
        log.info("Parsing with %s", engine.__class__.__name__)
        return engine.parse(file_path, **kwargs)


# Global registry instance
registry = FormatEngineRegistry()
