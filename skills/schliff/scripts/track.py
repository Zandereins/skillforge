#!/usr/bin/env python3
"""Schliff Track — Score history tracking and regression detection.

Records skill scores over time, detects regressions, and renders
sparkline visualizations of score trends.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Maximum history file size (10 MB) to prevent unbounded growth
_MAX_HISTORY_SIZE = 10_000_000

# Sparkline block characters (8 levels, low to high)
_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def get_history_path(skill_path: str) -> Path:
    """Resolve the history file path via git root, falling back to skill dir."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            root = result.stdout.strip()
            return Path(root) / ".schliff" / "history.json"
    except (subprocess.SubprocessError, OSError):
        pass
    return Path(skill_path).resolve().parent / ".schliff" / "history.json"


def get_current_commit() -> str:
    """Return the short SHA of HEAD, or 'no-git' outside a repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        pass
    return "no-git"


def record_score(
    skill_path: str,
    composite: float,
    grade: str,
    dimensions: dict,
) -> dict:
    """Append a score entry to history.

    If the last entry has the same commit and skill path, it is replaced
    (prevents duplicates from repeated runs on the same commit).
    Non-finite composites are clamped to 0.0; non-numeric dimensions
    default to 0.  Writes atomically via temp file + rename.
    """
    # Normalize path for consistent deduplication (relative vs absolute)
    skill_path = str(Path(skill_path).resolve())
    hist_path = get_history_path(skill_path)
    commit = get_current_commit()

    hist_path.parent.mkdir(parents=True, exist_ok=True)

    entries: List[dict] = []
    if hist_path.exists():
        try:
            raw = hist_path.read_text(encoding="utf-8")
            if len(raw) > _MAX_HISTORY_SIZE:
                print(
                    f"Warning: history file exceeds {_MAX_HISTORY_SIZE} bytes, "
                    "truncating to last 100 entries",
                    file=sys.stderr,
                )
                # Try to salvage recent entries from oversized file
                try:
                    all_entries = json.loads(raw)
                    if isinstance(all_entries, list):
                        entries = all_entries[-100:]
                    # else: entries stays []
                except (json.JSONDecodeError, MemoryError):
                    entries = []
            else:
                entries = json.loads(raw)
                if not isinstance(entries, list):
                    entries = []
        except (json.JSONDecodeError, OSError):
            entries = []

    # Guard against NaN/Inf which produce invalid JSON
    if not math.isfinite(composite):
        composite = 0.0

    # Safe int conversion for dimensions — skip non-numeric values
    safe_dims: Dict[str, int] = {}
    for k, v in dimensions.items():
        try:
            safe_dims[k] = int(v)
        except (ValueError, TypeError):
            safe_dims[k] = 0

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "commit": commit,
        "skill": skill_path,
        "composite": round(composite, 1),
        "grade": grade,
        "dimensions": safe_dims,
    }

    # Deduplicate: replace last entry if same commit and skill
    if entries and entries[-1].get("commit") == commit and entries[-1].get("skill") == skill_path:
        entries[-1] = entry
    else:
        entries.append(entry)

    # Atomic write: temp file + rename to prevent corruption on crash
    data = json.dumps(entries, indent=2) + "\n"
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(hist_path.parent), suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(hist_path))
        except OSError:
            # Clean up orphaned temp file before fallback
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            hist_path.write_text(data, encoding="utf-8")
    except OSError:
        # mkstemp itself failed — direct write
        hist_path.write_text(data, encoding="utf-8")

    return entry


def load_history(skill_path: Optional[str] = None) -> List[dict]:
    """Load score history, optionally filtered to a single skill.

    When *skill_path* is ``None``, the history file is located via the
    git repository root.  This requires the current working directory
    to be inside a git repository; otherwise an empty list is returned.
    """
    hist_path: Optional[Path] = None

    if skill_path:
        hist_path = get_history_path(skill_path)
    else:
        # Try git root without a skill path
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                hist_path = Path(result.stdout.strip()) / ".schliff" / "history.json"
        except (subprocess.SubprocessError, OSError):
            pass

    if hist_path is None or not hist_path.exists():
        return []

    try:
        raw = hist_path.read_text(encoding="utf-8")
        if len(raw) > _MAX_HISTORY_SIZE:
            print(
                f"Warning: history file exceeds {_MAX_HISTORY_SIZE} bytes, "
                "loading last 100 entries only",
                file=sys.stderr,
            )
            entries = json.loads(raw)
            if isinstance(entries, list):
                entries = entries[-100:]
            else:
                return []
        else:
            entries = json.loads(raw)
            if not isinstance(entries, list):
                return []
    except (json.JSONDecodeError, OSError):
        return []

    if skill_path:
        # Normalize for consistent matching (record_score stores resolved paths)
        normalized = str(Path(skill_path).resolve())
        entries = [e for e in entries if e.get("skill") == normalized]

    return entries


def render_sparkline(history: list[dict], width: int = 20) -> str:
    """Render a sparkline string from composite scores."""
    if not history or width <= 0:
        return ""

    scores = [e.get("composite", 0.0) for e in history]

    # Sample evenly if more entries than width
    if len(scores) > width:
        step = len(scores) / width
        scores = [scores[int(i * step)] for i in range(width)]

    chars = []
    for s in scores:
        clamped = max(0.0, min(100.0, s))
        idx = int(clamped / 100.0 * (len(_SPARK_CHARS) - 1))
        chars.append(_SPARK_CHARS[idx])

    return "".join(chars)


def check_regression(
    history: list[dict],
    threshold: float = 5.0,
) -> tuple[bool, float]:
    """Detect score regression between the last two entries."""
    if len(history) < 2:
        return False, 0.0

    current = history[-1].get("composite", 0.0)
    previous = history[-2].get("composite", 0.0)
    delta = current - previous

    if delta < -threshold:
        return True, delta
    return False, delta


def format_track_report(
    skill_path: str,
    history: Optional[List[dict]] = None,
) -> str:
    """Render a plain-text score history report."""
    if history is None:
        history = load_history(skill_path)

    name = Path(skill_path).stem

    lines: list[str] = []
    lines.append(f"═══ Schliff Track: {name} ═══")
    lines.append("")

    if not history:
        lines.append("No history recorded yet.")
        return "\n".join(lines)

    spark = render_sparkline(history)
    lines.append(f"Sparkline: {spark}")
    lines.append("")

    latest = history[-1]
    composites = [(e.get("composite", 0.0), e) for e in history]
    peak_score, peak_entry = max(composites, key=lambda x: x[0])
    low_score, low_entry = min(composites, key=lambda x: x[0])

    lines.append(f"Latest:  {latest['composite']:.1f} [{latest.get('grade', '?')}]  ({latest.get('commit', '?')})")
    lines.append(f"Peak:    {peak_score:.1f} [{peak_entry.get('grade', '?')}]  ({peak_entry.get('commit', '?')})")
    lines.append(f"Lowest:  {low_score:.1f} [{low_entry.get('grade', '?')}]  ({low_entry.get('commit', '?')})")
    lines.append(f"Entries: {len(history)}")
    lines.append("")

    regressed, delta = check_regression(history)
    if len(history) < 2:
        lines.append("Trend: — (single entry)")
    elif delta > 0.05:
        lines.append(f"Trend: ↑ improving ({delta:+.1f} from previous)")
    elif delta < -0.05:
        label = "REGRESSION" if regressed else "declining"
        lines.append(f"Trend: ↓ {label} ({delta:+.1f} from previous)")
    else:
        lines.append(f"Trend: → stable ({delta:+.1f} from previous)")

    return "\n".join(lines)
