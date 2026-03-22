"""Underscore alias for skill-mesh.py — enables clean Python imports.

Usage:
    import skill_mesh
    # or: from skill_mesh import run_mesh_analysis
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
_mod = importlib.import_module("skill-mesh")

def __getattr__(name):
    return getattr(_mod, name)
