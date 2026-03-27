"""Unit tests for the Schliff Track module — history, sparkline, regression detection."""
import json
import subprocess
from pathlib import Path

import pytest

import track


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def hist_dir(tmp_path, monkeypatch):
    """Redirect all history I/O to a temp directory and stub git commands."""
    hist_file = tmp_path / ".schliff" / "history.json"

    monkeypatch.setattr(track, "get_history_path", lambda _sp: hist_file)
    monkeypatch.setattr(track, "get_current_commit", lambda: "abc1234")

    return hist_file


# ---------------------------------------------------------------------------
# record_score
# ---------------------------------------------------------------------------

def test_record_creates_history_file(hist_dir):
    """record_score creates .schliff/history.json if it doesn't exist."""
    assert not hist_dir.exists()

    track.record_score("skill.md", 72.3, "B", {"structure": 80, "triggers": 65})

    assert hist_dir.exists()
    entries = json.loads(hist_dir.read_text())
    assert len(entries) == 1
    assert entries[0]["composite"] == 72.3
    assert entries[0]["grade"] == "B"


def test_record_appends_entry(hist_dir, monkeypatch):
    """Second call with a different commit appends a new entry."""
    track.record_score("skill.md", 70.0, "B", {"structure": 70})

    monkeypatch.setattr(track, "get_current_commit", lambda: "def5678")
    track.record_score("skill.md", 75.0, "B+", {"structure": 75})

    entries = json.loads(hist_dir.read_text())
    assert len(entries) == 2
    assert entries[0]["commit"] == "abc1234"
    assert entries[1]["commit"] == "def5678"


def test_record_deduplicates_same_commit(hist_dir):
    """Calling twice with the same commit replaces instead of appending."""
    track.record_score("skill.md", 70.0, "B", {"structure": 70})
    track.record_score("skill.md", 75.0, "B+", {"structure": 75})

    entries = json.loads(hist_dir.read_text())
    assert len(entries) == 1
    assert entries[0]["composite"] == 75.0


# ---------------------------------------------------------------------------
# load_history
# ---------------------------------------------------------------------------

def test_load_missing_file_returns_empty(tmp_path, monkeypatch):
    """load_history on a nonexistent path returns an empty list."""
    monkeypatch.setattr(
        track, "get_history_path",
        lambda _sp: tmp_path / "nope" / "history.json",
    )
    assert track.load_history("skill.md") == []


def test_load_filters_by_skill(hist_dir, monkeypatch):
    """History with multiple skills — filter returns only matching entries."""
    track.record_score("alpha.md", 60.0, "C", {"structure": 60})

    monkeypatch.setattr(track, "get_current_commit", lambda: "fff0001")
    track.record_score("beta.md", 80.0, "A", {"structure": 80})

    result = track.load_history("alpha.md")
    assert len(result) == 1
    assert result[0]["skill"] == "alpha.md"


# ---------------------------------------------------------------------------
# render_sparkline
# ---------------------------------------------------------------------------

def test_sparkline_characters():
    """Specific scores produce expected sparkline characters."""
    history = [
        {"composite": 0.0},
        {"composite": 50.0},
        {"composite": 100.0},
    ]
    spark = track.render_sparkline(history)
    assert spark[0] == "▁"   # 0   → lowest block
    assert spark[1] == "▄"   # 50  → mid block  (int(50/100*8) = 4 → index 4)
    assert spark[2] == "█"   # 100 → highest block


def test_sparkline_empty_history():
    """Empty list returns an empty string."""
    assert track.render_sparkline([]) == ""


def test_sparkline_sampling():
    """History longer than width gets sampled down to width."""
    history = [{"composite": float(i)} for i in range(100)]
    spark = track.render_sparkline(history, width=10)
    assert len(spark) == 10


# ---------------------------------------------------------------------------
# check_regression
# ---------------------------------------------------------------------------

def test_regression_detected():
    """Drop of 10 points with threshold 5 is flagged as regression."""
    history = [
        {"composite": 80.0},
        {"composite": 70.0},
    ]
    regressed, delta = track.check_regression(history, threshold=5.0)
    assert regressed is True
    assert delta == pytest.approx(-10.0)


def test_regression_not_detected():
    """Drop of 2 points with threshold 5 is not flagged."""
    history = [
        {"composite": 80.0},
        {"composite": 78.0},
    ]
    regressed, delta = track.check_regression(history, threshold=5.0)
    assert regressed is False
    assert delta == pytest.approx(-2.0)


def test_regression_too_few_entries():
    """Single entry cannot regress."""
    regressed, delta = track.check_regression([{"composite": 80.0}])
    assert regressed is False
    assert delta == 0.0


# ---------------------------------------------------------------------------
# format_track_report
# ---------------------------------------------------------------------------

def test_format_report_contains_sections(hist_dir, monkeypatch):
    """Report includes Sparkline, Latest, Peak, Lowest, and Trend sections."""
    track.record_score("skill.md", 60.0, "C", {"structure": 60})

    monkeypatch.setattr(track, "get_current_commit", lambda: "bbb2222")
    track.record_score("skill.md", 80.0, "A", {"structure": 80})

    report = track.format_track_report("skill.md")

    assert "Sparkline:" in report
    assert "Latest:" in report
    assert "Peak:" in report
    assert "Lowest:" in report
    assert "Trend:" in report


# ---------------------------------------------------------------------------
# Error handling & fallback tests (added by audit)
# ---------------------------------------------------------------------------

def test_get_history_path_no_git(tmp_path, monkeypatch):
    """Falls back to skill's parent dir when git is unavailable."""
    def _failing_run(*args, **kwargs):
        raise subprocess.SubprocessError("no git")
    monkeypatch.setattr(subprocess, "run", _failing_run)

    skill = str(tmp_path / "skills" / "my_skill.md")
    result = track.get_history_path(skill)
    expected = Path(skill).resolve().parent / ".schliff" / "history.json"
    assert result == expected


def test_get_current_commit_no_git(monkeypatch):
    """Returns 'no-git' when git is unavailable."""
    def _failing_run(*args, **kwargs):
        raise OSError("no git")
    monkeypatch.setattr(subprocess, "run", _failing_run)

    assert track.get_current_commit() == "no-git"


def test_load_history_corrupted_json(hist_dir):
    """Corrupted JSON returns empty list instead of crashing."""
    hist_dir.parent.mkdir(parents=True, exist_ok=True)
    hist_dir.write_text("{broken json!!", encoding="utf-8")

    result = track.load_history("skill.md")
    assert result == []


def test_load_history_non_list_json(hist_dir):
    """JSON that isn't a list returns empty."""
    hist_dir.parent.mkdir(parents=True, exist_ok=True)
    hist_dir.write_text('{"not": "a list"}', encoding="utf-8")

    result = track.load_history("skill.md")
    assert result == []


def test_record_score_non_list_json_resets(hist_dir):
    """Non-list JSON in history file is treated as empty."""
    hist_dir.parent.mkdir(parents=True, exist_ok=True)
    hist_dir.write_text('"just a string"', encoding="utf-8")

    track.record_score("skill.md", 80.0, "A", {"structure": 80})

    entries = json.loads(hist_dir.read_text())
    assert len(entries) == 1
    assert entries[0]["composite"] == 80.0


def test_format_report_empty_history():
    """Empty history shows 'No history recorded yet.'"""
    report = track.format_track_report("skill.md", history=[])
    assert "No history recorded yet" in report


def test_sparkline_clamps_out_of_range():
    """Out-of-range scores are clamped to 0-100."""
    history = [{"composite": -50.0}, {"composite": 200.0}]
    spark = track.render_sparkline(history)
    assert spark[0] == "▁"  # clamped to 0
    assert spark[1] == "█"  # clamped to 100


# ---------------------------------------------------------------------------
# Edge case tests (added by audit iteration 2)
# ---------------------------------------------------------------------------

def test_record_score_nan_composite(hist_dir):
    """NaN composite is coerced to 0.0, not written as invalid JSON."""
    track.record_score("skill.md", float("nan"), "?", {"structure": 50})

    entries = json.loads(hist_dir.read_text())
    assert len(entries) == 1
    assert entries[0]["composite"] == 0.0


def test_record_score_inf_composite(hist_dir):
    """Infinity composite is coerced to 0.0."""
    track.record_score("skill.md", float("inf"), "?", {"structure": 50})

    entries = json.loads(hist_dir.read_text())
    assert entries[0]["composite"] == 0.0


def test_record_score_non_numeric_dimensions(hist_dir):
    """Non-numeric dimension values default to 0 instead of crashing."""
    track.record_score("skill.md", 70.0, "B", {"quality": "high", "structure": 80})

    entries = json.loads(hist_dir.read_text())
    assert entries[0]["dimensions"]["quality"] == 0
    assert entries[0]["dimensions"]["structure"] == 80


def test_sparkline_width_zero():
    """width=0 returns empty string instead of ZeroDivisionError."""
    history = [{"composite": 50.0}]
    assert track.render_sparkline(history, width=0) == ""


def test_sparkline_width_negative():
    """Negative width returns empty string."""
    history = [{"composite": 50.0}]
    assert track.render_sparkline(history, width=-1) == ""
