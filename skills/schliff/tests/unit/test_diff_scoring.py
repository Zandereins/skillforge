"""Tests for scoring/diff.py — score_diff() and explain_score_change().

Covers:
1. score_diff() with a valid git ref returns expected structure
2. score_diff() with an invalid ref returns available: False
3. score_diff() classifies signal/noise lines correctly
4. explain_score_change() with no changes returns empty list
5. explain_score_change() with large delta returns explanation
"""
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from scoring.diff import score_diff, explain_score_change


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_diff_output(added: list[str], removed: list[str]) -> str:
    """Build a minimal unified diff string for mocking git output."""
    lines = [
        "diff --git a/SKILL.md b/SKILL.md",
        "--- a/SKILL.md",
        "+++ b/SKILL.md",
        "@@ -1,5 +1,5 @@",
    ]
    for line in removed:
        lines.append(f"-{line}")
    for line in added:
        lines.append(f"+{line}")
    return "\n".join(lines) + "\n"


def _mock_run_ok(stdout: str):
    """Return a mock subprocess.CompletedProcess with returncode=0."""
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = stdout
    mock.stderr = ""
    return mock


def _mock_run_fail():
    """Return a mock subprocess.CompletedProcess with returncode=128 (git error)."""
    mock = MagicMock()
    mock.returncode = 128
    mock.stdout = ""
    mock.stderr = "fatal: ambiguous argument 'BADREF': unknown revision"
    return mock


# ---------------------------------------------------------------------------
# 1. score_diff() with valid git ref returns expected structure
# ---------------------------------------------------------------------------

class TestScoreDiffStructure:
    """score_diff must return a well-formed dict when git succeeds."""

    def test_returns_available_true(self):
        """A successful git diff must set available=True."""
        diff_output = _make_diff_output(
            added=["Run the analysis."],
            removed=["You might want to consider running this."],
        )
        with patch("subprocess.run", return_value=_mock_run_ok(diff_output)):
            result = score_diff("SKILL.md", "HEAD~1")
        assert result["available"] is True

    def test_returns_diff_ref_key(self):
        """result must contain the diff_ref used."""
        diff_output = _make_diff_output(added=["Check the output."], removed=[])
        with patch("subprocess.run", return_value=_mock_run_ok(diff_output)):
            result = score_diff("SKILL.md", "HEAD~1")
        assert result["diff_ref"] == "HEAD~1"

    def test_returns_added_and_removed_dicts(self):
        """result must contain 'added' and 'removed' classification dicts."""
        diff_output = _make_diff_output(
            added=["Run the analysis."], removed=["Note that this step is important."]
        )
        with patch("subprocess.run", return_value=_mock_run_ok(diff_output)):
            result = score_diff("SKILL.md", "HEAD~1")
        assert "added" in result
        assert "removed" in result
        for section in ("added", "removed"):
            for key in ("signal", "noise", "neutral", "total"):
                assert key in result[section], f"missing key '{key}' in result['{section}']"

    def test_returns_net_change_dict(self):
        """result must contain a 'net_change' dict with signal, noise, lines."""
        diff_output = _make_diff_output(added=["Verify the result."], removed=[])
        with patch("subprocess.run", return_value=_mock_run_ok(diff_output)):
            result = score_diff("SKILL.md", "HEAD~1")
        assert "net_change" in result
        for key in ("signal", "noise", "lines"):
            assert key in result["net_change"]

    def test_net_lines_is_added_minus_removed(self):
        """net_change.lines must equal added.total - removed.total."""
        added = ["Run the analysis.", "Check the output."]
        removed = ["Note that this."]
        diff_output = _make_diff_output(added=added, removed=removed)
        with patch("subprocess.run", return_value=_mock_run_ok(diff_output)):
            result = score_diff("SKILL.md", "HEAD~1")
        assert result["net_change"]["lines"] == result["added"]["total"] - result["removed"]["total"]


# ---------------------------------------------------------------------------
# 2. score_diff() with invalid ref returns available: False
# ---------------------------------------------------------------------------

class TestScoreDiffInvalidRef:
    """Invalid or dangerous refs must produce available=False without crashing."""

    @pytest.mark.parametrize("bad_ref", [
        "-evil",               # starts with dash (blocked by guard)
        "HEAD~1; rm -rf /",   # shell injection characters
        "ref with spaces",    # spaces not in allowed pattern
        "HEAD~1|cat",         # pipe character
        "HEAD~1&whoami",      # ampersand
    ])
    def test_invalid_ref_format_returns_available_false(self, bad_ref):
        """Refs with dangerous characters must be rejected before calling git."""
        result = score_diff("SKILL.md", bad_ref)
        assert result["available"] is False
        assert "error" in result or "reason" in result

    def test_git_nonzero_exit_returns_available_false(self):
        """When git returns a non-zero exit code, available must be False."""
        with patch("subprocess.run", return_value=_mock_run_fail()):
            result = score_diff("SKILL.md", "BADREF123")
        assert result["available"] is False

    def test_empty_diff_output_returns_available_false(self):
        """When git returns success but empty stdout, available must be False."""
        mock = _mock_run_ok("")
        with patch("subprocess.run", return_value=mock):
            result = score_diff("SKILL.md", "HEAD~1")
        assert result["available"] is False

    def test_git_not_found_returns_available_false(self):
        """FileNotFoundError (git not on PATH) must return available=False."""
        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            result = score_diff("SKILL.md", "HEAD~1")
        assert result["available"] is False

    def test_git_timeout_returns_available_false(self):
        """subprocess.TimeoutExpired must be caught and return available=False."""
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["git"], timeout=10),
        ):
            result = score_diff("SKILL.md", "HEAD~1")
        assert result["available"] is False


# ---------------------------------------------------------------------------
# 3. score_diff() classifies signal/noise lines correctly
# ---------------------------------------------------------------------------

class TestScoreDiffClassification:
    """Lines must be placed in signal, noise, or neutral buckets correctly."""

    def test_imperative_verb_lines_are_signal(self):
        """Lines starting with known imperative verbs must count as signal."""
        signal_lines = [
            "Run the analysis script.",
            "Check the output file.",
            "Verify the result matches expectations.",
            "Create a new configuration file.",
            "Execute the build pipeline.",
        ]
        diff_output = _make_diff_output(added=signal_lines, removed=[])
        with patch("subprocess.run", return_value=_mock_run_ok(diff_output)):
            result = score_diff("SKILL.md", "HEAD~1")
        assert result["added"]["signal"] == len(signal_lines)
        assert result["added"]["noise"] == 0

    def test_hedging_lines_are_noise(self):
        """Lines with hedging phrases must count as noise."""
        noise_lines = [
            "You might want to consider running this step.",
            "It is important to note that this may fail.",
            "Please note that configuration is required.",
            "Don't forget to save your work.",
            "Always test your changes before deploying.",
        ]
        diff_output = _make_diff_output(added=noise_lines, removed=[])
        with patch("subprocess.run", return_value=_mock_run_ok(diff_output)):
            result = score_diff("SKILL.md", "HEAD~1")
        assert result["added"]["noise"] == len(noise_lines)

    def test_example_marker_lines_are_signal(self):
        """Lines containing example markers must count as signal."""
        example_lines = [
            "Example 1: basic usage",
            "For example, run the script with --verbose.",
            "e.g., python3 score-skill.py SKILL.md",
        ]
        diff_output = _make_diff_output(added=example_lines, removed=[])
        with patch("subprocess.run", return_value=_mock_run_ok(diff_output)):
            result = score_diff("SKILL.md", "HEAD~1")
        assert result["added"]["signal"] == len(example_lines)

    def test_neutral_lines_counted_correctly(self):
        """Lines that match neither signal nor noise must go into neutral."""
        neutral_lines = [
            "# Header",
            "",
            "Some plain description text here.",
        ]
        diff_output = _make_diff_output(added=neutral_lines, removed=[])
        with patch("subprocess.run", return_value=_mock_run_ok(diff_output)):
            result = score_diff("SKILL.md", "HEAD~1")
        assert result["added"]["neutral"] == len(neutral_lines)
        assert result["added"]["signal"] == 0
        assert result["added"]["noise"] == 0

    def test_net_signal_positive_when_signal_added(self):
        """Adding signal lines and removing noise must produce net_signal > 0."""
        diff_output = _make_diff_output(
            added=["Run the analysis.", "Check the output."],
            removed=["You might want to consider this."],
        )
        with patch("subprocess.run", return_value=_mock_run_ok(diff_output)):
            result = score_diff("SKILL.md", "HEAD~1")
        assert result["net_change"]["signal"] > 0
        assert result["net_change"]["noise"] < 0

    def test_removed_lines_tracked_separately(self):
        """Removed lines must populate result['removed'], not result['added']."""
        diff_output = _make_diff_output(
            added=[],
            removed=["Run the analysis."],
        )
        with patch("subprocess.run", return_value=_mock_run_ok(diff_output)):
            result = score_diff("SKILL.md", "HEAD~1")
        assert result["removed"]["signal"] == 1
        assert result["added"]["total"] == 0

    def test_total_counts_match_line_counts(self):
        """added.total and removed.total must equal the number of diff lines."""
        added = ["Run this.", "Check that.", "Verify output."]
        removed = ["Note that something.", "Maybe consider this."]
        diff_output = _make_diff_output(added=added, removed=removed)
        with patch("subprocess.run", return_value=_mock_run_ok(diff_output)):
            result = score_diff("SKILL.md", "HEAD~1")
        assert result["added"]["total"] == len(added)
        assert result["removed"]["total"] == len(removed)


# ---------------------------------------------------------------------------
# 4. explain_score_change() with no changes returns empty list
# ---------------------------------------------------------------------------

class TestExplainScoreChangeNoChanges:
    """When all dimension deltas are < 0.5, explain_score_change must return []."""

    def _no_diff(self) -> dict:
        return {"available": False, "reason": "no changes between refs"}

    def test_identical_scores_returns_empty_list(self):
        """Same old and new scores -> no explanations."""
        old = {"structure": 80, "efficiency": 70}
        new = {"structure": 80, "efficiency": 70}
        result = explain_score_change(old, new, self._no_diff())
        assert result == []

    def test_tiny_delta_below_threshold_returns_empty_list(self):
        """Delta of 0.4 is below the 0.5 threshold and must be ignored."""
        old = {"structure": 80.0}
        new = {"structure": 80.4}
        result = explain_score_change(old, new, self._no_diff())
        assert result == []

    def test_empty_old_and_new_scores_returns_empty_list(self):
        """Both old and new empty -> nothing to explain."""
        result = explain_score_change({}, {}, self._no_diff())
        assert result == []

    def test_returns_list_type(self):
        """Return type must always be list."""
        result = explain_score_change({"structure": 80}, {"structure": 80}, self._no_diff())
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# 5. explain_score_change() with large delta returns explanation
# ---------------------------------------------------------------------------

class TestExplainScoreChangeLargeDelta:
    """Deltas >= 0.5 must produce explanation entries."""

    def _no_diff(self) -> dict:
        return {"available": False}

    def _available_diff(self, net_signal=0, net_noise=0, net_lines=0) -> dict:
        return {
            "available": True,
            "net_change": {
                "signal": net_signal,
                "noise": net_noise,
                "lines": net_lines,
            },
        }

    def test_large_positive_delta_produces_entry(self):
        """An increase of 10 points must generate an explanation entry."""
        old = {"structure": 60}
        new = {"structure": 70}
        result = explain_score_change(old, new, self._no_diff())
        assert len(result) == 1
        assert result[0]["dimension"] == "structure"
        assert result[0]["delta"] == pytest.approx(10.0)

    def test_large_negative_delta_produces_entry(self):
        """A decrease of 15 points must generate an explanation with negative delta."""
        old = {"efficiency": 80}
        new = {"efficiency": 65}
        result = explain_score_change(old, new, self._no_diff())
        assert len(result) == 1
        assert result[0]["delta"] == pytest.approx(-15.0)

    def test_explanation_contains_required_keys(self):
        """Each explanation entry must contain dimension, old, new, delta, explanation."""
        old = {"quality": 50}
        new = {"quality": 75}
        result = explain_score_change(old, new, self._no_diff())
        assert len(result) == 1
        entry = result[0]
        for key in ("dimension", "old", "new", "delta", "explanation"):
            assert key in entry, f"missing key '{key}' in explanation entry"

    def test_multiple_changed_dims_all_explained(self):
        """Each dimension with delta >= 0.5 must produce a separate entry."""
        old = {"structure": 60, "efficiency": 80, "quality": 70}
        new = {"structure": 75, "efficiency": 60, "quality": 70}
        result = explain_score_change(old, new, self._no_diff())
        dims_in_result = {e["dimension"] for e in result}
        assert "structure" in dims_in_result
        assert "efficiency" in dims_in_result
        assert "quality" not in dims_in_result  # delta == 0, below threshold

    def test_efficiency_noise_removed_appended_when_diff_available(self):
        """When diff shows noise removed, efficiency explanation must mention it."""
        old = {"efficiency": 60}
        new = {"efficiency": 80}
        diff = self._available_diff(net_noise=-3)
        result = explain_score_change(old, new, diff)
        assert len(result) == 1
        assert "noise removed" in result[0]["explanation"]

    def test_efficiency_signal_added_appended_when_diff_available(self):
        """When diff shows signal added, efficiency explanation must mention it."""
        old = {"efficiency": 55}
        new = {"efficiency": 70}
        diff = self._available_diff(net_signal=4)
        result = explain_score_change(old, new, diff)
        assert len(result) == 1
        assert "signal added" in result[0]["explanation"]

    def test_structure_file_shortened_appended_when_diff_available(self):
        """When diff shows fewer lines, structure explanation must mention it."""
        old = {"structure": 70}
        new = {"structure": 55}
        diff = self._available_diff(net_lines=-20)
        result = explain_score_change(old, new, diff)
        assert len(result) == 1
        assert "file shortened" in result[0]["explanation"]

    def test_new_dimension_not_in_old_treated_as_delta_from_zero(self):
        """A dimension present only in new_scores is treated as old=0."""
        old = {}
        new = {"structure": 80}
        result = explain_score_change(old, new, self._no_diff())
        assert len(result) == 1
        assert result[0]["old"] == 0
        assert result[0]["new"] == 80

    def test_result_is_sorted_alphabetically_by_dimension(self):
        """explain_score_change iterates sorted dims; result order must be alphabetical."""
        old = {"zzz": 0, "aaa": 0, "mmm": 0}
        new = {"zzz": 100, "aaa": 100, "mmm": 100}
        result = explain_score_change(old, new, self._no_diff())
        dims = [e["dimension"] for e in result]
        assert dims == sorted(dims)
