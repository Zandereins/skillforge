"""Underscore alias for meta-report.py — enables clean Python imports.

Usage:
    import meta_report
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
_mod = importlib.import_module("meta-report")

def __getattr__(name):
    return getattr(_mod, name)
