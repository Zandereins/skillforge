"""Unit tests for terminal_art.py — score display formatting."""
import os

import pytest

from terminal_art import (
    score_to_grade,
    grade_colored,
    colored_bar,
    progress_bar,
    sparkline,
    format_score_display,
    _score_status,
    _dim_bar,
)


# ---------------------------------------------------------------------------
# Grade system
# ---------------------------------------------------------------------------

class TestScoreToGrade:
    def test_s_grade(self):
        assert score_to_grade(95) == "S"
        assert score_to_grade(100) == "S"

    def test_a_grade(self):
        assert score_to_grade(85) == "A"
        assert score_to_grade(94.9) == "A"

    def test_b_grade(self):
        assert score_to_grade(75) == "B"

    def test_c_grade(self):
        assert score_to_grade(65) == "C"

    def test_d_grade(self):
        assert score_to_grade(50) == "D"

    def test_f_grade(self):
        assert score_to_grade(10) == "F"
        assert score_to_grade(0) == "F"


class TestGradeColored:
    def test_no_color_env(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        assert grade_colored("S") == "[S]"
        assert grade_colored("F") == "[F]"

    def test_returns_string(self):
        result = grade_colored("A")
        assert isinstance(result, str)
        assert "A" in result


# ---------------------------------------------------------------------------
# Progress bars
# ---------------------------------------------------------------------------

class TestProgressBar:
    def test_full_bar(self):
        bar = progress_bar(100, width=10)
        assert len(bar) == 10
        assert "\u2588" * 10 == bar

    def test_empty_bar(self):
        bar = progress_bar(0, width=10)
        assert len(bar) == 10
        assert "\u2591" * 10 == bar

    def test_half_bar(self):
        bar = progress_bar(50, width=10)
        assert len(bar) == 10


class TestColoredBar:
    def test_returns_string(self):
        bar = colored_bar(80)
        assert isinstance(bar, str)

    def test_length_without_ansi(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        bar = colored_bar(80, bar_w=10)
        assert len(bar) == 10


# ---------------------------------------------------------------------------
# Sparkline
# ---------------------------------------------------------------------------

class TestSparkline:
    def test_empty(self):
        assert sparkline([]) == ""

    def test_single_value(self):
        result = sparkline([50])
        assert len(result) == 1

    def test_multiple_values(self):
        result = sparkline([0, 25, 50, 75, 100])
        assert len(result) == 5


# ---------------------------------------------------------------------------
# Score status words
# ---------------------------------------------------------------------------

class TestScoreStatus:
    def test_perfect(self):
        assert _score_status(100) == "perfect"

    def test_excellent(self):
        assert _score_status(97) == "excellent"

    def test_great(self):
        assert _score_status(90) == "great"

    def test_good(self):
        assert _score_status(78) == "good"

    def test_fair(self):
        assert _score_status(68) == "fair"

    def test_weak(self):
        assert _score_status(55) == "weak"

    def test_poor(self):
        assert _score_status(30) == "poor"


# ---------------------------------------------------------------------------
# Dimension bar
# ---------------------------------------------------------------------------

class TestDimBar:
    def test_full_score(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        bar = _dim_bar(100, width=10)
        assert len(bar) == 10
        assert "\u2591" not in bar

    def test_zero_score(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        bar = _dim_bar(0, width=10)
        assert len(bar) == 10
        assert "\u2588" not in bar

    def test_negative_score(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        bar = _dim_bar(-1, width=10)
        assert len(bar) == 10
        assert bar == "\u2591" * 10


# ---------------------------------------------------------------------------
# format_score_display (integration)
# ---------------------------------------------------------------------------

def _make_scores(structure=80, triggers=90, quality=85, edges=70,
                 efficiency=60, composability=95, clarity=100, runtime=-1):
    """Helper: build a scores dict matching scorer output shape."""
    return {
        "structure": {"score": structure, "issues": [], "details": {}},
        "triggers": {"score": triggers, "issues": [], "details": {}},
        "quality": {"score": quality, "issues": [], "details": {}},
        "edges": {"score": edges, "issues": [], "details": {}},
        "efficiency": {"score": efficiency, "issues": [], "details": {}},
        "composability": {"score": composability, "issues": [], "details": {}},
        "clarity": {"score": clarity, "issues": [], "details": {}},
        "runtime": {"score": runtime, "issues": [], "details": {}},
    }


def _make_composite(score=82.5, warnings=None):
    return {
        "score": score,
        "score_type": "structural",
        "measured_dimensions": 7,
        "total_dimensions": 8,
        "weight_coverage": 0.90,
        "unmeasured": ["runtime"],
        "warnings": warnings or [],
    }


class TestFormatScoreDisplay:
    def test_contains_version(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        output = format_score_display(
            _make_scores(), _make_composite(), version="6.3.0",
        )
        assert "v6.3.0" in output

    def test_contains_all_dimensions(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        output = format_score_display(_make_scores(), _make_composite())
        for dim in ["structure", "triggers", "quality", "edges",
                     "efficiency", "composability", "clarity"]:
            assert dim in output

    def test_skips_runtime_when_not_measured(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        output = format_score_display(_make_scores(runtime=-1), _make_composite())
        assert "runtime" not in output

    def test_shows_runtime_when_measured(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        output = format_score_display(
            _make_scores(runtime=88),
            _make_composite(score=85.0),
        )
        assert "runtime" in output

    def test_contains_composite_score(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        output = format_score_display(_make_scores(), _make_composite(score=82.5))
        assert "82.5/100" in output

    def test_contains_grade(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        output = format_score_display(_make_scores(), _make_composite(score=82.5))
        assert "[B]" in output

    def test_shows_status_words(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        output = format_score_display(
            _make_scores(structure=100, clarity=100),
            _make_composite(),
        )
        assert "perfect" in output

    def test_shows_contradictions(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        output = format_score_display(
            _make_scores(), _make_composite(),
            contradictions=["run linter", "skip tests"],
        )
        assert "2 contradictions" in output
        assert "score-inflation blocked" in output

    def test_no_contradictions_when_none(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        output = format_score_display(_make_scores(), _make_composite())
        assert "contradiction" not in output

    def test_shows_fix_count(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        output = format_score_display(
            _make_scores(), _make_composite(), fix_count=14,
        )
        assert "14 deterministic fixes" in output
        assert "/schliff:auto" in output

    def test_no_fix_line_when_zero(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        output = format_score_display(
            _make_scores(), _make_composite(), fix_count=0,
        )
        assert "deterministic fixes" not in output

    def test_shows_structural_label(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        output = format_score_display(_make_scores(), _make_composite())
        assert "Structural Score" in output

    def test_shows_unmeasured_warning(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        output = format_score_display(
            _make_scores(),
            _make_composite(warnings=["4/8 dimensions measured. Unmeasured: triggers"]),
        )
        assert "Unmeasured" in output

    def test_single_contradiction_grammar(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        output = format_score_display(
            _make_scores(), _make_composite(),
            contradictions=["run linter"],
        )
        assert "1 contradiction detected" in output
        assert "contradictions" not in output.split("1 ")[1].split("\n")[0]
