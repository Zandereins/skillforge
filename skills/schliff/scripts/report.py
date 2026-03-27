#!/usr/bin/env python3
"""Schliff Report — Generate Markdown Score Reports with Optional Gist Upload."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from typing import Any


# ---------------------------------------------------------------------------
# ASCII bar helper
# ---------------------------------------------------------------------------

_BAR_WIDTH = 10
_BAR_CHAR = "\u2588"  # full block


def _ascii_bar(score: float) -> str:
    """Return a fixed-width ASCII bar proportional to score/100.

    Args:
        score: A value between 0 and 100.

    Returns:
        A string of ``_BAR_WIDTH`` characters using full-block and space.
    """
    clamped = max(0.0, min(100.0, float(score)))
    filled = round(clamped / 100 * _BAR_WIDTH)
    return _BAR_CHAR * filled + " " * (_BAR_WIDTH - filled)


# ---------------------------------------------------------------------------
# Badge helper
# ---------------------------------------------------------------------------

_GRADE_COLORS = {
    "S": "brightgreen",
    "A": "green",
    "B": "yellowgreen",
    "C": "yellow",
    "D": "orange",
    "E": "red",
    "F": "red",
}


def _badge_markdown(score: float, grade: str) -> str:
    """Build a shields.io badge markdown string."""
    badge_score = f"{score:.1f}"
    color = _GRADE_COLORS.get(grade, "lightgrey")
    return (
        f"[![Schliff: {score:.1f} [{grade}]]"
        f"(https://img.shields.io/badge/Schliff-{badge_score}%2F100_%5B{grade}%5D-{color})]"
        f"(https://github.com/Zandereins/schliff)"
    )


# ---------------------------------------------------------------------------
# Collect top issues across dimensions
# ---------------------------------------------------------------------------

def _collect_top_issues(scores: dict[str, Any], limit: int = 3) -> list[str]:
    """Extract up to *limit* issues from the scores dict.

    Each dimension value is expected to have an ``issues`` list.
    Issues are collected in dimension-iteration order and capped.

    Args:
        scores: Mapping of dimension name to ``{"score": float, "issues": [...]}``.
        limit: Maximum number of issues to return.

    Returns:
        A list of issue strings, at most *limit* long.
    """
    issues: list[str] = []
    for dim_data in scores.values():
        if not isinstance(dim_data, dict):
            continue
        for issue in dim_data.get("issues", []):
            if isinstance(issue, str) and issue.strip():
                issues.append(issue.strip())
                if len(issues) >= limit:
                    return issues
    return issues


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report_markdown(
    scores: dict[str, Any],
    skill_path: str,
    composite: dict[str, Any],
    grade: str,
) -> str:
    """Generate a Markdown score report.

    Args:
        scores: Dimension scores — keys are dimension names, values are dicts
            with ``"score"`` (float) and ``"issues"`` (list[str]).
        skill_path: Filesystem path to the scored skill file.
        composite: Dict with at least ``"score"`` (float) and optional
            ``"warnings"`` (list[str]).
        grade: Letter grade (e.g. ``"A"``, ``"B"``).

    Returns:
        A complete Markdown string ready for display or upload.
    """
    composite_score: float = composite.get("score", 0.0)
    warnings: list[str] = composite.get("warnings", [])

    lines: list[str] = []

    # Header
    lines.append("## Schliff Score Report")
    lines.append("")
    lines.append(f"**Skill:** `{skill_path}`  ")
    lines.append(f"**Composite Score:** {composite_score:.1f}/100 [{grade}]")
    lines.append("")

    # Warnings
    if warnings:
        for w in warnings:
            lines.append(f"> {w}")
        lines.append("")

    # Dimension table
    lines.append("| Dimension | Score | Bar |")
    lines.append("|-----------|------:|-----|")
    for dim_name, dim_data in scores.items():
        if not isinstance(dim_data, dict):
            continue
        dim_score = dim_data.get("score", 0.0)
        bar = _ascii_bar(dim_score)
        lines.append(f"| {dim_name.capitalize()} | {dim_score:.1f} | `{bar}` |")
    lines.append("")

    # Recommendations (top 3 issues)
    top_issues = _collect_top_issues(scores, limit=3)
    lines.append("### Recommendations")
    lines.append("")
    if top_issues:
        for i, issue in enumerate(top_issues, 1):
            lines.append(f"{i}. {issue}")
    else:
        lines.append("No issues found.")
    lines.append("")

    # Badge
    badge = _badge_markdown(composite_score, grade)
    lines.append("---")
    lines.append("")
    lines.append("**Badge:**")
    lines.append("")
    lines.append("```markdown")
    lines.append(badge)
    lines.append("```")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Gist upload
# ---------------------------------------------------------------------------

def upload_gist(
    markdown: str,
    token: str | None = None,
    filename: str = "schliff-report.md",
) -> str | None:
    """Upload a Markdown report as a secret GitHub Gist.

    Args:
        markdown: The report content to upload.
        token: GitHub personal access token.  Falls back to the
            ``GITHUB_TOKEN`` environment variable when *None*.
        filename: Name of the file inside the gist.

    Returns:
        The gist HTML URL on success, or *None* when no token is
        available or the request fails.
    """
    resolved_token = token or os.environ.get("GITHUB_TOKEN")
    if not resolved_token:
        print("No GITHUB_TOKEN — printing report to stdout", file=sys.stderr)
        return None

    payload = json.dumps({
        "description": "Schliff Score Report",
        "public": False,
        "files": {filename: {"content": markdown}},
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.github.com/gists",
        data=payload,
        headers={
            "Authorization": f"token {resolved_token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("html_url")
    except urllib.error.HTTPError as exc:
        print(f"Gist upload failed: HTTP {exc.code} — {exc.reason}", file=sys.stderr)
        return None
    except (urllib.error.URLError, OSError) as exc:
        print(f"Gist upload failed: {exc}", file=sys.stderr)
        return None
