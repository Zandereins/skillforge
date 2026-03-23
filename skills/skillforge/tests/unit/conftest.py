"""Pytest configuration for SkillForge unit tests."""
import sys
from pathlib import Path

import pytest

# Add scripts directory to path so scoring package is importable
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture(autouse=True)
def clear_caches():
    from shared import _file_cache
    _file_cache.clear()
    yield
    _file_cache.clear()
