"""score_skill — Python import facade for the scoring package.

Enables `import score_skill` as before, backed by the scoring/ package.
"""
from scoring import (
    score_structure, score_triggers, score_efficiency,
    score_composability, score_quality,
    score_edges, score_runtime, score_clarity,
    score_diff, explain_score_change, compute_composite,
)
from shared import invalidate_cache, read_skill_safe, extract_description
