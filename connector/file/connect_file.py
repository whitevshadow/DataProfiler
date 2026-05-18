"""
Layer 1 — Local File Connector

Connects to local files (CSV, Parquet, etc.) with:
- Authentication (file permissions check)
- Metadata fetching (size, encoding, compression)
- Access validation (existence, readability, format detection)
- Unified source descriptor output

Integrates with Layer 2 (Validator + Sampler) for full intake pipeline.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import duckdb

# Import from parent connector module
try:
    from ..base import (
        BaseConnector,
        ConnectorError,
        RemoteObject,
        SourceDescriptor,
    )
except ImportError:
    from file_profiler.connectors.base import (
        BaseConnector,
        ConnectorError,
        RemoteObject,
        SourceDescriptor,
    )

log = logging.getLogger(__name__)


class FileConnector(BaseConnector):
    """
    Local file system connector.
    
    Handles CSV, Parquet, and other file formats supported by DuckDB.
    Validates file access, detects format, compression, and encoding.
    """

    def test_connection(
        self,
        descriptor: SourceDescriptor,
        credentials: dict,
    ) -> bool:
        """
        Test if the file/directory is accessible.
        
        For local files, credentials are not needed, but we verify:
        - Path exists
        - We have read permissions
        - Path is a file or directory
        
        Args:
            descriptor: SourceDescriptor with file:// scheme
            credentials: Ignored for local files
            
        Returns:
            True if file is accessible
            
        Raises:
            ConnectorError: If file doesn't exist or is not readable
        """
        path = Path(descriptor.path)
        
        if not path.exists():
            raise ConnectorError(f"Path does not exist: {path}")
        
        if not (path.is_file() or path.is_dir()):
            raise ConnectorError(f"Path is neither file nor directory: {path}")
        
        # Test read permissions
        if path.is_file():
            if not os.access(path, os.R_OK):
                raise ConnectorError(f"No read permission for file: {path}")
        elif path.is_dir():
            if not os.access(path, os.R_OK | os.X_OK):
                raise ConnectorError(f"No read/execute permission for directory: {path}")
        
        log.info("✓ File connection test passed: %s", path)
        return True

    def configure_duckdb(
        self,
        con: duckdb.DuckDBPyConnection,
        descriptor: SourceDescriptor,
        credentials: dict,
    ) -> None:
        """
        Configure DuckDB for local file reading.
        
        No special extensions needed for local files — DuckDB's built-in
        read_csv_auto() and read_parquet() handle most cases.
        
        Args:
            con: DuckDB connection
            descriptor: SourceDescriptor with file:// scheme
            credentials: Ignored for local files
        """
        # Enable parallel processing for better performance
        con.execute("PRAGMA threads=4;")
        
        # Set memory limit to avoid OOM on large files
        con.execute("PRAGMA memory_limit='4GB';")
        
        log.debug("DuckDB configured for local file access")

    def list_objects(
        self,
        descriptor: SourceDescriptor,
        credentials: dict,
    ) -> list[RemoteObject]:
        """
        List files in a directory or return single file info.
        
        If descriptor.path is a directory, lists all supported files.
        If it's a single file, returns a list with one RemoteObject.
        
        Args:
            descriptor: SourceDescriptor with file:// scheme
            credentials: Ignored for local files
            
        Returns:
            List of RemoteObject instances
        """
        path = Path(descriptor.path)
        
        # Supported extensions
        SUPPORTED_EXTS = {
            '.csv', '.tsv', '.txt',
            '.parquet', '.pq', '.parq',
            '.json', '.jsonl', '.ndjson',
            '.xlsx', '.xls',
        }
        
        objects = []
        
        if path.is_file():
            # Single file
            suffix = path.suffix.lower()
            file_format = self._detect_format(path)
            
            objects.append(RemoteObject(
                name=path.name,
                uri=f"file://{path.resolve().as_posix()}",
                size_bytes=path.stat().st_size,
                file_format=file_format,
            ))
        
        elif path.is_dir():
            # Directory — list all supported files
            for file_path in sorted(path.iterdir()):
                if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTS:
                    file_format = self._detect_format(file_path)
                    
                    objects.append(RemoteObject(
                        name=file_path.name,
                        uri=f"file://{file_path.resolve().as_posix()}",
                        size_bytes=file_path.stat().st_size,
                        file_format=file_format,
                    ))
        
        log.info("Found %d file(s) at %s", len(objects), path)
        return objects

    def duckdb_scan_expression(
        self,
        descriptor: SourceDescriptor,
        object_uri: Optional[str] = None,
    ) -> str:
        """
        Return DuckDB SQL expression to read the file.
        
        Args:
            descriptor: SourceDescriptor with file:// scheme
            object_uri: Override URI for specific file
            
        Returns:
            SQL expression like "read_csv_auto('path')" or "read_parquet('path')"
        """
        uri = object_uri or descriptor.raw_uri
        
        # Strip file:// prefix if present
        if uri.startswith("file://"):
            path_str = uri[7:]
        else:
            path_str = uri
        
        path = Path(path_str)
        suffix = path.suffix.lower()
        
        # Format detection
        if suffix in ('.csv', '.tsv', '.txt'):
            return f"read_csv_auto('{path.resolve().as_posix()}')"
        elif suffix in ('.parquet', '.pq', '.parq'):
            return f"read_parquet('{path.resolve().as_posix()}')"
        elif suffix in ('.json', '.jsonl', '.ndjson'):
            return f"read_json_auto('{path.resolve().as_posix()}')"
        else:
            # Fallback — let DuckDB auto-detect
            return f"read_csv_auto('{path.resolve().as_posix()}')"

    def _detect_format(self, path: Path) -> str:
        """
        Detect file format based on extension and magic bytes.
        
        Magic byte detection ensures we don't trust extensions blindly.
        
        Args:
            path: Path to file
            
        Returns:
            Format string: 'csv', 'parquet', 'json', 'excel', 'compressed', 'unknown'
        """
        suffix = path.suffix.lower()
        
        # Read first few bytes for magic byte detection
        try:
            with open(path, 'rb') as f:
                header = f.read(8)
        except Exception as e:
            log.warning("Cannot read file header for %s: %s", path, e)
            return 'unknown'
        
        # Magic byte detection (Layer 2 — Validation!)
        # Compressed files
        if header[:2] == b'\x1f\x8b':
            return 'compressed_gz'
        if header[:4] == b'PK\x03\x04':
            return 'compressed_zip'
        
        # Parquet magic: "PAR1"
        if header[:4] == b'PAR1':
            return 'parquet'
        
        # Excel magic
        if header[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
            return 'excel_xls'
        if header[:4] == b'PK\x03\x04':  # .xlsx is a ZIP
            return 'excel_xlsx'
        
        # JSON detection (simple heuristic)
        try:
            first_chars = header.decode('utf-8', errors='ignore').strip()
            if first_chars.startswith(('{', '[')):
                return 'json'
        except:
            pass
        
        # Fallback to extension-based detection
        if suffix in ('.csv', '.tsv', '.txt'):
            return 'csv'
        elif suffix in ('.parquet', '.pq', '.parq'):
            return 'parquet'
        elif suffix in ('.json', '.jsonl', '.ndjson'):
            return 'json'
        elif suffix in ('.xlsx', '.xls'):
            return 'excel'
        
        return 'unknown'


# ---------------------------------------------------------------------------
# High-level connect() function for easy usage
# ---------------------------------------------------------------------------

def connect(file_path: str | Path) -> dict:
    """
    High-level function to connect to a local file and return metadata.
    
    This is the main entry point for Layer 1 (Connector).
    
    Returns a unified source descriptor that Layer 2 (Validator) can use.
    
    Args:
        file_path: Path to local file or directory
        
    Returns:
        dict with structure:
        {
            "source_type": "file",
            "uri": "file:///path/to/file.csv",
            "is_remote": False,
            "file_name": "file.csv",
            "file_format": "csv",
            "size_bytes": 12345,
            "size_mb": 0.01,
            "encoding": None,  # Will be detected by Layer 2 (Validator)
            "compression": None,  # Will be detected by Layer 2 (Validator)
            "accessible": True,
            "exists": True
        }
        
    Raises:
        ConnectorError: If file doesn't exist or is not accessible
    """
    path = Path(file_path).resolve()
    
    # Create connector instance
    connector = FileConnector()
    
    # Create descriptor
    descriptor = SourceDescriptor(
        scheme="file",
        bucket_or_host="localhost",
        path=str(path),
        raw_uri=f"file://{path.as_posix()}",
    )
    
    # Test connection (validates existence and permissions)
    try:
        connector.test_connection(descriptor, {})
    except ConnectorError as e:
        log.error("Connection failed: %s", e)
        raise
    
    # Get file info
    if path.is_file():
        size_bytes = path.stat().st_size
        file_format = connector._detect_format(path)
        file_name = path.name
    else:
        # Directory — report as directory type
        size_bytes = 0
        file_format = "directory"
        file_name = path.name
    
    result = {
        "source_type": "file",
        "uri": f"file://{path.as_posix()}",
        "is_remote": False,
        "file_name": file_name,
        "file_format": file_format,
        "size_bytes": size_bytes,
        "size_mb": round(size_bytes / (1024 * 1024), 2),
        "encoding": None,  # Layer 2 will detect this
        "compression": None,  # Layer 2 will detect this
        "accessible": True,
        "exists": True,
    }
    
    log.info("✓ Connected to file: %s", path)
    log.info("  Format: %s | Size: %.2f MB", file_format, result["size_mb"])
    
    return result
