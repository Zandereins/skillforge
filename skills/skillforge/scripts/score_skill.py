"""score_skill — Python import facade for the scoring package.

Enables `import score_skill` as before, backed by the scoring/ package.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from scoring import (
    score_structure, score_triggers, score_efficiency,
    score_composability, score_coherence, score_quality,
    score_edges, score_runtime, score_clarity,
    score_diff, explain_score_change, compute_composite,
)
from shared import invalidate_cache, read_skill_safe, extract_description

# Backward compat aliases
_read_skill_safe = read_skill_safe
_extract_description = extract_description
