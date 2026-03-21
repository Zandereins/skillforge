#!/usr/bin/env python3
"""SkillForge Achievements — Unlockable milestones that celebrate progress.

Checks improvement history and skill state against achievement conditions.
Achievements are persistent across sessions via ~/.skillforge/meta/achievements.json.

Usage:
    python3 achievements.py SKILL.md [--json] [--check-only]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

ACHIEVEMENTS_PATH = Path.home() / ".skillforge" / "meta" / "achievements.json"

# Achievement definitions: (id, name, emoji, description, check_fn)
# check_fn receives (state_entries, current_score, skill_name) -> bool

ACHIEVEMENT_DEFS: list[dict[str, Any]] = [
    {
        "id": "first_improvement",
        "name": "First Blood",
        "badge": "\u2694",
        "desc": "First successful improvement applied",
        "check": lambda s, c, n: sum(1 for e in s if e.get("status") == "keep" and e.get("delta", 0) > 0) >= 1,
    },
    {
        "id": "ten_improvements",
        "name": "Seasoned",
        "badge": "\u2b50",
        "desc": "10 improvements applied across all runs",
        "check": lambda s, c, n: sum(1 for e in s if e.get("status") == "keep" and e.get("delta", 0) > 0) >= 10,
    },
    {
        "id": "hit_80",
        "name": "B-Grade",
        "badge": "\u26a1",
        "desc": "Reached composite score 80+",
        "check": lambda s, c, n: c.get("composite", 0) >= 80,
    },
    {
        "id": "hit_90",
        "name": "A-Grade",
        "badge": "\U0001f3af",
        "desc": "Reached composite score 90+",
        "check": lambda s, c, n: c.get("composite", 0) >= 90,
    },
    {
        "id": "hit_95",
        "name": "Elite",
        "badge": "\U0001f48e",
        "desc": "Reached composite score 95+",
        "check": lambda s, c, n: c.get("composite", 0) >= 95,
    },
    {
        "id": "perfect_run",
        "name": "Flawless",
        "badge": "\U0001f525",
        "desc": "5+ iterations with zero regressions",
        "check": lambda s, c, n: _check_flawless(s),
    },
    {
        "id": "all_dims_green",
        "name": "All Green",
        "badge": "\U0001f7e2",
        "desc": "All measured dimensions >= 80",
        "check": lambda s, c, n: _check_all_green(c),
    },
    {
        "id": "big_jump",
        "name": "Quantum Leap",
        "badge": "\U0001f680",
        "desc": "Single improvement with delta >= 5.0",
        "check": lambda s, c, n: any(e.get("delta", 0) >= 5.0 for e in s if e.get("status") == "keep"),
    },
    {
        "id": "comeback",
        "name": "Comeback",
        "badge": "\U0001f4aa",
        "desc": "Improved after 3+ consecutive discards",
        "check": lambda s, c, n: _check_comeback(s),
    },
    {
        "id": "centurion",
        "name": "Centurion",
        "badge": "\U0001f3c6",
        "desc": "100+ total iterations across all runs",
        "check": lambda s, c, n: len([e for e in s if e.get("status") != "baseline"]) >= 100,
    },
]


def _check_flawless(state: list[dict]) -> bool:
    """Check for 5+ consecutive keeps without any discard."""
    streak = 0
    for e in state:
        if e.get("status") == "keep":
            streak += 1
            if streak >= 5:
                return True
        elif e.get("status") == "discard":
            streak = 0
    return False


def _check_all_green(score: dict) -> bool:
    """Check if all measured dimensions are >= 80."""
    dims = score.get("dimensions", {})
    measured = [v for v in dims.values() if isinstance(v, (int, float)) and v >= 0]
    return len(measured) >= 3 and all(v >= 80 for v in measured)


def _check_comeback(state: list[dict]) -> bool:
    """Check if a keep followed 3+ consecutive discards."""
    discards = 0
    for e in state:
        if e.get("status") == "discard":
            discards += 1
        elif e.get("status") == "keep" and discards >= 3:
            return True
        else:
            discards = 0
    return False


def _load_unlocked() -> dict[str, dict]:
    """Load previously unlocked achievements."""
    if not ACHIEVEMENTS_PATH.exists():
        return {}
    try:
        return json.loads(ACHIEVEMENTS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_unlocked(unlocked: dict[str, dict]) -> None:
    """Persist unlocked achievements."""
    ACHIEVEMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACHIEVEMENTS_PATH.write_text(json.dumps(unlocked, indent=2), encoding="utf-8")


def check_achievements(
    state_entries: list[dict],
    current_score: dict,
    skill_name: str,
    check_only: bool = False,
) -> dict[str, Any]:
    """Check all achievements and return status.

    Args:
        check_only: If True, don't persist newly unlocked achievements.

    Returns dict with 'newly_unlocked', 'all_unlocked', 'total'.
    """
    unlocked = _load_unlocked()
    newly = []

    for ach in ACHIEVEMENT_DEFS:
        aid = ach["id"]
        if aid in unlocked:
            continue
        try:
            if ach["check"](state_entries, current_score, skill_name):
                entry = {
                    "name": ach["name"],
                    "badge": ach["badge"],
                    "desc": ach["desc"],
                    "skill": skill_name,
                    "unlocked_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
                unlocked[aid] = entry
                newly.append(entry)
        except Exception:
            continue

    if newly and not check_only:
        _save_unlocked(unlocked)

    return {
        "newly_unlocked": newly,
        "all_unlocked": list(unlocked.values()),
        "total_available": len(ACHIEVEMENT_DEFS),
        "total_unlocked": len(unlocked),
    }


def format_achievements(result: dict[str, Any]) -> str:
    """Format achievements for terminal display."""
    lines = []
    newly = result.get("newly_unlocked", [])
    if newly:
        lines.append("")
        for ach in newly:
            lines.append(f"  {ach['badge']}  Achievement Unlocked: {ach['name']} — {ach['desc']}")
        lines.append("")

    total = result["total_unlocked"]
    avail = result["total_available"]
    bar_w = 10
    filled = min(bar_w, int(round(total / avail * bar_w))) if avail > 0 else 0
    bar = "\u2588" * filled + "\u2591" * (bar_w - filled)
    lines.append(f"  Achievements: {bar}  {total}/{avail}")

    all_unlocked = result.get("all_unlocked", [])
    if all_unlocked:
        badges = " ".join(a["badge"] for a in all_unlocked)
        lines.append(f"  {badges}")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="SkillForge Achievements")
    parser.add_argument("skill_path", help="Path to SKILL.md")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--check-only", action="store_true", help="Don't persist new unlocks")
    args = parser.parse_args()

    import importlib
    try:
        scorer = importlib.import_module("score-skill")
    except (ImportError, ModuleNotFoundError) as e:
        print(f"Error: cannot import score-skill module: {e}", file=sys.stderr)
        sys.exit(1)

    skill_path = str(Path(args.skill_path).resolve())
    skill_dir = Path(skill_path).parent

    # Load state
    state_path = skill_dir / ".skillforge" / "auto-improve-state.jsonl"
    state: list[dict] = []
    if state_path.exists():
        for line in state_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    state.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    # Current score
    eval_suite = None
    eval_path = skill_dir / "eval-suite.json"
    if eval_path.exists():
        try:
            eval_suite = json.loads(eval_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    scores = {
        "structure": scorer.score_structure(skill_path),
        "triggers": scorer.score_triggers(skill_path, eval_suite),
        "quality": scorer.score_quality(skill_path, eval_suite),
        "edges": scorer.score_edges(skill_path, eval_suite),
        "efficiency": scorer.score_efficiency(skill_path),
        "composability": scorer.score_composability(skill_path),
    }
    composite = scorer.compute_composite(scores)
    current_score = {
        "composite": composite["score"],
        "dimensions": {k: v["score"] for k, v in scores.items()},
    }

    # Extract skill name
    import re
    content = Path(skill_path).read_text(encoding="utf-8")
    name_match = re.search(r"^name:\s*(.+?)$", content, re.MULTILINE)
    skill_name = name_match.group(1).strip() if name_match else Path(skill_path).parent.name

    result = check_achievements(state, current_score, skill_name, check_only=args.check_only)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_achievements(result))


if __name__ == "__main__":
    main()
