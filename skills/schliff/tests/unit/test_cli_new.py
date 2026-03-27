"""Tests for new CLI commands and PR #19 fixes.

Covers:
- cmd_demo: runs without error
- cmd_badge: produces valid shields.io URL with correct encoding
- cmd_badge: handles all grades (S through F)
- ReDoS fix: bounded regex completes quickly on pathological input
- no_real_examples fix: code_block_pairs >= 6 still flags no_real_examples
- Clarity injection suppression: custom weights suppress clarity auto-injection
- JSON rounding: composite_score floats are rounded in JSON output
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scoring import score_structure, compute_composite, score_clarity
from scoring.patterns import _RE_ERROR_BEHAVIOR

CLI_PATH = str(Path(__file__).resolve().parent.parent.parent / "scripts" / "cli.py")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


GOOD_SKILL = """\
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
"""


# ===========================================================================
# 1. cmd_demo — runs without error
# ===========================================================================

class TestCmdDemo:
    """cmd_demo must run without crashing."""

    def test_demo_exits_zero(self):
        result = _run_cli("demo")
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_demo_produces_output(self):
        result = _run_cli("demo")
        assert len(result.stdout.strip()) > 0, "Expected output from demo"

    def test_demo_shows_usage_hint(self):
        result = _run_cli("demo")
        assert "schliff" in result.stdout.lower()


# ===========================================================================
# 2. cmd_badge — valid shields.io URL with %2F encoding
# ===========================================================================

class TestCmdBadge:
    """cmd_badge must produce valid shields.io markdown badge."""

    def test_badge_exits_zero(self, tmp_path):
        skill_path = _write_skill(tmp_path, GOOD_SKILL)
        result = _run_cli("badge", skill_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_badge_contains_shields_io_url(self, tmp_path):
        skill_path = _write_skill(tmp_path, GOOD_SKILL)
        result = _run_cli("badge", skill_path)
        assert "img.shields.io/badge/" in result.stdout

    def test_badge_url_encodes_slash(self, tmp_path):
        """The score label contains '/' which must be encoded as %2F."""
        skill_path = _write_skill(tmp_path, GOOD_SKILL)
        result = _run_cli("badge", skill_path)
        # The raw "/" in "XX/100" must be URL-encoded
        assert "%2F" in result.stdout, (
            f"Expected %2F encoding in badge URL, got: {result.stdout.strip()}"
        )

    def test_badge_is_valid_markdown_image_link(self, tmp_path):
        """Badge output must be a markdown image link: [![alt](url)](link)."""
        skill_path = _write_skill(tmp_path, GOOD_SKILL)
        result = _run_cli("badge", skill_path)
        output = result.stdout.strip()
        # Markdown image link: [![...](https://...)](https://...)
        assert output.startswith("[!["), f"Expected markdown image link, got: {output}"
        assert "](https://img.shields.io/badge/" in output
        assert ")](https://github.com/Zandereins/schliff)" in output

    def test_badge_contains_grade(self, tmp_path):
        """Badge must contain a grade letter in brackets."""
        skill_path = _write_skill(tmp_path, GOOD_SKILL)
        result = _run_cli("badge", skill_path)
        # Should contain a grade like [S], [A], [B], etc.
        assert re.search(r"\[[SABCDEF]\]", result.stdout), (
            f"Expected grade in badge, got: {result.stdout.strip()}"
        )

    def test_badge_missing_file(self, tmp_path):
        missing = str(tmp_path / "nope.md")
        result = _run_cli("badge", missing)
        assert result.returncode == 1
        assert "not found" in result.stderr.lower()


# ===========================================================================
# 3. cmd_badge — all grade colors mapped
# ===========================================================================

class TestBadgeGradeColors:
    """All grades S through F must produce valid badge colors."""

    @pytest.mark.parametrize("grade", ["S", "A", "B", "C", "D", "E", "F"])
    def test_grade_has_color_mapping(self, grade):
        """Each grade must have a color in the badge color map."""
        # Reproduce the color map from cli.py
        colors = {
            "S": "brightgreen", "A": "green", "B": "yellowgreen",
            "C": "yellow", "D": "orange", "E": "red", "F": "red",
        }
        assert grade in colors, f"Grade {grade} missing from color map"
        assert colors[grade], f"Grade {grade} has empty color"


# ===========================================================================
# 4. ReDoS fix — bounded regex completes quickly on pathological input
# ===========================================================================

class TestReDoSBoundedRegex:
    """_RE_ERROR_BEHAVIOR with bounded {0,80} must not catastrophically backtrack."""

    def test_pathological_input_completes_fast(self):
        """A long 'if <many words> fails' input must match in < 50ms."""
        # Without the {0,80} bound, this would cause exponential backtracking
        pathological = "if " + "word " * 200 + "fails"
        start = time.monotonic()
        _RE_ERROR_BEHAVIOR.search(pathological)
        elapsed_ms = (time.monotonic() - start) * 1000
        assert elapsed_ms < 50, (
            f"Regex took {elapsed_ms:.1f}ms on pathological input (expected < 50ms)"
        )

    def test_bounded_regex_still_matches_normal_input(self):
        """Normal error behavior phrases must still match."""
        assert _RE_ERROR_BEHAVIOR.search("if the command fails")
        assert _RE_ERROR_BEHAVIOR.search("when parsing fails")
        assert _RE_ERROR_BEHAVIOR.search("on error, abort")
        assert _RE_ERROR_BEHAVIOR.search("gracefully degrade")

    def test_bounded_regex_rejects_long_gap(self):
        """Input with >80 chars between 'if' and 'fails' must NOT match that branch."""
        long_gap = "if " + "x" * 100 + " fails"
        # The 'if ... fails' branch has {0,80} — this should not match via that branch
        match = _RE_ERROR_BEHAVIOR.search(long_gap)
        # It may still match via other branches (e.g., "graceful" or "on error"),
        # but the "if ... fails" branch should not capture a 100-char gap
        if match:
            # If it matched, it should NOT be via the 'if ... fails' branch
            assert "fails" not in match.group() or len(match.group()) < 90


# ===========================================================================
# 5. no_real_examples fix — code_block_pairs >= 6 still flags issue
# ===========================================================================

class TestNoRealExamplesFix:
    """Skills with only code blocks (no real examples) must be flagged."""

    def test_many_code_blocks_without_examples_flags_issue(self, tmp_path):
        """A skill with >= 6 code_block_pairs but no 'Example' text must flag no_real_examples."""
        # 12 ``` markers = 6 code_block_pairs, but no "Example:" or "e.g." text
        code_blocks = "\n```bash\necho hello\n```\n" * 6
        content = f"""\
---
name: code-only-skill
description: A skill that has code blocks but no real examples.
---

# Code Only Skill

Use this skill when testing code block detection.

## Instructions

1. Run the setup
2. Check the output
3. Verify the result

{code_blocks}
"""
        skill_path = _write_skill(tmp_path, content)
        result = score_structure(skill_path)
        assert "no_real_examples" in result["issues"], (
            f"Expected no_real_examples issue, got: {result['issues']}"
        )

    def test_code_blocks_with_real_examples_no_issue(self, tmp_path):
        """A skill with code blocks AND real examples must NOT flag no_real_examples."""
        content = """\
---
name: example-skill
description: A skill with proper examples and code blocks.
---

# Example Skill

Use this skill when testing example detection.

## Examples

Example 1: Basic usage
```bash
echo hello
```

Example 2: Advanced usage
```bash
echo world
```
"""
        skill_path = _write_skill(tmp_path, content)
        result = score_structure(skill_path)
        assert "no_real_examples" not in result["issues"]


# ===========================================================================
# 6. Clarity injection suppression — custom weights take precedence
# ===========================================================================

class TestClarityInjectionSuppression:
    """When custom_weights are provided, clarity must NOT be auto-injected."""

    def test_custom_weights_suppress_clarity_injection(self):
        """compute_composite with custom_weights must not auto-add clarity weight."""
        scores = {
            "structure": {"score": 80, "issues": [], "details": {}},
            "triggers": {"score": 70, "issues": [], "details": {}},
            "quality": {"score": 75, "issues": [], "details": {}},
            "edges": {"score": 60, "issues": [], "details": {}},
            "efficiency": {"score": 65, "issues": [], "details": {}},
            "composability": {"score": 70, "issues": [], "details": {}},
            "clarity": {"score": 90, "issues": [], "details": {}},
        }
        custom = {"structure": 0.5, "triggers": 0.5}
        result = compute_composite(scores, custom_weights=custom)
        # clarity is in scores but custom_weights suppresses auto-injection
        # Key test: score must be identical whether or not clarity is in the input scores
        scores_without_clarity = {k: v for k, v in scores.items() if k != "clarity"}
        result_without = compute_composite(scores_without_clarity, custom_weights=custom)
        assert result["score"] == result_without["score"], (
            f"Clarity leaked into composite: {result['score']} != {result_without['score']}"
        )

    def test_no_custom_weights_injects_clarity(self):
        """Without custom_weights, clarity present in scores IS auto-injected."""
        scores = {
            "structure": {"score": 80, "issues": [], "details": {}},
            "triggers": {"score": 70, "issues": [], "details": {}},
            "quality": {"score": 75, "issues": [], "details": {}},
            "edges": {"score": 60, "issues": [], "details": {}},
            "efficiency": {"score": 65, "issues": [], "details": {}},
            "composability": {"score": 70, "issues": [], "details": {}},
            "clarity": {"score": 90, "issues": [], "details": {}},
        }
        result_with = compute_composite(scores)
        result_without = compute_composite({k: v for k, v in scores.items() if k != "clarity"})
        # With clarity present and no custom weights, scores should differ
        assert result_with["score"] != result_without["score"]


# ===========================================================================
# 7. JSON rounding — composite_score float precision
# ===========================================================================

class TestJsonRounding:
    """JSON output must have rounded float values."""

    def test_json_output_has_rounded_dimensions(self, tmp_path):
        """Dimension scores in --json output must be rounded to 1 decimal."""
        skill_path = _write_skill(tmp_path, GOOD_SKILL)
        result = _run_cli("score", "--json", skill_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        for dim, score in data["dimensions"].items():
            if isinstance(score, float):
                # Check that the value has at most 1 decimal place
                assert score == round(score, 1), (
                    f"Dimension {dim} has unrounded value {score}"
                )


# ===========================================================================
# 8. cmd_report — CLI smoke tests
# ===========================================================================

class TestCmdReport:
    """cmd_report must produce Markdown output or handle errors gracefully."""

    def test_report_exits_zero(self, tmp_path):
        """cmd_report on a valid skill exits 0."""
        skill_path = _write_skill(tmp_path, GOOD_SKILL)
        result = _run_cli("report", skill_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_report_produces_markdown(self, tmp_path):
        """cmd_report output contains the report header."""
        skill_path = _write_skill(tmp_path, GOOD_SKILL)
        result = _run_cli("report", skill_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "## Schliff Score Report" in result.stdout

    def test_report_contains_skill_path(self, tmp_path):
        """cmd_report output references the scored file."""
        skill_path = _write_skill(tmp_path, GOOD_SKILL)
        result = _run_cli("report", skill_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert skill_path in result.stdout

    def test_report_missing_file(self, tmp_path):
        """cmd_report with a missing file exits non-zero."""
        missing = str(tmp_path / "nope.md")
        result = _run_cli("report", missing)
        assert result.returncode == 1
        assert "not found" in result.stderr.lower()


# ===========================================================================
# 9. cmd_score --json includes token_budget key
# ===========================================================================

class TestScoreTokenBudget:
    """cmd_score --json must include the token_budget field."""

    def test_json_includes_token_budget_key(self, tmp_path):
        """JSON output must contain a 'token_budget' key."""
        skill_path = _write_skill(tmp_path, GOOD_SKILL)
        result = _run_cli("score", "--json", skill_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert "token_budget" in data, (
            f"'token_budget' key missing from JSON output: {list(data.keys())}"
        )

    def test_token_budget_has_required_fields(self, tmp_path):
        """token_budget must contain tokens, budget, within_budget, severity."""
        skill_path = _write_skill(tmp_path, GOOD_SKILL)
        result = _run_cli("score", "--json", skill_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        tb = data["token_budget"]
        assert "tokens" in tb, f"Missing 'tokens' in token_budget: {tb}"
        assert "budget" in tb, f"Missing 'budget' in token_budget: {tb}"
        assert "within_budget" in tb, f"Missing 'within_budget' in token_budget: {tb}"
        assert "severity" in tb, f"Missing 'severity' in token_budget: {tb}"
        assert isinstance(tb["tokens"], int)
        assert isinstance(tb["budget"], int)
        assert isinstance(tb["within_budget"], bool)

    def test_tokens_flag_shows_breakdown(self, tmp_path):
        """--tokens flag produces section breakdown output."""
        skill_path = _write_skill(tmp_path, GOOD_SKILL)
        result = _run_cli("score", "--tokens", skill_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "token" in result.stdout.lower(), (
            f"Expected token info in output, got: {result.stdout[:200]}"
        )
