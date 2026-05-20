# Layer 5 — Format Engines Documentation

## Overview

**Layer 5** converts raw data sources into a **Canonical Table IR** (Intermediate Representation).

### Design Philosophy

**Format engines ONLY parse, NEVER profile.**

This critical design rule prevents duplicated logic by keeping:
- **Parsing** (Layer 5) separate from
- **Analysis** (Layer 6 - Profiler)

---

## Architecture

### Canonical Table IR

The standardized intermediate representation that all format engines produce:

```python
@dataclass
class CanonicalTable:
    # Metadata
    source_path: str
    source_type: str  # "csv", "parquet", "json", etc.
    
    # Schema
    columns: List[Column]
    column_count: int
    row_count: Optional[int]
    
    # Data
    rows: Optional[List[List[Any]]]  # In-memory
    _row_iterator: Optional[Iterator]  # Streaming
    
    # Format-specific
    encoding: Optional[str]
    delimiter: Optional[str]
    compression: Optional[str]
```

### Benefits

✅ **Single Profiler** — Works with all formats  
✅ **No Duplication** — Parse logic per format, profile logic once  
✅ **Easy Extension** — Add new format = One new engine class  
✅ **Memory Efficient** — Supports both in-memory and streaming  

---

## Supported Formats

| Format | Engine | Status | Dependencies |
|--------|--------|--------|--------------|
| CSV/TSV | `CSVEngine` | ✅ Complete | Built-in |
| JSON | `JSONEngine` | ✅ Complete | Built-in |
| NDJSON | `JSONEngine` | ✅ Complete | Built-in |
| Parquet | `ParquetEngine` | ✅ Complete | `pyarrow` |
| Excel | `ExcelEngine` | ✅ Complete | `pandas`, `openpyxl` |
| SQLite | `SQLiteEngine` | ✅ Complete | `duckdb` |
| PostgreSQL | _Future_ | 🚧 Planned | `psycopg2` |
| Snowflake | _Future_ | 🚧 Planned | `snowflake-connector` |

---

## Usage

### Basic Usage

```python
from profiler.engines import registry

# Parse any supported format
table = registry.parse(
    file_path=Path("data/sales.csv"),
    file_format="csv",
    encoding="utf-8",
    sample_size=1000
)

# Access data
print(f"Columns: {table.get_column_names()}")
print(f"Rows: {table.row_count}")

# Iterate rows
for row in table.iter_rows():
    process(row)
```

### Format-Specific Options

#### CSV
```python
table = registry.parse(
    file_path=path,
    file_format="csv",
    encoding="utf-8",
    delimiter=",",
    sample_size=5000
)
```

#### JSON/NDJSON
```python
table = registry.parse(
    file_path=path,
    file_format="json",  # or "jsonl", "ndjson"
    sample_size=1000
)
```

#### Parquet
```python
table = registry.parse(
    file_path=path,
    file_format="parquet",
    sample_size=10000
)
```

#### Excel
```python
table = registry.parse(
    file_path=path,
    file_format="excel",
    sheet_name="Sheet1",  # Optional
    sample_size=1000
)
```

#### SQLite/DuckDB
```python
table = registry.parse(
    file_path=path,
    file_format="sqlite",
    table_name="customers",  # Optional
    sample_size=5000
)
```

---

## Integration with Pipeline

Layer 5 sits between the Sampler (Layer 4) and the future Profiler (Layer 6):

```python
# After Layer 4 (Sampler)
from profiler.engines import registry

# Parse using appropriate engine
canonical_table = registry.parse(
    file_path=file_path,
    file_format=connector_result["file_format"],
    encoding=validation_result.encoding,
    compression=validation_result.compression,
    sample_size=execution_plan.sample_size
)

# canonical_table is now ready for Layer 6 (Profiler)
# Profiler works with CanonicalTable regardless of source format
```

---

## Engine Implementation

### Creating a New Engine

To add support for a new format:

```python
class MyFormatEngine(FormatEngine):
    def can_handle(self, file_path: Path, file_format: str) -> bool:
        return file_format == "myformat"
    
    def parse(
        self,
        file_path: Path,
        encoding: Optional[str] = None,
        compression: Optional[str] = None,
        sample_size: Optional[int] = None,
        **kwargs
    ) -> CanonicalTable:
        # 1. Read file
        # 2. Extract schema
        # 3. Extract data
        # 4. Return CanonicalTable
        
        columns = [Column(name=..., index=...)]
        rows = [...]
        
        return CanonicalTable(
            source_path=str(file_path),
            source_type="myformat",
            columns=columns,
            column_count=len(columns),
            row_count=len(rows),
            rows=rows
        )

# Register engine
registry.register(MyFormatEngine())
```

### Engine Responsibilities

**DO:**
- ✅ Parse file format
- ✅ Extract schema (column names, order)
- ✅ Extract data (rows)
- ✅ Handle compression
- ✅ Handle sampling
- ✅ Handle encoding (for text formats)

**DON'T:**
- ❌ Infer data types (Layer 6)
- ❌ Calculate statistics (Layer 6)
- ❌ Profile data quality (Layer 6)
- ❌ Detect patterns (Layer 6)

---

## File Structure

```
profiler/
└── engines/
    ├── __init__.py            # Module exports
    └── format_engines.py      # All engines + CanonicalTable IR

tests/
└── test_engines.py            # Engine tests

docs/
└── LAYER5_FORMAT_ENGINES.md   # This file
```

---

## Testing

Run the test suite:

```bash
python tests/test_engines.py
```

Expected output:
```
FORMAT ENGINES TEST SUITE
============================================================

TEST: CSV Engine
✓ Parsed: data/Sales_Customers.csv
  Columns: 13
  Rows: 5

TEST: JSON Engine
✓ Parsed: json
  Columns: 4
  Rows: 2

TEST: NDJSON Engine
✓ Parsed: json
  Columns: 3
  Rows: 2

RESULTS
============================================================
✓ CSV Engine
✓ JSON Engine
✓ NDJSON Engine
⚠ Parquet Engine (skipped)
✓ CanonicalTable Methods

Total: 4/4 passed, 1 skipped

✓ All tests passed!
```

---

## Performance Considerations

### Memory Management

For large files, engines support **streaming**:

```python
# In-memory (small files)
table.rows  # List of all rows

# Streaming (large files)
for row in table.iter_rows():
    process(row)  # One row at a time
```

### Sampling

All engines support `sample_size` parameter:

```python
table = registry.parse(
    file_path=large_file,
    file_format="csv",
    sample_size=10000  # Only read first 10K rows
)
```

This integrates with Layer 4 (Execution Planner) sample size recommendations.

---

## Error Handling

Engines raise descriptive errors:

```python
try:
    table = registry.parse(file_path, "csv")
except ValueError as e:
    # Empty file, invalid format, etc.
    print(f"Parse error: {e}")
except ImportError as e:
    # Missing dependency (e.g., pyarrow)
    print(f"Missing dependency: {e}")
```

---

## Future Enhancements

### Planned Engines

- **PostgreSQL** — Direct database connection
- **Snowflake** — Cloud data warehouse
- **BigQuery** — Google Cloud
- **Redshift** — AWS data warehouse
- **Kafka** — Streaming data

### Planned Features

- **Schema inference** hints (but not full inference - that's Layer 6)
- **Column sampling** (sample columns in addition to rows)
- **Multi-file support** (directory of files → single table)
- **Partitioned data** support

---

## Complete Pipeline

With Layer 5 implemented:

```
Layer 1: Connector       → Connect to source
Layer 2: Validator       → Verify format/encoding
Layer 2.5: Classifier    → Semantic intelligence
Layer 3: Planner         → Execution strategy
Layer 4: Sampler         → Adaptive sampling
Layer 5: Format Engine   → Parse → CanonicalTable ✅
Layer 6: Profiler        → Statistics/analysis (Future)
```

---

## Key Takeaways

1. **Separation of Concerns** — Parsing ≠ Profiling
2. **Single Profiler** — Works with all formats
3. **Extensible** — New format = New engine class
4. **Efficient** — Supports streaming for large files
5. **Integrated** — Works with adaptive sampling from Layer 4

Layer 5 is the bridge between **raw data** and **structured analysis**. 🎯
