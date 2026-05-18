# Connector Module Structure

## Current Organization (Clean & Modular)

```
connector/
├── __init__.py                 # Main module exports
├── __main__.py                 # CLI entry point
├── base.py                     # Base classes & interfaces
├── registry.py                 # Connector registry
├── uri_parser.py              # URI parsing utilities
├── connection_manager.py       # Connection management
├── connection_pool.py          # Connection pooling
├── credential_store.py         # Credential storage
├── duckdb_remote.py            # DuckDB remote utilities
│
├── file/                       # Local file connector
│   ├── __init__.py
│   └── connect_file.py
│
├── cloud/                      # Cloud storage connectors
│   ├── __init__.py
│   └── cloud_storage.py       # S3, GCS, Azure ADLS
│
└── database/                   # Database connectors
    ├── __init__.py
    └── database.py            # PostgreSQL, Snowflake
```

## Structure Benefits

### ✅ Modular Organization
- Each connector type in its own subdirectory
- Clear separation of concerns
- Easy to add new connector types

### ✅ Consistent with Profiler Structure
```
profiler/
├── classifier/
├── planner/
├── sampling/
└── validator/
```

### ✅ Clean Imports
```python
# Module-level imports
from connector.file import FileConnector
from connector.cloud import CloudStorageConnector
from connector.database import DatabaseConnector
```

### ✅ Easy to Extend
Add new connectors by creating a new subdirectory:
```
connector/
└── streaming/         # NEW: Kafka, Kinesis, etc.
    ├── __init__.py
    └── kafka_connector.py
```

## Import Patterns

### For Package Users
```python
from file_profiler.connectors.file import FileConnector
from file_profiler.connectors.cloud import CloudStorageConnector
from file_profiler.connectors.database import DatabaseConnector
```

### Internal (Relative Imports)
```python
# Within connector module
from ..base import BaseConnector
from ..registry import registry
```

## Key Files

| File | Purpose |
|------|---------|
| `base.py` | Abstract base classes & data structures |
| `registry.py` | Lazy connector registration |
| `uri_parser.py` | Parse connection URIs |
| `connection_manager.py` | Manage active connections |
| `file/connect_file.py` | Local file system connector |
| `cloud/cloud_storage.py` | S3, GCS, Azure blob storage |
| `database/database.py` | PostgreSQL, Snowflake connectors |

## Comparison: Before vs After

### Before (Mixed Structure)
```
connector/
├── cloud_storage.py      # ❌ Root level
├── database.py           # ❌ Root level
└── file/                 # ✓ Organized
    └── connect_file.py
```

### After (Clean Structure)
```
connector/
├── file/                 # ✓ All organized
├── cloud/                # ✓ All organized
└── database/             # ✓ All organized
```

Now follows the same pattern as `profiler/` module! ✨
