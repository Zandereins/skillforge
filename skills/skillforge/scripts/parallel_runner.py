"""Underscore alias for parallel-runner.py — enables clean Python imports.

Usage:
    import parallel_runner
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
_mod = importlib.import_module("parallel-runner")

def __getattr__(name):
    return getattr(_mod, name)
