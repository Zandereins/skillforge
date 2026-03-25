"""Unit tests for doctor.py recommendations."""
from pathlib import Path

import pytest

from doctor import _score_single_skill


def _write_skill(tmp_path, lines=100, has_refs=False):
    """Helper to create a test skill with configurable size and refs."""
    content_lines = [
        "---",
        "name: test-skill",
        "description: A test skill for unit testing. Use when testing doctor recommendations.",
        "---",
        "",
        "# Test Skill",
        "",
        "Use this skill when you need to test doctor functionality.",
        "",
        "## Instructions",
        "",
        "1. Read the input",
        "2. Process the data",
        "3. Return the result",
        "",
        "## Examples",
        "",
        "Example 1: Basic usage",
        "Input: test data",
        "Output: processed result",
        "",
        "Example 2: Edge case",
        "Input: empty data",
        "Output: error message",
        "",
    ]
    # Pad with realistic content to reach target line count
    while len(content_lines) < lines:
        content_lines.append(f"- Step {len(content_lines)}: process item")

    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir(exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("\n".join(content_lines), encoding="utf-8")

    if has_refs:
        refs_dir = skill_dir / "references"
        refs_dir.mkdir()
        (refs_dir / "example.md").write_text(
            "# Reference\nSome content.", encoding="utf-8"
        )

    return str(skill_file)


class TestDoctorRecommendations:
    """Test references/ extraction recommendations in doctor."""

    def test_long_skill_no_refs_gets_recommendation(self, tmp_path):
        """Skill >300 lines without references/ should get a recommendation."""
        path = _write_skill(tmp_path, lines=350, has_refs=False)
        result = _score_single_skill(path)
        assert len(result["recommendations"]) == 1
        assert "references/" in result["recommendations"][0]

    def test_long_skill_with_refs_no_recommendation(self, tmp_path):
        """Skill >300 lines WITH references/ should NOT get a recommendation."""
        path = _write_skill(tmp_path, lines=350, has_refs=True)
        result = _score_single_skill(path)
        assert len(result["recommendations"]) == 0

    def test_short_skill_no_refs_no_recommendation(self, tmp_path):
        """Skill <300 lines without references/ should NOT get a recommendation."""
        path = _write_skill(tmp_path, lines=150, has_refs=False)
        result = _score_single_skill(path)
        assert len(result["recommendations"]) == 0

    def test_recommendation_includes_line_count(self, tmp_path):
        """Recommendation text should include the actual line count."""
        path = _write_skill(tmp_path, lines=400, has_refs=False)
        result = _score_single_skill(path)
        assert "400" in result["recommendations"][0]
