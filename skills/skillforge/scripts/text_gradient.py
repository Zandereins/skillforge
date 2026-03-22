"""Underscore alias for text-gradient.py — enables clean Python imports.

Usage:
    import text_gradient
    # or: from text_gradient import compute_gradients, generate_patches
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
_mod = importlib.import_module("text-gradient")

def __getattr__(name):
    return getattr(_mod, name)
