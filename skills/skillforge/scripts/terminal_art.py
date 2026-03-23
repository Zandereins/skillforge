#!/usr/bin/env python3
"""SkillForge — Shared Terminal Art Library

Centralized render functions for grades, heatmaps, banners, and score cards.
Imported by dashboard.py, generate-report.py, auto-improve.py, init-skill.py,
and achievements.py.

Pattern: ANSI only when is_color_tty(), NO_COLOR respected, returns str.
"""
from __future__ import annotations

import os
import sys


# ---------------------------------------------------------------------------
# Color detection
# ---------------------------------------------------------------------------

def is_color_tty() -> bool:
    """Check if stdout supports ANSI colors."""
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty() and not os.environ.get("NO_COLOR")


# ---------------------------------------------------------------------------
# Grade system
# ---------------------------------------------------------------------------

_GRADE_THRESHOLDS = [
    (95, "S"), (85, "A"), (75, "B"), (65, "C"), (50, "D"), (35, "E"),
]

_GRADE_COLORS = {
    "S": "\x1b[35m",  # magenta
    "A": "\x1b[32m",  # green
    "B": "\x1b[32m",  # green
    "C": "\x1b[33m",  # yellow
    "D": "\x1b[31m",  # red
    "E": "\x1b[31m",  # red
    "F": "\x1b[31m",  # red
}

RESET = "\x1b[0m"


def score_to_grade(score: float) -> str:
    """Map composite score to letter grade: S(>=95) A(>=85) B(>=75) C(>=65) D(>=50) E(>=35) F(<35)."""
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


def grade_colored(grade: str) -> str:
    """Return grade string with ANSI color if TTY supports it."""
    if not is_color_tty():
        return f"[{grade}]"
    color = _GRADE_COLORS.get(grade, "")
    return f"{color}[{grade}]{RESET}"


# ---------------------------------------------------------------------------
# Progress bars and gauges
# ---------------------------------------------------------------------------

def colored_bar(score: float, bar_w: int = 10) -> str:
    """Render a gauge bar, optionally colored by score threshold."""
    filled = min(bar_w, int(round(score / 100 * bar_w)))
    bar = "\u2588" * filled + "\u2591" * (bar_w - filled)
    if not is_color_tty():
        return bar
    if score >= 80:
        return f"\x1b[32m{bar}{RESET}"  # green
    elif score >= 60:
        return f"\x1b[33m{bar}{RESET}"  # yellow
    else:
        return f"\x1b[31m{bar}{RESET}"  # red


def progress_bar(score: float, width: int = 20) -> str:
    """Return an ASCII progress bar like: ████████████░░░░░░░░."""
    filled = min(width, int(round(score / 100 * width)))
    empty = width - filled
    return "\u2588" * filled + "\u2591" * empty


def sparkline(values: list[float]) -> str:
    """Render a sparkline from a list of values using Unicode block characters."""
    if not values:
        return ""
    blocks = " \u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
    lo, hi = min(values), max(values)
    spread = hi - lo if hi > lo else 1
    return "".join(blocks[min(8, int((v - lo) / spread * 8))] for v in values)


# ---------------------------------------------------------------------------
# ASCII Heatmap
# ---------------------------------------------------------------------------

_HEAT_CHARS = " \u2591\u2592\u2593\u2588"  # ' ░▒▓█'


def render_heatmap(dims: list[str], iterations: list[dict], width: int = 30) -> str:
    """Render a Dimension x Iteration grid with ░▒▓█ characters.

    Args:
        dims: List of dimension names.
        iterations: List of dicts, each with a 'dimensions' dict mapping dim->score.
        width: Max label width for alignment.

    Returns:
        Multi-line string of the heatmap.
    """
    if not dims or not iterations:
        return ""

    # Compute max label width
    label_w = min(width, max(len(d) for d in dims) + 1)

    lines = []

    # Header row
    header_label = " " * label_w
    iter_nums = "  ".join(f"{i + 1}" for i in range(len(iterations)))
    lines.append(f"{header_label} Iter {iter_nums}")

    for dim in dims:
        # Truncate or pad label
        label = dim[:label_w - 1] + ":" if len(dim) >= label_w else dim + ":"
        label = label.ljust(label_w)

        cells = []
        for it in iterations:
            dim_scores = it.get("dimensions", {})
            score = dim_scores.get(dim, -1)
            if isinstance(score, (int, float)) and score >= 0:
                # Map 0-100 to heat char index 0-4
                idx = min(4, int(score / 25))
                char = _HEAT_CHARS[idx]
            else:
                char = " "
            cells.append(char)

        line = label + "  ".join(cells)
        lines.append(line)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Box Banner
# ---------------------------------------------------------------------------

def render_banner(title: str, subtitle: str = "") -> str:
    """Render a Unicode Box-Drawing banner.

    ╭─ SkillForge ──────────────╮
    │  title                    │
    │  subtitle                 │
    ╰───────────────────────────╯
    """
    content_lines = [title]
    if subtitle:
        content_lines.append(subtitle)

    max_len = max(len(line) for line in content_lines)
    box_w = max(max_len + 4, 30)

    lines = []
    top = f"\u256d\u2500 SkillForge " + "\u2500" * (box_w - 14) + "\u256e"
    lines.append(top)
    for cl in content_lines:
        lines.append(f"\u2502  {cl:<{box_w - 4}}  \u2502")
    lines.append(f"\u2570" + "\u2500" * (box_w - 2) + "\u256f")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Before/After comparison
# ---------------------------------------------------------------------------

def render_before_after(before: float, after: float, label: str = "Score") -> str:
    """Side-by-side bars: Before ████░░ 42 → After ████████ 87 (+45)."""
    bar_w = 10
    bar_before = progress_bar(before, bar_w)
    bar_after = progress_bar(after, bar_w)
    delta = after - before
    delta_str = f"({delta:+.1f})"
    return f"{label}: {bar_before} {before:.0f} \u2192 {bar_after} {after:.0f} {delta_str}"


# ---------------------------------------------------------------------------
# Score Card
# ---------------------------------------------------------------------------

def render_score_card(score: float, grade: str, dims: dict) -> str:
    """Compact card: Grade + Score + Dimension-Bars.

    Returns a multi-line string.
    """
    lines = []
    grade_str = grade_colored(grade)
    lines.append(f"  Score: {score:.1f}/100  {grade_str}")
    lines.append("")

    for dim, s in dims.items():
        if isinstance(s, (int, float)) and s >= 0:
            bar = colored_bar(s)
            lines.append(f"    {dim:15s} {bar}  {s:.0f}/100")
        else:
            lines.append(f"    {dim:15s} {'n/a':>15s}")

    return "\n".join(lines)
