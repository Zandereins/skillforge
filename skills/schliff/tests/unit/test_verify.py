"""Unit tests for schliff verify (verify.py)."""
import json
import time
from pathlib import Path

import pytest

import verify as verify_mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def good_skill(tmp_path):
    """A well-formed SKILL.md that scores high."""
    content = '''---
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

## Dependencies

Requires: Python 3.9+, scoring package.
'''
    skill_path = tmp_path / "SKILL.md"
    skill_path.write_text(content, encoding="utf-8")
    return str(skill_path)


@pytest.fixture
def bad_skill(tmp_path):
    """A poorly-formed SKILL.md that scores low."""
    content = '''no frontmatter here
TODO: add description
FIXME: add examples
This might maybe probably help with stuff.
'''
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    skill_path = bad_dir / "SKILL.md"
    skill_path.write_text(content, encoding="utf-8")
    return str(skill_path)


@pytest.fixture
def history_file(tmp_path):
    """A temporary history file path."""
    return str(tmp_path / ".schliff" / "history.jsonl")


# ---------------------------------------------------------------------------
# _score_skill
# ---------------------------------------------------------------------------

class TestScoreSkill:
    def test_returns_composite(self, good_skill):
        result = verify_mod._score_skill(good_skill)
        assert "composite" in result
        assert isinstance(result["composite"], float)
        assert 0 <= result["composite"] <= 100

    def test_returns_grade(self, good_skill):
        result = verify_mod._score_skill(good_skill)
        assert result["grade"] in ("S", "A", "B", "C", "D", "F")

    def test_returns_dimensions(self, good_skill):
        result = verify_mod._score_skill(good_skill)
        assert "dimensions" in result
        assert "structure" in result["dimensions"]
        assert "clarity" in result["dimensions"]

    def test_bad_skill_scores_lower(self, good_skill, bad_skill):
        good = verify_mod._score_skill(good_skill)
        bad = verify_mod._score_skill(bad_skill)
        assert good["composite"] > bad["composite"]


# ---------------------------------------------------------------------------
# _score_to_grade
# ---------------------------------------------------------------------------

class TestScoreToGrade:
    def test_grades(self):
        assert verify_mod._score_to_grade(100) == "S"
        assert verify_mod._score_to_grade(95) == "S"
        assert verify_mod._score_to_grade(90) == "A"
        assert verify_mod._score_to_grade(80) == "B"
        assert verify_mod._score_to_grade(70) == "C"
        assert verify_mod._score_to_grade(55) == "D"
        assert verify_mod._score_to_grade(30) == "F"


# ---------------------------------------------------------------------------
# History: load_last_score / append_history
# ---------------------------------------------------------------------------

class TestHistory:
    def test_no_history_returns_none(self, good_skill, history_file):
        result = verify_mod.load_last_score(good_skill, history_file)
        assert result is None

    def test_append_and_load(self, good_skill, history_file):
        result = {"composite": 82.5, "grade": "B", "dimensions": {}}
        verify_mod.append_history(good_skill, result, history_file)

        loaded = verify_mod.load_last_score(good_skill, history_file)
        assert loaded == 82.5

    def test_loads_latest_entry(self, good_skill, history_file):
        r1 = {"composite": 70.0, "grade": "C", "dimensions": {}}
        r2 = {"composite": 85.0, "grade": "A", "dimensions": {}}
        verify_mod.append_history(good_skill, r1, history_file)
        verify_mod.append_history(good_skill, r2, history_file)

        loaded = verify_mod.load_last_score(good_skill, history_file)
        assert loaded == 85.0

    def test_different_skills_isolated(self, tmp_path, history_file):
        skill_a = tmp_path / "a" / "SKILL.md"
        skill_b = tmp_path / "b" / "SKILL.md"
        skill_a.parent.mkdir()
        skill_b.parent.mkdir()
        skill_a.write_text("---\nname: a\n---\n", encoding="utf-8")
        skill_b.write_text("---\nname: b\n---\n", encoding="utf-8")

        verify_mod.append_history(str(skill_a), {"composite": 60.0, "grade": "C", "dimensions": {}}, history_file)
        verify_mod.append_history(str(skill_b), {"composite": 90.0, "grade": "A", "dimensions": {}}, history_file)

        assert verify_mod.load_last_score(str(skill_a), history_file) == 60.0
        assert verify_mod.load_last_score(str(skill_b), history_file) == 90.0

    def test_creates_parent_dirs(self, tmp_path):
        deep_path = str(tmp_path / "a" / "b" / "c" / "history.jsonl")
        verify_mod.append_history(
            "/fake/SKILL.md",
            {"composite": 50.0, "grade": "D", "dimensions": {}},
            deep_path,
        )
        assert Path(deep_path).exists()

    def test_history_entry_has_timestamp(self, good_skill, history_file):
        verify_mod.append_history(
            good_skill,
            {"composite": 80.0, "grade": "B", "dimensions": {}},
            history_file,
        )
        line = Path(history_file).read_text(encoding="utf-8").strip()
        entry = json.loads(line)
        assert "timestamp" in entry
        # Timestamp should be today
        assert entry["timestamp"].startswith(time.strftime("%Y-%m-%d"))

    def test_corrupt_lines_skipped(self, good_skill, history_file):
        hp = Path(history_file)
        hp.parent.mkdir(parents=True, exist_ok=True)
        resolved = str(Path(good_skill).resolve())
        hp.write_text(
            "not json\n"
            f'{{"skill_path":"{resolved}","composite":77.0}}\n'
            "also broken\n",
            encoding="utf-8",
        )
        assert verify_mod.load_last_score(good_skill, history_file) == 77.0


# ---------------------------------------------------------------------------
# run_verify — threshold checks
# ---------------------------------------------------------------------------

class TestRunVerifyThreshold:
    def test_good_skill_passes_default(self, good_skill, history_file):
        verdict = verify_mod.run_verify(
            good_skill, min_score=40.0, history_path=history_file,
        )
        assert verdict["exit_code"] == 0
        assert verdict["passed_threshold"] is True
        assert "PASS" in verdict["message"]

    def test_bad_skill_fails_high_threshold(self, bad_skill, history_file):
        verdict = verify_mod.run_verify(
            bad_skill, min_score=90.0, history_path=history_file,
        )
        assert verdict["exit_code"] == 1
        assert verdict["passed_threshold"] is False
        assert "FAIL" in verdict["message"]

    def test_custom_min_score(self, good_skill, history_file):
        verdict = verify_mod.run_verify(
            good_skill, min_score=99.0, history_path=history_file,
        )
        # Good skill unlikely to hit 99
        assert verdict["min_score"] == 99.0

    def test_records_history_on_pass(self, good_skill, history_file):
        verify_mod.run_verify(
            good_skill, min_score=40.0, history_path=history_file,
        )
        assert Path(history_file).exists()
        content = Path(history_file).read_text(encoding="utf-8").strip()
        assert len(content.splitlines()) == 1

    def test_records_history_on_fail(self, bad_skill, history_file):
        verify_mod.run_verify(
            bad_skill, min_score=99.0, history_path=history_file,
        )
        assert Path(history_file).exists()


# ---------------------------------------------------------------------------
# run_verify — regression checks
# ---------------------------------------------------------------------------

class TestRunVerifyRegression:
    def test_no_previous_score_passes(self, good_skill, history_file):
        verdict = verify_mod.run_verify(
            good_skill, min_score=40.0, check_regression=True,
            history_path=history_file,
        )
        assert verdict["exit_code"] == 0
        assert verdict["previous_score"] is None
        assert "no previous score" in verdict["message"]

    def test_score_improved_passes(self, good_skill, history_file):
        # Seed history with a low score
        verify_mod.append_history(
            good_skill,
            {"composite": 10.0, "grade": "F", "dimensions": {}},
            history_file,
        )
        verdict = verify_mod.run_verify(
            good_skill, min_score=40.0, check_regression=True,
            history_path=history_file,
        )
        assert verdict["exit_code"] == 0
        assert verdict["delta"] is not None
        assert verdict["delta"] > 0
        assert verdict["regression"] is False

    def test_score_regressed_fails(self, good_skill, history_file):
        # Seed history with a very high score that real scoring can't reach
        verify_mod.append_history(
            good_skill,
            {"composite": 999.0, "grade": "S", "dimensions": {}},
            history_file,
        )
        verdict = verify_mod.run_verify(
            good_skill, min_score=40.0, check_regression=True,
            history_path=history_file,
        )
        assert verdict["exit_code"] == 1
        assert verdict["regression"] is True
        assert "REGRESSION" in verdict["message"]
        assert verdict["delta"] < 0

    def test_regression_check_off_ignores_drop(self, good_skill, history_file):
        verify_mod.append_history(
            good_skill,
            {"composite": 999.0, "grade": "S", "dimensions": {}},
            history_file,
        )
        verdict = verify_mod.run_verify(
            good_skill, min_score=40.0, check_regression=False,
            history_path=history_file,
        )
        # Without --regression, score drop doesn't matter
        assert verdict["exit_code"] == 0

    def test_threshold_checked_before_regression(self, bad_skill, history_file):
        """If score < min_score, fail immediately without regression check."""
        verdict = verify_mod.run_verify(
            bad_skill, min_score=99.0, check_regression=True,
            history_path=history_file,
        )
        assert verdict["exit_code"] == 1
        assert "FAIL" in verdict["message"]
        # Regression check should not have run
        assert verdict["regression"] is False


# ---------------------------------------------------------------------------
# format_verdict
# ---------------------------------------------------------------------------

class TestFormatVerdict:
    def test_pass_message(self):
        verdict = {
            "message": "PASS: 82.5/100 [B] >= 75",
            "exit_code": 0,
            "dimensions": {},
        }
        output = verify_mod.format_verdict(verdict)
        assert "PASS" in output

    def test_fail_shows_weak_dimensions(self):
        verdict = {
            "message": "FAIL: 50.0/100 [D] < minimum 75",
            "exit_code": 1,
            "dimensions": {"structure": 30, "triggers": 90, "efficiency": 45},
        }
        output = verify_mod.format_verdict(verdict)
        assert "Weak dimensions" in output
        assert "structure" in output
        assert "efficiency" in output
        # triggers (90) should NOT appear in weak list
        assert "triggers" not in output.split("Weak")[1]

    def test_pass_no_weak_breakdown(self):
        verdict = {
            "message": "PASS: 90/100 [A] >= 75",
            "exit_code": 0,
            "dimensions": {"structure": 95, "triggers": 90},
        }
        output = verify_mod.format_verdict(verdict)
        assert "Weak" not in output


# ---------------------------------------------------------------------------
# Verdict dict structure
# ---------------------------------------------------------------------------

class TestVerdictStructure:
    def test_all_keys_present(self, good_skill, history_file):
        verdict = verify_mod.run_verify(
            good_skill, min_score=40.0, history_path=history_file,
        )
        expected_keys = {
            "skill_path", "composite", "grade", "dimensions",
            "min_score", "passed_threshold", "exit_code", "message",
            "previous_score", "delta", "regression",
        }
        assert set(verdict.keys()) == expected_keys

    def test_json_serializable(self, good_skill, history_file):
        verdict = verify_mod.run_verify(
            good_skill, min_score=40.0, history_path=history_file,
        )
        # Must not raise
        serialized = json.dumps(verdict)
        assert isinstance(serialized, str)
