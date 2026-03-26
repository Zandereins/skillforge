"""Smoke tests for schliff CLI (scripts/cli.py).

Tests the CLI via subprocess to avoid sys.exit() killing the test runner.
No network, no LLM — pure structural scoring only.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

CLI_PATH = str(Path(__file__).resolve().parent.parent.parent / "scripts" / "cli.py")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GOOD_SKILL = '''\
---
name: test-skill
description: >
  A comprehensive test skill for verifying scoring functions.
  Use when running automated quality checks on skill files.
  Do NOT use for creating new skills from scratch.
---

# Test Skill

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
'''


@pytest.fixture
def skill_file(tmp_path):
    """Write a well-formed SKILL.md to a temp directory."""
    p = tmp_path / "SKILL.md"
    p.write_text(GOOD_SKILL, encoding="utf-8")
    return str(p)


def _run_cli(*args, timeout=30):
    """Helper: run cli.py with the given arguments."""
    return subprocess.run(
        [sys.executable, CLI_PATH, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# 1. cmd_score — valid skill file
# ---------------------------------------------------------------------------

def test_score_valid_skill(skill_file):
    result = _run_cli("score", skill_file)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert len(result.stdout.strip()) > 0, "Expected some output from score"


# ---------------------------------------------------------------------------
# 2. cmd_score — missing file
# ---------------------------------------------------------------------------

def test_score_missing_file(tmp_path):
    missing = str(tmp_path / "does_not_exist.md")
    result = _run_cli("score", missing)
    assert result.returncode == 1
    assert "not found" in result.stderr.lower()


# ---------------------------------------------------------------------------
# 3. cmd_score — --json flag
# ---------------------------------------------------------------------------

def test_score_json_output(skill_file):
    result = _run_cli("score", "--json", skill_file)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    data = json.loads(result.stdout)
    assert "composite_score" in data
    assert "dimensions" in data
    assert isinstance(data["composite_score"], (int, float))


# ---------------------------------------------------------------------------
# 4. cmd_verify — valid skill file (exit 0 or 1)
# ---------------------------------------------------------------------------

def test_verify_valid_skill(skill_file):
    result = _run_cli("verify", skill_file)
    assert result.returncode in (0, 1), (
        f"Expected exit 0 or 1, got {result.returncode}; stderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# 5. cmd_verify — missing file (exit 2)
# ---------------------------------------------------------------------------

def test_verify_missing_file(tmp_path):
    missing = str(tmp_path / "nope.md")
    result = _run_cli("verify", missing)
    assert result.returncode == 2
    assert "not found" in result.stderr.lower()


# ---------------------------------------------------------------------------
# 6. cmd_verify — --min-score flag
# ---------------------------------------------------------------------------

def test_verify_min_score_zero_passes(skill_file):
    """With --min-score 0 any valid skill should pass."""
    result = _run_cli("verify", "--min-score", "0", skill_file)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_verify_min_score_100_fails(skill_file):
    """With --min-score 100 virtually any skill should fail."""
    result = _run_cli("verify", "--min-score", "100", skill_file)
    assert result.returncode == 1, (
        f"Expected exit 1 (fail) with --min-score 100, got {result.returncode}"
    )


# ---------------------------------------------------------------------------
# 7. cmd_version
# ---------------------------------------------------------------------------

def test_version():
    result = _run_cli("version")
    assert result.returncode == 0
    assert "schliff" in result.stdout.lower()


# ---------------------------------------------------------------------------
# 8. main() with no arguments
# ---------------------------------------------------------------------------

def test_no_arguments():
    result = _run_cli()
    # argparse prints help to stdout; should not crash
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# 9. cmd_score — --format flag accepted and surfaced in JSON output
# ---------------------------------------------------------------------------

def test_score_format_flag_accepted(skill_file):
    """--format flag is accepted without error."""
    result = _run_cli("score", "--format", "skill.md", skill_file)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_score_json_includes_format_key(skill_file):
    """JSON output includes a 'format' key."""
    result = _run_cli("score", "--json", skill_file)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    data = json.loads(result.stdout)
    assert "format" in data, f"'format' key missing from JSON output: {data.keys()}"
    assert isinstance(data["format"], str)


def test_score_format_override_in_json(skill_file):
    """--format override appears in JSON output."""
    result = _run_cli("score", "--json", "--format", "claude.md", skill_file)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    data = json.loads(result.stdout)
    assert data["format"] == "claude.md"


def test_score_format_invalid_choice(skill_file):
    """--format with an invalid choice exits non-zero."""
    result = _run_cli("score", "--format", "invalid_format", skill_file)
    assert result.returncode != 0
