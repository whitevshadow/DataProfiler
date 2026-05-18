"""
File connector module.

Provides local file system connectivity for the profiling pipeline.
"""

from .connect_file import FileConnector, connect

__all__ = ["FileConnector", "connect"]
