"""Schliff — Format Detection and Content Normalization

Detect the format of a project instruction file and normalize non-SKILL.md
content to SKILL.md shape so the existing scoring engine can process it
without any scorer changes.
"""
from __future__ import annotations

import re
from pathlib import Path

# Supported format identifiers
FORMAT_SKILL_MD = "skill.md"
FORMAT_CLAUDE_MD = "claude.md"
FORMAT_CURSORRULES = "cursorrules"
FORMAT_AGENTS_MD = "agents.md"
FORMAT_UNKNOWN = "unknown"

_BASENAME_MAP: dict[str, str] = {
    "skill.md": FORMAT_SKILL_MD,
    "claude.md": FORMAT_CLAUDE_MD,
    ".cursorrules": FORMAT_CURSORRULES,
    "agents.md": FORMAT_AGENTS_MD,
}

_RE_H1 = re.compile(r"^#\s+(.+)", re.MULTILINE)


def detect_format(filename: str) -> str:
    """Return the format identifier for a project instruction file.

    Matches by basename (case-insensitive). Returns one of:
    "skill.md", "claude.md", "cursorrules", "agents.md", "unknown".
    """
    basename = Path(filename).name.lower()
    return _BASENAME_MAP.get(basename, FORMAT_UNKNOWN)


def normalize_content(content: str, fmt: str) -> str:
    """Normalize non-SKILL.md content to SKILL.md shape.

    If the content already has YAML frontmatter (starts with "---") or
    fmt is "skill.md", return content unchanged. Otherwise wrap the content
    in synthetic YAML frontmatter so the scoring engine can process it.
    """
    if fmt == FORMAT_SKILL_MD or content.startswith("---"):
        return content

    name = _extract_name(content)
    desc = _extract_description(content, name)

    header = f"---\nname: {name}\ndescription: {desc}\n---\n\n"
    return header + content


def _extract_name(content: str) -> str:
    """Extract a name from the first H1 heading or first significant line."""
    match = _RE_H1.search(content)
    if match:
        return match.group(1).strip()

    for line in content.splitlines():
        stripped = line.strip()
        if stripped:
            # Truncate long lines to keep frontmatter readable
            return stripped[:80]

    return "Untitled"


def _extract_description(content: str, name: str) -> str:
    """Extract a description from the first paragraph after any heading."""
    lines = content.splitlines()
    past_heading = False
    paragraph: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            past_heading = True
            continue
        if past_heading or not _RE_H1.search(content):
            if stripped:
                paragraph.append(stripped)
            elif paragraph:
                break  # end of first paragraph

    desc = " ".join(paragraph).strip()
    if not desc:
        desc = name
    # Truncate to keep frontmatter compact
    return desc[:200]
