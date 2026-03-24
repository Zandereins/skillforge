"""Golden-file regression tests for scoring determinism.

Each test captures known-good scores for specific skill contents.
If a code change causes a score shift beyond tolerance, the test fails,
signaling a potential regression (or an intentional scoring change that
needs the golden values updated).
"""
import json
import tempfile
from pathlib import Path

import pytest

from scoring import (
    score_structure,
    score_triggers,
    score_efficiency,
    score_composability,
    score_clarity,
    compute_composite,
)


# --- Helpers ---

def _write_skill(tmp_path: Path, content: str) -> str:
    """Write skill content to a temp file, return path string."""
    skill_path = tmp_path / "SKILL.md"
    skill_path.write_text(content, encoding="utf-8")
    return str(skill_path)


def _score_all(skill_path: str, eval_suite: dict = None) -> dict:
    """Score all structural dimensions and compute composite."""
    scores = {
        "structure": score_structure(skill_path),
        "efficiency": score_efficiency(skill_path),
        "composability": score_composability(skill_path),
        "clarity": score_clarity(skill_path),
    }
    if eval_suite:
        scores["triggers"] = score_triggers(skill_path, eval_suite)
    result = compute_composite(scores)
    result["dimensions"] = {k: v["score"] for k, v in scores.items()}
    return result


def _assert_score_in_range(actual: float, expected: float, tolerance: float = 3.0, label: str = ""):
    """Assert score is within tolerance of expected value."""
    assert abs(actual - expected) <= tolerance, (
        f"{label}: expected ~{expected} ±{tolerance}, got {actual}"
    )


# --- Golden Skill Contents ---

GOOD_SKILL = '''---
name: test-skill
description: >
  A test skill for unit testing. Use when testing scoring functions.
  Do not use for production deployment or security scanning.
---

# Test Skill

Use this skill when you need to test scoring functions.

## Instructions

1. Read the input file
2. Run the scoring function
3. Verify the output matches expectations

## Examples

Example 1: Basic scoring
```bash
python3 scripts/score-skill.py test.md --json
```

Example 2: With eval suite
```bash
python3 scripts/score-skill.py test.md --eval-suite eval.json
```

## When NOT to Use

Do not use this skill for:
- Production deployment
- Security vulnerability scanning
- Database migrations
'''

BAD_SKILL = '''no frontmatter here

TODO: add description
FIXME: add examples

you might want to consider maybe possibly doing something
you could try to perhaps attempt this
'''

MEDIUM_SKILL = '''---
name: code-formatter
description: Format code files using project-specific linting rules. Use when the user asks to format, lint, or clean up code style.
---

# Code Formatter

Format source code using the project's configured linter and formatter.

## Instructions

1. Read the project's linter configuration (e.g., `.eslintrc`, `ruff.toml`, `.prettierrc`)
2. Run the formatter on the specified files
3. Report which files were changed

## When NOT to Use

Do not use for:
- Refactoring logic (use a refactoring skill instead)
- Adding new code

## Examples

Example: Format a Python file
```bash
ruff format src/main.py
```
'''


# --- Golden Tests ---

class TestGoldenGoodSkill:
    """Good skill should score high across all dimensions."""

    def test_structure_high(self, tmp_path):
        path = _write_skill(tmp_path, GOOD_SKILL)
        result = score_structure(path)
        assert result["score"] >= 80, f"Structure should be >=80, got {result['score']}"

    def test_efficiency_reasonable(self, tmp_path):
        path = _write_skill(tmp_path, GOOD_SKILL)
        result = score_efficiency(path)
        assert result["score"] >= 60, f"Efficiency should be >=60, got {result['score']}"

    def test_composability_reasonable(self, tmp_path):
        path = _write_skill(tmp_path, GOOD_SKILL)
        result = score_composability(path)
        # With 10 checks, a basic good skill hits ~30 (scope + no global state + handoff)
        assert result["score"] >= 20, f"Composability should be >=20, got {result['score']}"

    def test_clarity_high(self, tmp_path):
        path = _write_skill(tmp_path, GOOD_SKILL)
        result = score_clarity(path)
        assert result["score"] >= 80, f"Clarity should be >=80, got {result['score']}"

    def test_composite_high(self, tmp_path):
        path = _write_skill(tmp_path, GOOD_SKILL)
        result = _score_all(path)
        assert result["score"] >= 70, f"Composite should be >=70, got {result['score']}"


class TestGoldenBadSkill:
    """Bad skill should score low across all dimensions."""

    def test_structure_low(self, tmp_path):
        path = _write_skill(tmp_path, BAD_SKILL)
        result = score_structure(path)
        # Bad skill has no frontmatter, no examples, but some lines count
        _assert_score_in_range(result["score"], 33, tolerance=5, label="bad_structure")

    def test_efficiency_low(self, tmp_path):
        path = _write_skill(tmp_path, BAD_SKILL)
        result = score_efficiency(path)
        assert result["score"] <= 60, f"Efficiency should be <=60, got {result['score']}"

    def test_composability_low(self, tmp_path):
        path = _write_skill(tmp_path, BAD_SKILL)
        result = score_composability(path)
        # With 10 checks, bad skill only hits global-state (no globals) + no hard reqs
        _assert_score_in_range(result["score"], 20, tolerance=5, label="bad_composability")

    def test_clarity_high_because_short(self, tmp_path):
        """Short bad skill has no contradictions — clarity measures contradictions, not quality."""
        path = _write_skill(tmp_path, BAD_SKILL)
        result = score_clarity(path)
        # Clarity=100 is correct: no contradictions in a short skill
        assert result["score"] >= 80, f"Clarity should be >=80 (no contradictions), got {result['score']}"

    def test_composite_low(self, tmp_path):
        path = _write_skill(tmp_path, BAD_SKILL)
        result = _score_all(path)
        _assert_score_in_range(result["score"], 45, tolerance=5, label="bad_composite")


class TestGoldenMediumSkill:
    """Medium skill should score in the middle range."""

    def test_structure_medium(self, tmp_path):
        path = _write_skill(tmp_path, MEDIUM_SKILL)
        result = score_structure(path)
        assert 50 <= result["score"] <= 95, f"Structure should be 50-95, got {result['score']}"

    def test_efficiency_medium(self, tmp_path):
        path = _write_skill(tmp_path, MEDIUM_SKILL)
        result = score_efficiency(path)
        assert result["score"] >= 50, f"Efficiency should be >=50, got {result['score']}"

    def test_composability_medium(self, tmp_path):
        path = _write_skill(tmp_path, MEDIUM_SKILL)
        result = score_composability(path)
        # Has scope boundaries but no handoff, no I/O contract
        assert 20 <= result["score"] <= 80, f"Composability should be 20-80, got {result['score']}"

    def test_clarity_high(self, tmp_path):
        path = _write_skill(tmp_path, MEDIUM_SKILL)
        result = score_clarity(path)
        # Medium skill has no contradictions
        assert result["score"] >= 70, f"Clarity should be >=70, got {result['score']}"

    def test_composite_medium(self, tmp_path):
        path = _write_skill(tmp_path, MEDIUM_SKILL)
        result = _score_all(path)
        assert 50 <= result["score"] <= 90, f"Composite should be 50-90, got {result['score']}"


class TestGoldenSelfScore:
    """Schliff's own SKILL.md should maintain S-grade."""

    def test_self_score_structural_high(self):
        """Schliff's SKILL.md structural-only score must be >= 80."""
        skill_path = str(Path(__file__).resolve().parent.parent.parent / "SKILL.md")
        result = _score_all(skill_path)
        # Note: without eval-suite, triggers/quality/edges are excluded.
        # Full score with eval-suite is ~90+. Structural-only is lower.
        assert result["score"] >= 80, (
            f"Self-score regression! Expected >=80, got {result['score']}"
        )

    def test_self_structure_perfect(self):
        """Structure should be near-perfect for our own skill."""
        skill_path = str(Path(__file__).resolve().parent.parent.parent / "SKILL.md")
        result = score_structure(skill_path)
        assert result["score"] >= 90, f"Structure should be >=90, got {result['score']}"

    def test_self_clarity_perfect(self):
        """Clarity should be perfect for our own skill."""
        skill_path = str(Path(__file__).resolve().parent.parent.parent / "SKILL.md")
        result = score_clarity(skill_path)
        assert result["score"] >= 90, f"Clarity should be >=90, got {result['score']}"


class TestScoringDeterminism:
    """Scoring must be deterministic — same input, same output."""

    def test_repeated_scoring_identical(self, tmp_path):
        """Score the same skill 3 times, all results must match."""
        path = _write_skill(tmp_path, GOOD_SKILL)
        scores = [_score_all(path)["score"] for _ in range(3)]
        assert scores[0] == scores[1] == scores[2], (
            f"Non-deterministic scoring! Got: {scores}"
        )

    def test_dimension_scores_stable(self, tmp_path):
        """Individual dimension scores must be stable across runs."""
        path = _write_skill(tmp_path, MEDIUM_SKILL)
        results = [_score_all(path)["dimensions"] for _ in range(3)]
        for dim in results[0]:
            values = [r[dim] for r in results]
            assert values[0] == values[1] == values[2], (
                f"Non-deterministic {dim}! Got: {values}"
            )
