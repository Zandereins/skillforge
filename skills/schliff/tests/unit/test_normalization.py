"""Tests for format normalization integrated into build_scores().

Regression guard: SKILL.md scores must remain identical to the v6.3.0 baseline.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared import build_scores
from scoring import compute_composite

# Absolute path to the baseline fixture
FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "v630_baseline.json"
# Absolute path to schliff's own SKILL.md
SKILL_MD_PATH = Path(__file__).resolve().parent.parent.parent / "SKILL.md"


# ---------------------------------------------------------------------------
# Regression guard
# ---------------------------------------------------------------------------

def test_skill_md_composite_identical_to_baseline():
    """SKILL.md composite score must match the v6.3.0 baseline exactly."""
    from shared import load_eval_suite
    baseline = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    eval_suite = load_eval_suite(str(SKILL_MD_PATH))
    scores = build_scores(str(SKILL_MD_PATH), eval_suite=eval_suite)
    result = compute_composite(scores)

    assert result["score"] == baseline["composite_score"], (
        f"composite changed: got {result['score']}, "
        f"expected {baseline['composite_score']}"
    )


def test_skill_md_dimensions_identical_to_baseline():
    """Every dimension score must match the v6.3.0 baseline exactly (tolerance=0)."""
    from shared import load_eval_suite
    baseline = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    baseline_dims = baseline["dimensions"]

    eval_suite = load_eval_suite(str(SKILL_MD_PATH))
    scores = build_scores(str(SKILL_MD_PATH), eval_suite=eval_suite)

    for dim, expected in baseline_dims.items():
        if dim == "runtime":
            # runtime is disabled (-1) and not included in build_scores by default
            continue
        assert dim in scores, f"dimension '{dim}' missing from scores"
        assert scores[dim]["score"] == expected, (
            f"dimension '{dim}' changed: got {scores[dim]['score']}, expected {expected}"
        )


# ---------------------------------------------------------------------------
# Normalization: non-SKILL.md formats get synthetic frontmatter injected
# ---------------------------------------------------------------------------

def test_build_scores_with_claude_md_does_not_crash(tmp_path):
    """build_scores() must handle a CLAUDE.md-shaped file without raising."""
    content = "# My AI Rules\n\nAlways be helpful. Do not hallucinate.\n"
    claude_file = tmp_path / "CLAUDE.md"
    claude_file.write_text(content, encoding="utf-8")

    scores = build_scores(str(claude_file))
    # Must return a dict with the standard dimensions
    for dim in ("structure", "triggers", "quality", "edges",
                "efficiency", "composability", "clarity"):
        assert dim in scores, f"dimension '{dim}' missing for CLAUDE.md input"


def test_build_scores_with_cursorrules_does_not_crash(tmp_path):
    """build_scores() must handle a .cursorrules-shaped file without raising."""
    content = "# Cursor Rules\n\nUse TypeScript. Prefer functional style.\n"
    rules_file = tmp_path / ".cursorrules"
    rules_file.write_text(content, encoding="utf-8")

    scores = build_scores(str(rules_file))
    for dim in ("structure", "triggers", "quality", "edges",
                "efficiency", "composability", "clarity"):
        assert dim in scores, f"dimension '{dim}' missing for .cursorrules input"


def test_build_scores_skill_md_path_unchanged():
    """For SKILL.md input, build_scores() must not create or mutate any tempfile."""
    # We verify this indirectly: scores must equal baseline (tested above).
    # Additionally, passing SKILL.md twice must yield identical results.
    scores_a = build_scores(str(SKILL_MD_PATH))
    scores_b = build_scores(str(SKILL_MD_PATH))
    assert scores_a == scores_b
