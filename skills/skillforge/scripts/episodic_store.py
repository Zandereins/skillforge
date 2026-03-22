"""Underscore alias for episodic-store.py — enables clean Python imports.

Usage:
    import episodic_store
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
_mod = importlib.import_module("episodic-store")

def __getattr__(name):
    return getattr(_mod, name)
