"""Unit tests for doctor.py discover_instruction_files function."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from doctor import discover_instruction_files


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_file(base: Path, *parts: str) -> Path:
    """Create an empty file at base/parts, creating parent dirs as needed."""
    p = base.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("")
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDiscoverInstructionFiles:
    """Tests for discover_instruction_files."""

    def test_finds_claude_md(self, tmp_path: Path) -> None:
        """discover_instruction_files finds CLAUDE.md."""
        _create_file(tmp_path, "CLAUDE.md")
        results = discover_instruction_files(str(tmp_path))
        assert len(results) == 1
        assert results[0]["name"] == "CLAUDE.md"

    def test_finds_cursorrules(self, tmp_path: Path) -> None:
        """discover_instruction_files finds .cursorrules."""
        _create_file(tmp_path, ".cursorrules")
        results = discover_instruction_files(str(tmp_path))
        assert len(results) == 1
        assert results[0]["name"] == ".cursorrules"

    def test_finds_agents_md(self, tmp_path: Path) -> None:
        """discover_instruction_files finds AGENTS.md."""
        _create_file(tmp_path, "AGENTS.md")
        results = discover_instruction_files(str(tmp_path))
        assert len(results) == 1
        assert results[0]["name"] == "AGENTS.md"

    def test_excludes_git_directory(self, tmp_path: Path) -> None:
        """discover_instruction_files excludes .git directory."""
        _create_file(tmp_path, ".git", "CLAUDE.md")
        _create_file(tmp_path, "CLAUDE.md")
        results = discover_instruction_files(str(tmp_path))
        assert len(results) == 1
        assert ".git" not in results[0]["path"]

    def test_excludes_node_modules(self, tmp_path: Path) -> None:
        """discover_instruction_files excludes node_modules."""
        _create_file(tmp_path, "node_modules", "pkg", "CLAUDE.md")
        results = discover_instruction_files(str(tmp_path))
        assert len(results) == 0

    def test_excludes_pycache(self, tmp_path: Path) -> None:
        """discover_instruction_files excludes __pycache__."""
        _create_file(tmp_path, "__pycache__", "CLAUDE.md")
        results = discover_instruction_files(str(tmp_path))
        assert len(results) == 0

    def test_empty_dir_returns_empty_list(self, tmp_path: Path) -> None:
        """discover_instruction_files returns empty list for empty dir."""
        results = discover_instruction_files(str(tmp_path))
        assert results == []

    def test_case_insensitive(self, tmp_path: Path) -> None:
        """discover_instruction_files is case-insensitive (finds claude.md and CLAUDE.md)."""
        _create_file(tmp_path, "sub1", "claude.md")
        _create_file(tmp_path, "sub2", "CLAUDE.md")
        results = discover_instruction_files(str(tmp_path))
        assert len(results) == 2
        names = {r["name"] for r in results}
        assert "claude.md" in names
        assert "CLAUDE.md" in names

    def test_correct_format_field(self, tmp_path: Path) -> None:
        """Results include correct format field from detect_format."""
        _create_file(tmp_path, "CLAUDE.md")
        _create_file(tmp_path, ".cursorrules")
        _create_file(tmp_path, "AGENTS.md")
        results = discover_instruction_files(str(tmp_path))
        fmt_map = {r["name"]: r["format"] for r in results}
        assert fmt_map["CLAUDE.md"] == "claude.md"
        assert fmt_map[".cursorrules"] == "cursorrules"
        assert fmt_map["AGENTS.md"] == "agents.md"

    def test_results_sorted_by_path(self, tmp_path: Path) -> None:
        """Results are sorted by absolute path."""
        _create_file(tmp_path, "z_dir", "CLAUDE.md")
        _create_file(tmp_path, "a_dir", ".cursorrules")
        results = discover_instruction_files(str(tmp_path))
        paths = [r["path"] for r in results]
        assert paths == sorted(paths)

    def test_excludes_venv_and_dotvenv(self, tmp_path: Path) -> None:
        """discover_instruction_files excludes venv/ and .venv/."""
        _create_file(tmp_path, "venv", "CLAUDE.md")
        _create_file(tmp_path, ".venv", "CLAUDE.md")
        results = discover_instruction_files(str(tmp_path))
        assert len(results) == 0

    def test_nested_subdirectory(self, tmp_path: Path) -> None:
        """discover_instruction_files finds files in nested subdirectories."""
        _create_file(tmp_path, "a", "b", "c", "CLAUDE.md")
        results = discover_instruction_files(str(tmp_path))
        assert len(results) == 1
        assert results[0]["name"] == "CLAUDE.md"
        assert "a" in results[0]["path"]
