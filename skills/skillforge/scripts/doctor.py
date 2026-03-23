#!/usr/bin/env python3
"""SkillForge Doctor — Health Check for All Installed Skills

Scans all installed skills, scores each one, and produces a summary table
with actionable recommendations. Single command, zero arguments needed.

Usage:
    python3 doctor.py [--skill-dirs DIR...] [--json] [--verbose]

Output: Table of skills with structural scores, issues, and suggested actions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

import score_skill as scorer
import skill_mesh

from terminal_art import score_to_grade, grade_colored


def _default_skill_dirs() -> list[str]:
    """Return default skill scan directories."""
    return [
        str(Path.home() / ".claude" / "skills"),
        ".claude/skills",
    ]


def _score_single_skill(skill_path: str) -> dict:
    """Score a single skill and return summary."""
    skill_dir = Path(skill_path).parent

    # Load eval suite if available
    eval_suite = None
    eval_path = skill_dir / "eval-suite.json"
    if eval_path.exists():
        try:
            eval_suite = json.loads(eval_path.read_text(encoding="utf-8"))
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

    # Collect all issues
    all_issues = []
    for dim, data in scores.items():
        for issue in data.get("issues", []):
            all_issues.append(f"[{dim}] {issue}")

    # Determine recommended action
    score = composite["score"]
    has_eval = eval_suite is not None
    unmeasured = composite.get("unmeasured", [])

    if not has_eval:
        action = "Run /skillforge:init to generate eval suite"
    elif score < 50:
        action = "Run /skillforge:auto — significant room for improvement"
    elif score < 80:
        action = "Run /skillforge:auto — moderate improvements possible"
    elif score < 95:
        action = "Run /skillforge:analyze for targeted fixes"
    else:
        action = "Healthy — consider runtime eval for validation"

    return {
        "composite": score,
        "score_type": composite.get("score_type", "structural"),
        "grade": score_to_grade(score),
        "measured": composite["measured_dimensions"],
        "total_dims": composite["total_dimensions"],
        "has_eval_suite": has_eval,
        "issue_count": len(all_issues),
        "issues": all_issues,
        "action": action,
    }


def run_doctor(
    skill_dirs: list[str] | None = None,
    verbose: bool = False,
) -> dict:
    """Run doctor scan across all installed skills."""
    dirs = skill_dirs or _default_skill_dirs()

    # Discover all skills
    skills = skill_mesh.discover_skills(dirs)

    if not skills:
        return {
            "skills_found": 0,
            "results": [],
            "summary": "No skills found. Check skill directories.",
        }

    results = []
    healthy = 0
    needs_work = 0
    no_eval = 0

    for skill in skills:
        path = skill["path"]
        name = skill["name"]

        try:
            score_result = _score_single_skill(path)
        except Exception as e:
            results.append({
                "name": name,
                "path": path,
                "error": str(e),
            })
            continue

        result = {
            "name": name,
            "path": path,
            **score_result,
        }
        results.append(result)

        if not score_result["has_eval_suite"]:
            no_eval += 1
        elif score_result["composite"] >= 80:
            healthy += 1
        else:
            needs_work += 1

    # Sort by score ascending (worst first — they need attention)
    results.sort(key=lambda r: r.get("composite", 0))

    # Run mesh analysis for cross-skill issues
    mesh_result = skill_mesh.run_mesh_analysis(dirs, incremental=True)
    mesh_issues = mesh_result.get("issues", [])
    mesh_health = mesh_result.get("health", {}).get("score", 100)

    summary_parts = [f"{len(results)} skills scanned"]
    if healthy:
        summary_parts.append(f"{healthy} healthy")
    if needs_work:
        summary_parts.append(f"{needs_work} need work")
    if no_eval:
        summary_parts.append(f"{no_eval} missing eval suite")
    if mesh_issues:
        summary_parts.append(f"{len(mesh_issues)} mesh issues")

    return {
        "skills_found": len(results),
        "healthy": healthy,
        "needs_work": needs_work,
        "no_eval_suite": no_eval,
        "mesh_health": mesh_health,
        "mesh_issue_count": len(mesh_issues),
        "results": results,
        "summary": " | ".join(summary_parts),
    }


def format_doctor_report(report: dict) -> str:
    """Format doctor report as human-readable text."""
    lines = []
    lines.append("=" * 70)
    lines.append("  SkillForge Doctor — Skill Health Check")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"  {report['summary']}")
    lines.append("")

    results = report.get("results", [])
    if not results:
        lines.append("  No skills found in scanned directories.")
        lines.append("")
        lines.append("  Default scan dirs:")
        for d in _default_skill_dirs():
            lines.append(f"    - {d}")
        lines.append("")
        lines.append("=" * 70)
        return "\n".join(lines)

    # Table header
    lines.append(f"  {'Skill':<25s} {'Score':>6s} {'Grade':>6s} {'Dims':>6s} {'Issues':>7s}  Action")
    lines.append("  " + "-" * 68)

    for r in results:
        if "error" in r:
            lines.append(f"  {r['name']:<25s}  ERROR: {r['error'][:40]}")
            continue

        name = r["name"][:24]
        score = r["composite"]
        grade = grade_colored(r["grade"])
        dims = f"{r['measured']}/{r['total_dims']}"
        issues = r["issue_count"]
        action = r["action"][:35]

        lines.append(f"  {name:<25s} {score:>5.0f} {grade:>6s} {dims:>6s} {issues:>7d}  {action}")

    lines.append("")

    # Mesh health
    mesh_health = report.get("mesh_health", 100)
    mesh_issues = report.get("mesh_issue_count", 0)
    if mesh_issues > 0:
        lines.append(f"  Mesh Health: {mesh_health}/100 ({mesh_issues} cross-skill issues)")
        lines.append("  Run /skillforge:mesh for details.")
        lines.append("")

    # Top-level recommendations
    no_eval = report.get("no_eval_suite", 0)
    needs_work = report.get("needs_work", 0)

    if no_eval > 0 or needs_work > 0:
        lines.append("  Recommended next steps:")
        if no_eval > 0:
            lines.append(f"    1. Run /skillforge:init on {no_eval} skills missing eval suites")
        if needs_work > 0:
            lines.append(f"    {'2' if no_eval else '1'}. Run /skillforge:auto on {needs_work} low-scoring skills")
        lines.append("")

    lines.append("  NOTE: Scores are STRUCTURAL — they measure file organization,")
    lines.append("  not runtime effectiveness. Use --runtime for validated scoring.")
    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="SkillForge Doctor — Health Check for All Skills")
    parser.add_argument("--skill-dirs", nargs="+", default=None,
                        help="Directories to scan (default: ~/.claude/skills/, .claude/skills/)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show per-skill issues")
    args = parser.parse_args()

    report = run_doctor(skill_dirs=args.skill_dirs, verbose=args.verbose)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_doctor_report(report))


if __name__ == "__main__":
    main()
