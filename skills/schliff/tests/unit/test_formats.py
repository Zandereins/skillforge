"""Tests for scoring/formats.py — format detection and content normalization."""
from __future__ import annotations

from scoring.formats import detect_format, normalize_content


# --- P0: detect_format ---

def test_detect_skill_md():
    assert detect_format("SKILL.md") == "skill.md"


def test_detect_claude_md():
    assert detect_format("CLAUDE.md") == "claude.md"


def test_detect_cursorrules():
    assert detect_format(".cursorrules") == "cursorrules"


def test_detect_agents_md():
    assert detect_format("AGENTS.md") == "agents.md"


def test_detect_unknown():
    assert detect_format("README.md") == "unknown"


# --- P0: normalize_content passthrough ---

def test_normalize_passthrough():
    content = "---\nname: My Skill\ndescription: Does things\n---\n\n# My Skill\n\nBody text."
    result = normalize_content(content, "skill.md")
    assert result == content


# --- normalize_content: non-skill.md formats get synthetic frontmatter ---

def test_normalize_wraps_plain_content():
    content = "# My Tool\n\nThis tool does something useful."
    result = normalize_content(content, "claude.md")
    assert result.startswith("---\n")
    assert "name:" in result
    assert "description:" in result
    assert content in result


def test_normalize_passthrough_if_already_has_frontmatter():
    content = "---\nname: Existing\ndescription: Already wrapped\n---\n\nBody."
    result = normalize_content(content, "cursorrules")
    assert result == content


def test_normalize_no_heading_uses_first_line():
    content = "This is the first significant line.\n\nMore content follows."
    result = normalize_content(content, "agents.md")
    assert result.startswith("---\n")
    assert "name:" in result
    assert content in result
