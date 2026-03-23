"""Score structural quality of a skill file.

Checks frontmatter, length, examples, headers, progressive disclosure,
imperative voice, referenced files, and dead content.
"""
from pathlib import Path

from shared import read_skill_safe, strip_frontmatter
from scoring.patterns import (
    _RE_FRONTMATTER_NAME, _RE_FRONTMATTER_DESC, _RE_REAL_EXAMPLES,
    _RE_CODE_BLOCKS, _RE_HEADERS, _RE_HEDGING, _RE_REFS, _RE_TODO,
    _RE_SECTION_HEADER,
)


def score_structure(skill_path: str) -> dict:
    """Score structural quality of a skill file.

    Uses inline Python analysis directly — no external bash dependency.
    """
    return _score_structure_inline(skill_path)


def _score_structure_inline(skill_path: str) -> dict:
    """Score structural quality of a SKILL.md file."""
    score = 0
    issues = []

    try:
        content = read_skill_safe(skill_path)
    except (FileNotFoundError, ValueError):
        return {"score": 0, "issues": ["file_not_found"], "details": {}}

    # Early return for empty or nearly empty skill bodies
    body = strip_frontmatter(content)
    if len(body.strip()) < 10:
        return {"score": 0, "issues": ["empty_skill_body"], "details": {}}

    lines = content.split("\n")

    # Frontmatter
    if lines and lines[0].strip() == "---":
        score += 10
        if _RE_FRONTMATTER_NAME.search(content):
            score += 10
        else:
            issues.append("missing_name")
        if _RE_FRONTMATTER_DESC.search(content):
            score += 10
        else:
            issues.append("missing_description")
    else:
        issues.append("no_frontmatter")

    # Length
    if len(lines) <= 500:
        score += 10
    elif len(lines) <= 700:
        score += 5
        issues.append("long_skill_md")

    # Examples — match the improved bash script logic
    real_examples = len(_RE_REAL_EXAMPLES.findall(content))
    code_block_pairs = len(_RE_CODE_BLOCKS.findall(content)) // 2
    if real_examples >= 2:
        score += 10
    elif real_examples >= 1 or (real_examples + code_block_pairs // 3) >= 2:
        score += 5
    else:
        issues.append("no_real_examples")

    # Headers — only count non-empty sections (anti-gaming)
    all_headers = list(_RE_HEADERS.finditer(content))
    header_count = 0
    content_lines = content.split("\n")
    for h_match in all_headers:
        h_line = content[:h_match.start()].count("\n")
        # Check next 5 lines for actual content (not blank or another header)
        has_content = False
        for j in range(h_line + 1, min(h_line + 6, len(content_lines))):
            stripped = content_lines[j].strip()
            if stripped and not stripped.startswith("#"):
                has_content = True
                break
        if has_content:
            header_count += 1
    if header_count >= 3:
        score += 10
    elif header_count >= 1:
        score += 5

    # Progressive disclosure
    skill_dir = Path(skill_path).parent
    if (skill_dir / "references").is_dir() or len(lines) <= 200:
        score += 15
    else:
        score += 5
        issues.append("no_progressive_disclosure")

    # Imperative voice
    hedge_count = len(_RE_HEDGING.findall(content))
    if hedge_count == 0:
        score += 5
    elif hedge_count <= 2:
        score += 3

    # Referenced files exist
    refs = set(_RE_REFS.findall(content))
    if not refs:
        # No references declared — neutral score (not rewarded, not penalized)
        score += 5
    else:
        missing = [r for r in refs if not (skill_dir / r).exists()]
        if not missing:
            # All declared references exist — reward completeness
            score += 10
        else:
            # Some references missing — partial credit
            score += 5
            issues.append(f"missing_refs: {missing}")

    # No dead content (TODO/FIXME/placeholder, empty sections)
    todo_count = len(_RE_TODO.findall(content))
    # Check for headers followed by only blank lines or next header
    empty_sections = 0
    for i, line in enumerate(lines):
        if _RE_SECTION_HEADER.match(line):
            # Look at next 5 non-empty lines
            next_content = 0
            for j in range(i + 1, min(i + 6, len(lines))):
                if lines[j].strip() and not lines[j].startswith("#"):
                    next_content += 1
            if next_content == 0:
                empty_sections += 1
    if todo_count == 0 and empty_sections == 0:
        score += 10
    elif todo_count == 0:
        score += 7
        issues.append(f"has_empty_sections:{empty_sections}")
    else:
        issues.append(f"has_todo_or_placeholder_text:{todo_count}")
        if empty_sections > 0:
            issues.append(f"has_empty_sections:{empty_sections}")

    return {"score": max(0, min(100, score)), "issues": issues, "details": {"line_count": len(lines)}}
