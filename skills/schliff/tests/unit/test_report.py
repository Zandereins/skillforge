"""Unit tests for skills/schliff/scripts/report.py."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure the scripts directory is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from report import generate_report_markdown, upload_gist, _ascii_bar


# ---------------------------------------------------------------------------
# Sample data helpers
# ---------------------------------------------------------------------------

def _sample_scores() -> dict:
    return {
        "structure": {"score": 80.0, "issues": ["Missing YAML frontmatter"]},
        "triggers": {"score": 60.0, "issues": ["Too few trigger phrases", "Vague triggers"]},
        "quality": {"score": 100.0, "issues": []},
        "edges": {"score": 50.0, "issues": ["No edge-case handling", "Missing error states"]},
    }


def _sample_composite() -> dict:
    return {"score": 72.5, "warnings": ["No eval suite found"]}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGenerateReportMarkdown:
    """Tests for generate_report_markdown."""

    def test_contains_header(self) -> None:
        md = generate_report_markdown(_sample_scores(), "/tmp/SKILL.md", _sample_composite(), "B")
        assert "## Schliff Score Report" in md

    def test_contains_skill_path_and_composite(self) -> None:
        md = generate_report_markdown(_sample_scores(), "/tmp/SKILL.md", _sample_composite(), "B")
        assert "`/tmp/SKILL.md`" in md
        assert "72.5/100" in md
        assert "[B]" in md

    def test_dimension_table_has_all_dimensions(self) -> None:
        scores = _sample_scores()
        md = generate_report_markdown(scores, "/tmp/SKILL.md", _sample_composite(), "B")
        for dim in scores:
            assert dim.capitalize() in md

    def test_badge_present(self) -> None:
        md = generate_report_markdown(_sample_scores(), "/tmp/SKILL.md", _sample_composite(), "B")
        assert "img.shields.io/badge/Schliff" in md
        assert "Zandereins/schliff" in md

    def test_recommendations_capped_at_three(self) -> None:
        scores = {
            "a": {"score": 10, "issues": ["issue1", "issue2"]},
            "b": {"score": 20, "issues": ["issue3", "issue4"]},
            "c": {"score": 30, "issues": ["issue5"]},
        }
        md = generate_report_markdown(scores, "s.md", {"score": 20.0, "warnings": []}, "F")
        # Count numbered recommendation lines (1. / 2. / 3.)
        rec_lines = [l for l in md.splitlines() if l and l[0].isdigit() and ". " in l]
        assert len(rec_lines) == 3

    def test_empty_scores(self) -> None:
        md = generate_report_markdown({}, "s.md", {"score": 0.0, "warnings": []}, "F")
        assert "## Schliff Score Report" in md
        assert "No issues found." in md

    def test_includes_all_dimension_names(self) -> None:
        scores = {
            "structure": {"score": 90, "issues": []},
            "triggers": {"score": 70, "issues": []},
            "quality": {"score": 85, "issues": []},
        }
        md = generate_report_markdown(scores, "s.md", {"score": 81.7, "warnings": []}, "B")
        assert "Structure" in md
        assert "Triggers" in md
        assert "Quality" in md


class TestAsciiBars:
    """Tests for ASCII bar proportionality."""

    def test_full_score(self) -> None:
        bar = _ascii_bar(100)
        assert bar.count("\u2588") == 10
        assert len(bar) == 10

    def test_half_score(self) -> None:
        bar = _ascii_bar(50)
        assert bar.count("\u2588") == 5
        assert len(bar) == 10

    def test_zero_score(self) -> None:
        bar = _ascii_bar(0)
        assert bar.count("\u2588") == 0
        assert len(bar) == 10


class TestUploadGist:
    """Tests for upload_gist without network calls."""

    def test_returns_none_when_no_token(self, monkeypatch) -> None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        result = upload_gist("# test", token=None)
        assert result is None
