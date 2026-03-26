"""Tests for schliff compare command (T6).

Covers:
- test_compare_output_has_deltas: JSON output contains deltas and biggest_gap
- test_compare_terminal_output: terminal output shows dimension table
- test_compare_missing_file_a: exits 1 when first file is missing
- test_compare_missing_file_b: exits 1 when second file is missing
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

CLI_PATH = str(Path(__file__).resolve().parent.parent.parent / "scripts" / "cli.py")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_cli(*args, timeout=30):
    return subprocess.run(
        [sys.executable, CLI_PATH, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


BAD_SKILL = """\
---
name: bad-skill
description: Vague skill with no structure.
---

# Bad Skill

This skill might help sometimes.
"""

GOOD_SKILL = """\
---
name: good-skill
description: >
  A comprehensive skill with proper structure and triggers.
  Use when running automated quality checks on skill files.
  Do NOT use for creating new skills from scratch.
---

# Good Skill

Use this skill when you need to verify skill quality scoring.

## When to Use

- Run automated quality checks on skill files
- Verify scoring functions produce expected results
- Test the verification pipeline

## How to Use

1. Run `schliff score path/to/SKILL.md` to get a baseline
2. Review the dimension breakdown
3. Fix any weak dimensions

## Scope

This skill handles: scoring verification, quality checks.
This skill does NOT handle: skill creation, runtime evaluation.

## Error Behavior

If the skill file is missing, return exit code 2.
If scoring fails, log the error and return exit code 2.
"""


# ---------------------------------------------------------------------------
# P0: JSON output contains deltas and biggest_gap
# ---------------------------------------------------------------------------

class TestCompareOutputHasDeltas:
    """cmd_compare --json must return deltas and biggest_gap."""

    def test_compare_output_has_deltas(self, tmp_path):
        """JSON output must have deltas dict and biggest_gap with dimension + delta."""
        path_a = tmp_path / "bad_skill.md"
        path_b = tmp_path / "good_skill.md"
        path_a.write_text(BAD_SKILL, encoding="utf-8")
        path_b.write_text(GOOD_SKILL, encoding="utf-8")

        result = _run_cli("compare", str(path_a), str(path_b), "--json")
        assert result.returncode == 0, f"stderr: {result.stderr}"

        data = json.loads(result.stdout)

        # Top-level keys
        assert "file_a" in data
        assert "file_b" in data
        assert "deltas" in data
        assert "biggest_gap" in data

        # file_a and file_b have expected shape
        assert "composite" in data["file_a"]
        assert "dimensions" in data["file_a"]
        assert "composite" in data["file_b"]
        assert "dimensions" in data["file_b"]

        # deltas is a non-empty dict of floats
        assert isinstance(data["deltas"], dict)
        assert len(data["deltas"]) > 0
        for dim, delta in data["deltas"].items():
            assert isinstance(delta, (int, float)), f"delta for {dim} is not numeric"

        # biggest_gap has required fields
        assert "dimension" in data["biggest_gap"]
        assert "delta" in data["biggest_gap"]
        assert data["biggest_gap"]["dimension"] in data["deltas"]

    def test_compare_good_scores_higher_than_bad(self, tmp_path):
        """The good skill must have a higher composite score than the bad skill."""
        path_a = tmp_path / "bad_skill.md"
        path_b = tmp_path / "good_skill.md"
        path_a.write_text(BAD_SKILL, encoding="utf-8")
        path_b.write_text(GOOD_SKILL, encoding="utf-8")

        result = _run_cli("compare", str(path_a), str(path_b), "--json")
        assert result.returncode == 0, f"stderr: {result.stderr}"

        data = json.loads(result.stdout)
        assert data["file_b"]["composite"] > data["file_a"]["composite"], (
            f"Expected good skill to score higher: "
            f"A={data['file_a']['composite']}, B={data['file_b']['composite']}"
        )


# ---------------------------------------------------------------------------
# Terminal output
# ---------------------------------------------------------------------------

class TestCompareTerminalOutput:
    """Terminal output must contain the comparison table."""

    def test_compare_terminal_shows_dimensions(self, tmp_path):
        path_a = tmp_path / "bad_skill.md"
        path_b = tmp_path / "good_skill.md"
        path_a.write_text(BAD_SKILL, encoding="utf-8")
        path_b.write_text(GOOD_SKILL, encoding="utf-8")

        result = _run_cli("compare", str(path_a), str(path_b))
        assert result.returncode == 0, f"stderr: {result.stderr}"

        output = result.stdout
        assert "schliff compare" in output
        assert "File A" in output
        assert "File B" in output
        assert "Composite" in output
        assert "Biggest gap" in output

    def test_compare_terminal_shows_delta_sign(self, tmp_path):
        """Delta column must show signed values like +10.0 or -5.0."""
        path_a = tmp_path / "bad_skill.md"
        path_b = tmp_path / "good_skill.md"
        path_a.write_text(BAD_SKILL, encoding="utf-8")
        path_b.write_text(GOOD_SKILL, encoding="utf-8")

        result = _run_cli("compare", str(path_a), str(path_b))
        assert result.returncode == 0, f"stderr: {result.stderr}"

        import re
        assert re.search(r"[+-]\d+\.\d", result.stdout), (
            "Expected signed delta values in output"
        )


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestCompareMissingFiles:
    """Missing files must cause exit code 1 with an error message."""

    def test_compare_missing_file_a(self, tmp_path):
        path_b = tmp_path / "good_skill.md"
        path_b.write_text(GOOD_SKILL, encoding="utf-8")
        missing = str(tmp_path / "nope_a.md")

        result = _run_cli("compare", missing, str(path_b))
        assert result.returncode == 1
        assert "not found" in result.stderr.lower()

    def test_compare_missing_file_b(self, tmp_path):
        path_a = tmp_path / "bad_skill.md"
        path_a.write_text(BAD_SKILL, encoding="utf-8")
        missing = str(tmp_path / "nope_b.md")

        result = _run_cli("compare", str(path_a), missing)
        assert result.returncode == 1
        assert "not found" in result.stderr.lower()
