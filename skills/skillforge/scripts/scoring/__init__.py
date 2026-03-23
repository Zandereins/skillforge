"""SkillForge Scoring Package — public API.

Each dimension is scored in its own module. Import everything from here
for backward compatibility with code that used the monolithic score-skill.py.
"""
import sys as _sys
from pathlib import Path as _Path

# Ensure scripts/ is on sys.path so scoring modules can import shared, nlp
_scripts_dir = str(_Path(__file__).resolve().parent.parent)
if _scripts_dir not in _sys.path:
    _sys.path.insert(0, _scripts_dir)
from scoring.structure import score_structure
from scoring.triggers import score_triggers
from scoring.efficiency import score_efficiency
from scoring.composability import score_composability
from scoring.coherence import score_coherence  # Note: returns {bonus, details} not {score, issues, details} — used internally by quality.py
from scoring.quality import score_quality
from scoring.edges import score_edges
from scoring.runtime import score_runtime
from scoring.clarity import score_clarity
from scoring.diff import score_diff, explain_score_change
from scoring.composite import compute_composite
