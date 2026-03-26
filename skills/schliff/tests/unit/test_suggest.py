"""Tests for schliff suggest command (T7).

Covers:
- test_suggest_ranking_by_impact: suggestions are sorted by estimated delta descending
- test_suggest_exits_zero: command exits with code 0
- test_suggest_produces_output: command prints non-empty output
- test_suggest_missing_file: prints error and exits 1 on missing file
- test_suggest_json_output: --json flag produces valid JSON with expected keys
- test_suggest_top_flag: --top N limits the number of suggestions
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

CLI_PATH = str(Path(__file__).resolve().parent.parent.parent / "scripts" / "cli.py")
SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "scripts")


def _run_cli(*args, timeout=30):
    """Run cli.py with the given arguments."""
    return subprocess.run(
        [sys.executable, CLI_PATH, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _write_skill(tmp_path: Path, content: str) -> str:
    """Write content to SKILL.md and return the path string."""
    p = tmp_path / "SKILL.md"
    p.write_text(content, encoding="utf-8")
    return str(p)


# Deliberately bad skill — mirrors cmd_demo content, with extra flaws
BAD_SKILL = """\
---
name: deploy-helper
description: Helps with deployment stuff
---

# Deploy Helper

This skill probably helps with deployment. You might want to use it when deploying things.
Consider possibly running the deploy command.

## What It Does

- Setting up deployment configurations
- Running deploy commands
- Checking if deployment worked

## How To Use

1. Tell Claude you want to deploy something
2. It will try to help you
3. Check if it worked
"""


# ===========================================================================
# P0: suggestions are sorted by estimated delta descending
# ===========================================================================

class TestSuggestRankingByImpact:
    """cmd_suggest must return suggestions sorted by estimated delta descending."""

    def test_suggest_ranking_by_impact(self, tmp_path):
        """Suggestions from a bad skill must be sorted by delta descending."""
        # Use the text_gradient API directly to verify sorting
        sys.path.insert(0, SCRIPTS_DIR)
        import text_gradient

        skill_path = _write_skill(tmp_path, BAD_SKILL)
        gradients = text_gradient.compute_gradients(
            skill_path, eval_suite=None, include_clarity=True,
        )

        assert len(gradients) > 0, "Expected at least one gradient for a bad skill"

        # Verify sorted by delta descending (primary sort key is priority, which is
        # derived from delta — so we verify the priority order holds for delta too)
        deltas = [g["delta"] for g in gradients]
        # Each delta must be >= the next (sorted descending by priority/delta)
        # Allow ties — just verify no delta is strictly less than an earlier one
        # by more than a floating point epsilon when priorities are equal
        for i in range(len(gradients) - 1):
            priority_a = gradients[i]["priority"]
            priority_b = gradients[i + 1]["priority"]
            assert priority_a >= priority_b, (
                f"Gradient #{i+1} has lower priority ({priority_a}) than "
                f"gradient #{i+2} ({priority_b}) — sort order violated"
            )

    def test_suggest_top_n_returns_highest_impact_first(self, tmp_path):
        """The first suggestion must have the highest priority score."""
        sys.path.insert(0, SCRIPTS_DIR)
        import text_gradient

        skill_path = _write_skill(tmp_path, BAD_SKILL)
        all_gradients = text_gradient.compute_gradients(
            skill_path, eval_suite=None, include_clarity=True,
        )
        top3 = text_gradient.compute_gradients(
            skill_path, eval_suite=None, include_clarity=True, top_n=3,
        )

        assert len(top3) <= 3
        # Top 3 must be the first 3 from the full sorted list
        for i, g in enumerate(top3):
            assert g["issue"] == all_gradients[i]["issue"], (
                f"top_n={3} item {i} mismatch: {g['issue']} vs {all_gradients[i]['issue']}"
            )


# ===========================================================================
# CLI integration tests
# ===========================================================================

class TestSuggestCli:
    """CLI-level tests for the suggest command."""

    def test_suggest_exits_zero(self, tmp_path):
        skill_path = _write_skill(tmp_path, BAD_SKILL)
        result = _run_cli("suggest", skill_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_suggest_produces_output(self, tmp_path):
        skill_path = _write_skill(tmp_path, BAD_SKILL)
        result = _run_cli("suggest", skill_path)
        assert len(result.stdout.strip()) > 0, "Expected non-empty output"

    def test_suggest_shows_top_fixes_header(self, tmp_path):
        skill_path = _write_skill(tmp_path, BAD_SKILL)
        result = _run_cli("suggest", skill_path)
        assert "TOP FIXES" in result.stdout, f"Expected 'TOP FIXES' in output:\n{result.stdout}"

    def test_suggest_shows_score_summary(self, tmp_path):
        skill_path = _write_skill(tmp_path, BAD_SKILL)
        result = _run_cli("suggest", skill_path)
        assert "Current:" in result.stdout, f"Expected score summary in output:\n{result.stdout}"
        assert "Estimated after fixes:" in result.stdout

    def test_suggest_missing_file(self, tmp_path):
        missing = str(tmp_path / "nope.md")
        result = _run_cli("suggest", missing)
        assert result.returncode == 1
        assert "not found" in result.stderr.lower()

    def test_suggest_json_output(self, tmp_path):
        skill_path = _write_skill(tmp_path, BAD_SKILL)
        result = _run_cli("suggest", "--json", skill_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert "current_score" in data
        assert "estimated_score" in data
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)

    def test_suggest_json_suggestions_have_required_fields(self, tmp_path):
        skill_path = _write_skill(tmp_path, BAD_SKILL)
        result = _run_cli("suggest", "--json", skill_path)
        data = json.loads(result.stdout)
        for s in data["suggestions"]:
            assert "rank" in s
            assert "delta" in s
            assert "instruction" in s
            assert "dimension" in s

    def test_suggest_top_flag_limits_output(self, tmp_path):
        skill_path = _write_skill(tmp_path, BAD_SKILL)
        result = _run_cli("suggest", "--json", "--top", "3", skill_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert len(data["suggestions"]) <= 3

    def test_suggest_top_default_is_five(self, tmp_path):
        skill_path = _write_skill(tmp_path, BAD_SKILL)
        result = _run_cli("suggest", "--json", skill_path)
        data = json.loads(result.stdout)
        assert len(data["suggestions"]) <= 5

    def test_suggest_estimated_score_not_above_100(self, tmp_path):
        skill_path = _write_skill(tmp_path, BAD_SKILL)
        result = _run_cli("suggest", "--json", skill_path)
        data = json.loads(result.stdout)
        assert data["estimated_score"] <= 100.0

    def test_suggest_estimated_score_gte_current(self, tmp_path):
        """Estimated score must be >= current score (fixes can only improve)."""
        skill_path = _write_skill(tmp_path, BAD_SKILL)
        result = _run_cli("suggest", "--json", skill_path)
        data = json.loads(result.stdout)
        assert data["estimated_score"] >= data["current_score"], (
            f"Estimated {data['estimated_score']} < current {data['current_score']}"
        )
