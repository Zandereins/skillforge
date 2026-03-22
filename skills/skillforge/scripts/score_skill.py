"""Underscore alias for score-skill.py — enables clean Python imports.

Usage:
    import score_skill
    score_skill.score_structure(path)
    score_skill.compute_composite(scores)
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
_mod = importlib.import_module("score-skill")

def __getattr__(name):
    return getattr(_mod, name)
