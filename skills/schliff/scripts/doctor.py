#!/usr/bin/env python3
"""Schliff Doctor — Health Check for All Installed Skills

Scans all installed skills, scores each one, and produces a summary table
with actionable recommendations. Single command, zero arguments needed.

Usage:
    python3 doctor.py [--skill-dirs DIR...] [--repo DIR] [--json] [--verbose]

Output: Table of skills with structural scores, issues, and suggested actions.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import score_skill as scorer
import skill_mesh

from scoring.formats import detect_format
from shared import estimate_token_cost
from terminal_art import score_to_grade, grade_colored

# Directories to skip during instruction file discovery
_EXCLUDED_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__"}

# Filenames to match (lowercase) for instruction file discovery
_INSTRUCTION_FILENAMES = {"claude.md", ".cursorrules", "agents.md"}


def discover_instruction_files(root_dir: str) -> list[dict]:
    """Discover all project instruction files in a directory tree.

    Finds: CLAUDE.md, .cursorrules, AGENTS.md (any case).
    Excludes: .git/, node_modules/, venv/, __pycache__/, .venv/

    Uses detect_format() from scoring.formats to classify each file.

    Returns list of dicts:
    [{"path": "/abs/path/to/CLAUDE.md", "format": "claude.md", "name": "CLAUDE.md"}, ...]
    """
    results: list[dict] = []
    for dirpath, dirs, files in os.walk(root_dir):
        # Skip excluded directories in-place
        dirs[:] = [d for d in dirs if d not in _EXCLUDED_DIRS]
        for fname in files:
            if fname.lower() in _INSTRUCTION_FILENAMES:
                full_path = os.path.join(dirpath, fname)
                abs_path = os.path.abspath(full_path)
                fmt = detect_format(fname)
                results.append({
                    "path": abs_path,
                    "format": fmt,
                    "name": fname,
                })
    results.sort(key=lambda r: r["path"])
    return results


def _default_skill_dirs() -> list[str]:
    """Return default skill scan directories."""
    return [
        str(Path.home() / ".claude" / "skills"),
        ".claude/skills",
    ]


def _score_single_skill(skill_path: str) -> dict:
    """Score a single skill and return summary."""
    from shared import load_eval_suite, build_scores

    eval_suite = load_eval_suite(skill_path)
    scores = build_scores(skill_path, eval_suite)

    composite = scorer.compute_composite(scores)

    # Collect all issues
    all_issues = []
    for dim, data in scores.items():
        for issue in data.get("issues", []):
            all_issues.append(f"[{dim}] {issue}")

    # Check for skill-specific recommendations
    recommendations = []
    structure_issues = scores.get("structure", {}).get("issues", [])
    line_count = scores.get("structure", {}).get("details", {}).get("line_count", 0)
    if "no_progressive_disclosure" in structure_issues and line_count > 300:
        recommendations.append(
            f"Consider extracting into references/ — {line_count} lines without progressive disclosure"
        )

    # Determine recommended action
    score = composite["score"]
    has_eval = eval_suite is not None
    unmeasured = composite.get("unmeasured", [])

    if not has_eval:
        action = f"/schliff:init {skill_path}"
    elif score < 50:
        action = f"/schliff:auto {skill_path}"
    elif score < 80:
        action = f"/schliff:auto {skill_path}"
    elif score < 95:
        action = f"/schliff:analyze {skill_path}"
    else:
        action = "Healthy"

    tokens = estimate_token_cost(skill_path)

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
        "tokens": tokens,
        "recommendations": recommendations,
    }


def run_doctor(
    skill_dirs: list[str] | None = None,
    verbose: bool = False,
    repo_root: str | None = None,
) -> dict:
    """Run doctor scan across all installed skills."""
    dirs = skill_dirs or _default_skill_dirs()

    # Discover all skills
    skills = skill_mesh.discover_skills(dirs)

    if not skills:
        # Discover instruction files even when no skills found
        scan_root = repo_root or "."
        instruction_files = discover_instruction_files(scan_root)
        return {
            "skills_found": 0,
            "healthy": 0,
            "needs_work": 0,
            "no_eval_suite": 0,
            "total_tokens": 0,
            "mesh_health": 100,
            "mesh_issue_count": 0,
            "results": [],
            "instruction_files": instruction_files,
            "drift_findings": [],
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

    # Compute total token cost across all skills
    total_tokens = sum(r.get("tokens", 0) for r in results if "error" not in r)

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

    # Discover project instruction files
    scan_root = repo_root or "."
    instruction_files = discover_instruction_files(scan_root)

    # Drift analysis on discovered instruction files
    drift_findings: list[dict] = []
    if instruction_files and repo_root:
        try:
            import drift as drift_mod
            for ifile in instruction_files:
                try:
                    content = Path(ifile["path"]).read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                refs = drift_mod.extract_references(content)
                if refs:
                    findings = drift_mod.validate_references(refs, repo_root)
                    missing = [f for f in findings if f["status"] == "missing"]
                    if missing:
                        drift_findings.extend(
                            {**f, "source_file": ifile["name"]} for f in missing
                        )
        except ImportError:
            pass  # drift module not available — skip

    if drift_findings:
        summary_parts.append(f"{len(drift_findings)} stale references")

    return {
        "skills_found": len(results),
        "healthy": healthy,
        "needs_work": needs_work,
        "no_eval_suite": no_eval,
        "total_tokens": total_tokens,
        "mesh_health": mesh_health,
        "mesh_issue_count": len(mesh_issues),
        "results": results,
        "instruction_files": instruction_files,
        "drift_findings": drift_findings,
        "scan_root": scan_root,
        "summary": " | ".join(summary_parts),
    }


def format_doctor_report(report: dict, verbose: bool = False) -> str:
    """Format doctor report as human-readable text."""
    lines = []
    lines.append("=" * 70)
    lines.append("  Schliff Doctor — Skill Health Check")
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

    # Total token cost
    total_tokens = report.get("total_tokens", 0)
    if total_tokens > 0:
        lines.append(f"  Total context cost: ~{total_tokens:,} tokens")
        lines.append("")

    # Table header
    lines.append(f"  {'Skill':<25s} {'Score':>6s} {'Grade':>6s} {'Dims':>6s} {'Tokens':>7s} {'Issues':>7s}  Action")
    lines.append("  " + "-" * 76)

    for r in results:
        if "error" in r:
            lines.append(f"  {r['name']:<25s}  ERROR: {r['error'][:40]}")
            continue

        name = r["name"][:24]
        score = r["composite"]
        grade = grade_colored(r["grade"])
        dims = f"{r['measured']}/{r['total_dims']}"
        tokens = r.get("tokens", 0)
        issues = r["issue_count"]
        action = r["action"][:35]

        lines.append(f"  {name:<25s} {score:>5.0f} {grade:>6s} {dims:>6s} {tokens:>7d} {issues:>7d}  {action}")

        if verbose and r.get("issues"):
            for issue in r["issues"][:5]:  # Cap at 5 to avoid flooding
                lines.append(f"    {'':25s}  └─ {issue}")

    lines.append("")

    # Project instruction files
    instruction_files = report.get("instruction_files", [])
    lines.append("  Project Instruction Files")
    lines.append("  " + "-" * 25)
    if instruction_files:
        for f in instruction_files:
            rel_path = os.path.relpath(f["path"], start=report.get("scan_root", "."))
            lines.append(f"  {f['name']:<20s} {f['format']:<14s} ./{rel_path}")
    else:
        lines.append("  No project instruction files found.")
    lines.append("")

    # Drift findings
    drift_findings = report.get("drift_findings", [])
    if drift_findings:
        lines.append(f"  Stale References ({len(drift_findings)} found)")
        lines.append("  " + "-" * 25)
        for df in drift_findings[:10]:  # Cap at 10 to avoid flooding
            lines.append(f"    {df.get('source_file', '?')}: `{df['ref']}` (line {df['line']})")
        if len(drift_findings) > 10:
            lines.append(f"    ... and {len(drift_findings) - 10} more")
        lines.append("")

    # Mesh health
    mesh_health = report.get("mesh_health", 100)
    mesh_issues = report.get("mesh_issue_count", 0)
    if mesh_issues > 0:
        lines.append(f"  Mesh Health: {mesh_health}/100 ({mesh_issues} cross-skill issues)")
        lines.append("  Run /schliff:mesh for details.")
        lines.append("")

    # Top-level recommendations
    no_eval = report.get("no_eval_suite", 0)
    needs_work = report.get("needs_work", 0)

    if no_eval > 0 or needs_work > 0:
        lines.append("  Recommended next steps:")
        if no_eval > 0:
            lines.append(f"    1. Run /schliff:init on {no_eval} skills missing eval suites")
        if needs_work > 0:
            lines.append(f"    {'2' if no_eval else '1'}. Run /schliff:auto on {needs_work} low-scoring skills")
        lines.append("")

    # Skill-specific recommendations
    skills_with_recs = [r for r in results if r.get("recommendations")]
    if skills_with_recs:
        lines.append("  Skill-specific recommendations:")
        for r in skills_with_recs:
            for rec in r["recommendations"]:
                lines.append(f"    - {r['name']}: {rec}")
        lines.append("")

    lines.append("  NOTE: Scores are STRUCTURAL — they measure file organization,")
    lines.append("  not runtime effectiveness. Runtime scoring requires an eval suite.")
    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Schliff Doctor — Health Check for All Skills")
    parser.add_argument("--skill-dirs", nargs="+", default=None,
                        help="Directories to scan (default: ~/.claude/skills/, .claude/skills/)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show per-skill issues")
    parser.add_argument("--repo", default=None,
                        help="Repository root for instruction file discovery")
    args = parser.parse_args()

    report = run_doctor(skill_dirs=args.skill_dirs, verbose=args.verbose,
                        repo_root=args.repo)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_doctor_report(report, verbose=args.verbose))


if __name__ == "__main__":
    main()
