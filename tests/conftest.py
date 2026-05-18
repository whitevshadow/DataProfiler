from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def tmp_path():
    """Workspace-local temp path that avoids locked AppData/pytest basetemp dirs."""
    root = Path(".test-tmp-runtime").resolve()
    root.mkdir(exist_ok=True)
    path = root / uuid.uuid4().hex
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
