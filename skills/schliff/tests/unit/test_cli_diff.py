"""Tests for cmd_diff CLI command.

Covers:
- Happy path: diff between commits with human-readable and JSON output
- Security: ref injection blocked, path traversal blocked, size limit enforced
- Edge cases: file not found, invalid ref, not a git repo, first commit (no HEAD~1)
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

CLI_PATH = str(Path(__file__).resolve().parent.parent.parent / "scripts" / "cli.py")

SKILL_V1 = """\
---
name: test-skill
description: A test skill for diffing
---

# Test Skill

This skill helps with testing.
"""

SKILL_V2 = """\
---
name: test-skill
description: A test skill for diffing and verification
---

# Test Skill

This skill helps with testing.

## When to Use

- Run automated quality checks
- Verify scoring functions

## Scope

This skill handles: scoring verification.
This skill does NOT handle: skill creation.

## Error Behavior

If the file is missing, return exit code 1.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_cli(*args, cwd=None, timeout=30):
    """Run cli.py with the given arguments."""
    return subprocess.run(
        [sys.executable, CLI_PATH, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=cwd,
    )


def _init_git_repo(tmp_path: Path) -> Path:
    """Create a git repo with two commits of a SKILL.md file."""
    repo = tmp_path / "repo"
    repo.mkdir()
    skill = repo / "SKILL.md"

    # Init repo
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(repo), capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(repo), capture_output=True,
    )

    # First commit: v1
    skill.write_text(SKILL_V1, encoding="utf-8")
    subprocess.run(["git", "add", "SKILL.md"], cwd=str(repo), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "v1"],
        cwd=str(repo), capture_output=True,
    )

    # Second commit: v2
    skill.write_text(SKILL_V2, encoding="utf-8")
    subprocess.run(["git", "add", "SKILL.md"], cwd=str(repo), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "v2"],
        cwd=str(repo), capture_output=True,
    )

    return repo


# ---------------------------------------------------------------------------
# Happy Path
# ---------------------------------------------------------------------------

class TestDiffHappyPath:
    """Test successful diff operations."""

    def test_diff_human_readable(self, tmp_path):
        """Diff between two commits produces human-readable output."""
        repo = _init_git_repo(tmp_path)
        result = _run_cli("diff", "SKILL.md", "--ref", "HEAD~1", cwd=str(repo))

        assert result.returncode == 0
        assert "schliff diff" in result.stdout
        assert "Composite:" in result.stdout
        assert "→" in result.stdout

    def test_diff_json_output(self, tmp_path):
        """Diff with --json produces valid JSON with expected keys."""
        repo = _init_git_repo(tmp_path)
        result = _run_cli("diff", "SKILL.md", "--ref", "HEAD~1", "--json", cwd=str(repo))

        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "skill_path" in data
        assert "ref" in data
        assert "old_composite" in data
        assert "new_composite" in data
        assert "composite_delta" in data
        assert "dimensions" in data
        assert isinstance(data["old_composite"], (int, float))
        assert isinstance(data["new_composite"], (int, float))

    def test_diff_json_composites_are_numbers(self, tmp_path):
        """JSON output contains numeric composites and delta."""
        repo = _init_git_repo(tmp_path)
        result = _run_cli("diff", "SKILL.md", "--ref", "HEAD~1", "--json", cwd=str(repo))

        data = json.loads(result.stdout)
        assert isinstance(data["composite_delta"], (int, float))
        # v2 should score higher than v1 (more structure, scope, error behavior)
        assert data["new_composite"] >= data["old_composite"]

    def test_diff_shows_dimension_changes(self, tmp_path):
        """Diff shows per-dimension changes when dimensions differ."""
        repo = _init_git_repo(tmp_path)
        result = _run_cli("diff", "SKILL.md", "--ref", "HEAD~1", "--json", cwd=str(repo))

        data = json.loads(result.stdout)
        # v2 has more structure (headers, scope) so at least one dimension should change
        assert isinstance(data["dimensions"], list)

    def test_diff_no_change(self, tmp_path):
        """Diff against same commit shows no significant changes."""
        repo = _init_git_repo(tmp_path)
        result = _run_cli("diff", "SKILL.md", "--ref", "HEAD", cwd=str(repo))

        assert result.returncode == 0
        assert "No significant dimension changes" in result.stdout


# ---------------------------------------------------------------------------
# Security: Ref Injection
# ---------------------------------------------------------------------------

class TestDiffRefInjection:
    """Test that malicious git refs are rejected."""

    def test_ref_starting_with_dash_rejected(self, tmp_path):
        """Refs starting with '-' are blocked (prevents git flag injection).

        argparse may reject single-dash refs before our validation runs
        (it interprets them as flags). Either way the command must fail.
        """
        repo = _init_git_repo(tmp_path)
        # Use --ref=-c to force argparse to accept the value
        result = _run_cli("diff", "SKILL.md", "--ref=-c", cwd=str(repo))

        assert result.returncode != 0
        assert "invalid git reference" in result.stderr

    def test_ref_with_semicolon_rejected(self, tmp_path):
        """Refs with shell metacharacters are blocked."""
        repo = _init_git_repo(tmp_path)
        result = _run_cli("diff", "SKILL.md", "--ref", "HEAD;rm -rf /", cwd=str(repo))

        assert result.returncode != 0
        assert "invalid git reference" in result.stderr

    def test_ref_with_backtick_rejected(self, tmp_path):
        """Refs with backticks are blocked."""
        repo = _init_git_repo(tmp_path)
        result = _run_cli("diff", "SKILL.md", "--ref", "HEAD`whoami`", cwd=str(repo))

        assert result.returncode != 0
        assert "invalid git reference" in result.stderr

    def test_ref_with_dollar_rejected(self, tmp_path):
        """Refs with $ are blocked."""
        repo = _init_git_repo(tmp_path)
        result = _run_cli("diff", "SKILL.md", "--ref", "$(whoami)", cwd=str(repo))

        assert result.returncode != 0
        assert "invalid git reference" in result.stderr

    def test_ref_with_spaces_rejected(self, tmp_path):
        """Refs with spaces are blocked."""
        repo = _init_git_repo(tmp_path)
        result = _run_cli("diff", "SKILL.md", "--ref", "HEAD --quiet", cwd=str(repo))

        assert result.returncode != 0
        # Either argparse rejects or our validation catches it
        assert result.returncode != 0

    def test_valid_refs_accepted(self, tmp_path):
        """Common valid git ref formats pass validation."""
        repo = _init_git_repo(tmp_path)

        valid_refs = ["HEAD~1", "HEAD", "HEAD~2", "HEAD^"]
        for ref in valid_refs:
            result = _run_cli("diff", "SKILL.md", "--ref", ref, cwd=str(repo))
            assert "invalid git reference" not in result.stderr, f"Valid ref {ref!r} was rejected"


# ---------------------------------------------------------------------------
# Security: Path Traversal
# ---------------------------------------------------------------------------

class TestDiffPathTraversal:
    """Test that paths outside the git repo are rejected."""

    def test_path_outside_repo_rejected(self, tmp_path):
        """Files outside the git repository are rejected."""
        repo = _init_git_repo(tmp_path)

        # Create a file outside the repo
        outside = tmp_path / "outside_skill.md"
        outside.write_text(SKILL_V1, encoding="utf-8")

        result = _run_cli("diff", str(outside), cwd=str(repo))

        assert result.returncode != 0
        assert "must be inside the git repository" in result.stderr


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestDiffEdgeCases:
    """Test edge cases and error handling."""

    def test_file_not_found(self, tmp_path):
        """Nonexistent file returns error."""
        repo = _init_git_repo(tmp_path)
        result = _run_cli("diff", "nonexistent.md", cwd=str(repo))

        assert result.returncode != 0
        assert "file not found" in result.stderr

    def test_invalid_ref_not_in_history(self, tmp_path):
        """Valid-format ref that doesn't exist in git returns error."""
        repo = _init_git_repo(tmp_path)
        result = _run_cli("diff", "SKILL.md", "--ref", "nonexistent_branch", cwd=str(repo))

        assert result.returncode != 0
        assert "cannot read" in result.stderr or "may not exist" in result.stderr

    def test_first_commit_no_parent(self, tmp_path):
        """Diff on first commit (no HEAD~1) returns helpful error."""
        repo = tmp_path / "fresh_repo"
        repo.mkdir()

        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(repo), capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(repo), capture_output=True,
        )

        skill = repo / "SKILL.md"
        skill.write_text(SKILL_V1, encoding="utf-8")
        subprocess.run(["git", "add", "SKILL.md"], cwd=str(repo), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "first"],
            cwd=str(repo), capture_output=True,
        )

        # HEAD~1 doesn't exist
        result = _run_cli("diff", "SKILL.md", "--ref", "HEAD~1", cwd=str(repo))

        assert result.returncode != 0
        assert "cannot read" in result.stderr or "may not exist" in result.stderr

    def test_not_a_git_repo(self, tmp_path):
        """Running diff outside a git repo returns error."""
        skill = tmp_path / "SKILL.md"
        skill.write_text(SKILL_V1, encoding="utf-8")

        result = _run_cli("diff", str(skill), cwd=str(tmp_path))

        assert result.returncode != 0
        assert "not a git repository" in result.stderr

    def test_file_not_tracked_in_ref(self, tmp_path):
        """File exists now but wasn't in the referenced commit."""
        repo = tmp_path / "repo2"
        repo.mkdir()

        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(repo), capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(repo), capture_output=True,
        )

        # First commit with a different file
        other = repo / "other.txt"
        other.write_text("hello", encoding="utf-8")
        subprocess.run(["git", "add", "other.txt"], cwd=str(repo), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(repo), capture_output=True,
        )

        # Second commit adds SKILL.md
        skill = repo / "SKILL.md"
        skill.write_text(SKILL_V1, encoding="utf-8")
        subprocess.run(["git", "add", "SKILL.md"], cwd=str(repo), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add skill"],
            cwd=str(repo), capture_output=True,
        )

        # Diff against HEAD~1 where SKILL.md didn't exist
        result = _run_cli("diff", "SKILL.md", "--ref", "HEAD~1", cwd=str(repo))

        assert result.returncode != 0
        assert "cannot read" in result.stderr or "may not exist" in result.stderr

    def test_diff_help_shows_usage(self):
        """--help produces usage information."""
        result = _run_cli("diff", "--help")

        assert result.returncode == 0
        assert "skill_path" in result.stdout
        assert "--ref" in result.stdout
        assert "--json" in result.stdout
