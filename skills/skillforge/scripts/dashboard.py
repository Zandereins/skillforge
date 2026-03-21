#!/usr/bin/env python3
"""SkillForge Skill Health Dashboard — Unified Status View

Combines score, gradients, mesh issues, strategy history, and untriaged
failures into one report for a given skill.

Usage:
    python3 dashboard.py SKILL.md [--json] [--skill-dirs DIR...]

Output: Single-page health overview with actionable next steps.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


def _is_color_tty() -> bool:
    """Check if stdout supports ANSI colors."""
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _colored_bar(score: int, bar_w: int = 10) -> str:
    """Render a gauge bar, optionally colored by score threshold."""
    filled = min(bar_w, int(round(score / 100 * bar_w)))
    bar = "\u2588" * filled + "\u2591" * (bar_w - filled)
    if not _is_color_tty():
        return bar
    if score >= 80:
        return f"\x1b[32m{bar}\x1b[0m"  # green
    elif score >= 60:
        return f"\x1b[33m{bar}\x1b[0m"  # yellow
    else:
        return f"\x1b[31m{bar}\x1b[0m"  # red

# Import terminal_art for grade system
try:
    from terminal_art import score_to_grade, grade_colored
except ImportError:
    def score_to_grade(s: float) -> str:
        for t, g in [(95,"S"),(85,"A"),(75,"B"),(65,"C"),(50,"D")]:
            if s >= t: return g
        return "F"
    def grade_colored(g: str) -> str:
        return f"[{g}]"

# Import sibling modules via importlib (hyphenated names)
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

import importlib

def _try_import(module_name: str):
    """Import a hyphenated sibling module; return None on failure."""
    try:
        return importlib.import_module(module_name)
    except (ImportError, ModuleNotFoundError, SyntaxError) as e:
        print(f"Warning: module '{module_name}' unavailable — dashboard will show N/A for that section ({e})", file=sys.stderr)
        return None

scorer = _try_import("score-skill")
gradient_engine = _try_import("text-gradient")
mesh_analyzer = _try_import("skill-mesh")
meta_reporter = _try_import("meta-report")
achievements_mod = _try_import("achievements")


def _load_jsonl_safe(path: Path, max_size: int = 10_000_000) -> list[dict]:
    """Load JSONL with size guard."""
    if not path.exists():
        return []
    if path.stat().st_size > max_size:
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def generate_dashboard(
    skill_path: str,
    skill_dirs: list[str] | None = None,
    include_clarity: bool = True,
) -> dict:
    """Generate unified health dashboard for a skill."""
    skill_p = Path(skill_path)
    skill_dir = skill_p.parent
    skill_name = "unknown"

    # Extract skill name
    if scorer is not None:
        try:
            content = scorer._read_skill_safe(skill_path)
            name_match = re.search(r"^name:\s*(.+?)$", content, re.MULTILINE)
            if name_match:
                skill_name = name_match.group(1).strip()
        except (FileNotFoundError, ValueError):
            pass

    # 1. Score (all dimensions)
    eval_suite = None
    auto_eval = skill_dir / "eval-suite.json"
    if auto_eval.exists():
        try:
            eval_suite = json.loads(auto_eval.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: failed to parse eval-suite.json: {e}", file=sys.stderr)

    _na = {"score": -1, "issues": [], "details": {}}
    if scorer is not None:
        scores = {
            "structure": scorer.score_structure(skill_path),
            "triggers": scorer.score_triggers(skill_path, eval_suite),
            "quality": scorer.score_quality(skill_path, eval_suite),
            "edges": scorer.score_edges(skill_path, eval_suite),
            "efficiency": scorer.score_efficiency(skill_path),
            "composability": scorer.score_composability(skill_path),
        }
        if include_clarity:
            scores["clarity"] = scorer.score_clarity(skill_path)
        composite = scorer.compute_composite(scores)
    else:
        scores = {
            "structure": _na, "triggers": _na, "quality": _na,
            "edges": _na, "efficiency": _na, "composability": _na,
        }
        if include_clarity:
            scores["clarity"] = _na
        composite = {"score": -1, "measured_dimensions": 0, "total_dimensions": len(scores), "weight_coverage": 0.0}

    # 2. Top gradients
    if gradient_engine is not None:
        gradients = gradient_engine.compute_gradients(
            skill_path, eval_suite=eval_suite,
            include_clarity=include_clarity, top_n=5,
        )
    else:
        gradients = []

    # 3. Mesh issues (filtered to this skill)
    if mesh_analyzer is not None:
        mesh_result = mesh_analyzer.run_mesh_analysis(
            skill_dirs=skill_dirs or [],
            severity_filter=None,
            incremental=True,
        )
    else:
        mesh_result = {"issues": []}
    mesh_issues = [
        i for i in mesh_result.get("issues", [])
        if skill_name in (i.get("skill_a", ""), i.get("skill_b", ""), i.get("skill", ""))
    ]

    # 4. Untriaged failures
    failures_path = skill_dir / ".skillforge" / "failures.jsonl"
    failures = _load_jsonl_safe(failures_path, max_size=1_000_000)
    untriaged = [f for f in failures if not f.get("injected")]

    # 5. Strategy history from meta
    meta_dir = Path.home() / ".skillforge" / "meta"
    strategy_entries = _load_jsonl_safe(meta_dir / "strategy-log.jsonl")
    skill_strategies = [e for e in strategy_entries if e.get("skill") == skill_name]

    # Compute strategy stats
    strategy_stats = {}
    for entry in skill_strategies:
        st = entry.get("strategy_type", "unknown")
        if st not in strategy_stats:
            strategy_stats[st] = {"total": 0, "kept": 0, "deltas": []}
        strategy_stats[st]["total"] += 1
        if entry.get("status") == "keep":
            strategy_stats[st]["kept"] += 1
            strategy_stats[st]["deltas"].append(entry.get("delta", 0))

    for st, data in strategy_stats.items():
        data["keep_rate"] = round(data["kept"] / data["total"], 2) if data["total"] > 0 else 0
        data["avg_delta"] = round(sum(data["deltas"]) / len(data["deltas"]), 2) if data["deltas"] else 0
        del data["deltas"]

    result = {
        "skill_name": skill_name,
        "skill_path": skill_path,
        "composite_score": composite["score"],
        "dimensions": {k: v["score"] for k, v in scores.items()},
        "top_gradients": [
            {"dimension": g["dimension"], "issue": g["issue"],
             "instruction": g["instruction"], "delta": g["delta"],
             "priority": g["priority"]}
            for g in gradients
        ],
        "mesh_issues": mesh_issues,
        "untriaged_failures": len(untriaged),
        "failure_clusters": _cluster_failures(untriaged),
        "strategy_history": strategy_stats,
        "confidence": {
            "measured": composite["measured_dimensions"],
            "total": composite["total_dimensions"],
            "weight_coverage": composite["weight_coverage"],
        },
    }

    # 6. Achievements
    if achievements_mod is not None:
        state_path = skill_dir / ".skillforge" / "auto-improve-state.jsonl"
        state_entries = _load_jsonl_safe(state_path)
        current_score = {
            "composite": composite["score"],
            "dimensions": {k: v["score"] for k, v in scores.items()},
        }
        ach_result = achievements_mod.check_achievements(state_entries, current_score, skill_name)
        result["achievements"] = ach_result
    else:
        result["achievements"] = None

    return result


def _cluster_failures(failures: list[dict]) -> dict:
    """Cluster failures by type."""
    clusters: dict[str, int] = {}
    for f in failures:
        key = f.get("failure_type", "unknown")
        clusters[key] = clusters.get(key, 0) + 1
    return clusters


def format_dashboard(dashboard: dict) -> str:
    """Format dashboard as human-readable text."""
    lines = []
    lines.append("=" * 70)
    lines.append(f"  SkillForge Health Dashboard: {dashboard['skill_name']}")
    lines.append("=" * 70)
    lines.append("")

    # Score with gauge + grade
    score = dashboard["composite_score"]
    bar = _colored_bar(score, bar_w=20)
    grade = score_to_grade(score)
    grade_str = grade_colored(grade)
    lines.append(f"  Composite: {bar}  {score}/100  {grade_str}")

    conf = dashboard["confidence"]
    if conf["measured"] < conf["total"]:
        lines.append(f"    [{conf['measured']}/{conf['total']} dimensions, {conf['weight_coverage']:.0%} coverage]")
    lines.append("")

    # Dimensions (with colored gauge bars)
    lines.append("  Dimensions:")
    for dim, s in dashboard["dimensions"].items():
        if s >= 0:
            bar = _colored_bar(s)
            lines.append(f"    {dim:15s} {bar}  {s}/100")
        else:
            lines.append(f"    {dim:15s} {'n/a':>15s}")
    lines.append("")

    # Top gradients
    gradients = dashboard.get("top_gradients", [])
    if gradients:
        lines.append(f"  Top {len(gradients)} Improvements:")
        lines.append("  " + "-" * 60)
        for i, g in enumerate(gradients, 1):
            lines.append(f"    #{i} [{g['dimension']}] {g['issue']}")
            lines.append(f"       {g['instruction'][:80]}")
            lines.append(f"       delta: +{g['delta']:.1f}  |  priority: {g['priority']}")
        lines.append("")

    # Mesh issues
    mesh = dashboard.get("mesh_issues", [])
    if mesh:
        lines.append(f"  Mesh Issues ({len(mesh)}):")
        for issue in mesh[:5]:
            sev = issue.get("severity", "info").upper()
            itype = issue.get("type", "unknown")
            if itype == "trigger_overlap":
                lines.append(f"    [{sev}] Overlap with {issue.get('skill_b', '?')} ({issue.get('similarity', 0):.0%})")
            elif itype == "broken_handoff":
                lines.append(f"    [{sev}] Broken ref: '{issue.get('referenced', '?')}'")
            elif itype == "scope_collision":
                lines.append(f"    [{sev}] Scope collision with {issue.get('skill_b', '?')}")
        lines.append("")

    # Failures
    untriaged = dashboard.get("untriaged_failures", 0)
    if untriaged > 0:
        lines.append(f"  Untriaged Failures: {untriaged}")
        clusters = dashboard.get("failure_clusters", {})
        for ftype, count in sorted(clusters.items(), key=lambda x: -x[1]):
            lines.append(f"    - {ftype}: {count}")
        lines.append("  Run /skillforge:triage to investigate.")
        lines.append("")

    # Strategy history
    strategies = dashboard.get("strategy_history", {})
    if strategies:
        lines.append("  Strategy History:")
        for st, data in sorted(strategies.items(), key=lambda x: -x[1].get("keep_rate", 0)):
            lines.append(
                f"    {st:25s} keep={data['keep_rate']:.0%} "
                f"avg_delta={data['avg_delta']:+.1f} "
                f"({data['kept']}/{data['total']})"
            )
        lines.append("")

    # Achievements
    ach = dashboard.get("achievements")
    if ach and achievements_mod is not None:
        lines.append(achievements_mod.format_achievements(ach))
        lines.append("")

    lines.append("=" * 70)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="SkillForge Skill Health Dashboard")
    parser.add_argument("skill_path", help="Path to SKILL.md")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--skill-dirs", nargs="+", default=[],
                        help="Directories to scan for mesh analysis")
    parser.add_argument("--no-clarity", action="store_true",
                        help="Exclude clarity dimension")
    args = parser.parse_args()

    dashboard = generate_dashboard(
        args.skill_path,
        skill_dirs=args.skill_dirs,
        include_clarity=not args.no_clarity,
    )

    if args.json:
        print(json.dumps(dashboard, indent=2))
    else:
        print(format_dashboard(dashboard))


if __name__ == "__main__":
    main()
