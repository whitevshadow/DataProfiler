"""
Remote data source connectors — S3, MinIO, ADLS, GCS, Snowflake, PostgreSQL.

Provides URI-based routing, credential management, and DuckDB-backed
remote data access.  The existing local-file pipeline is untouched;
remote sources enter at the RawColumnData level.

Public API:
    parse_uri(uri)          → SourceDescriptor
    is_remote_uri(uri)      → bool
    resolve_source(path)    → Path | SourceDescriptor
    ConnectionManager       — in-memory credential store
    registry                — ConnectorRegistry singleton
"""

# Use try/except to support both package structures
try:
    from file_profiler.connectors.uri_parser import is_remote_uri, parse_uri
    from file_profiler.connectors.base import (
        BaseConnector,
        RemoteObject,
        SourceDescriptor,
    )
    from file_profiler.connectors.connection_manager import ConnectionManager
    from file_profiler.connectors.registry import registry
except ImportError:
    # Local imports for development/testing
    try:
        from .uri_parser import is_remote_uri, parse_uri
        from .base import (
            BaseConnector,
            RemoteObject,
            SourceDescriptor,
        )
        from .connection_manager import ConnectionManager
        from .registry import registry
    except ImportError:
        # Minimal stubs for when full package is not available
        def is_remote_uri(uri):
            return uri.startswith(('s3://', 'gs://', 'abfss://', 'postgresql://', 'snowflake://'))
        
        def parse_uri(uri):
            return None
        
        BaseConnector = None
        RemoteObject = None
        SourceDescriptor = None
        ConnectionManager = None
        registry = None

__all__ = [
    "BaseConnector",
    "ConnectionManager",
    "RemoteObject",
    "SourceDescriptor",
    "is_remote_uri",
    "parse_uri",
    "registry",
]
