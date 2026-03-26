#!/usr/bin/env python3
"""Schliff CLI — The finishing cut for Claude Code skills.

Usage:
    schliff score <path>        Score a SKILL.md file
    schliff diff <path>         Explain score changes between git commits
    schliff verify <path>       CI gate — exit 0 if pass, 1 if fail
    schliff doctor              Scan all installed skills
    schliff badge <path>        Generate markdown badge
    schliff demo                Score a built-in bad skill
    schliff version             Show version
"""
import sys
import os
import json
import argparse

# Ensure scripts dir is on sys.path so existing modules (scoring, shared, etc.)
# can be imported without restructuring the project.
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


def _load_eval_suite_from_args(args: argparse.Namespace) -> "dict | None":
    """Load eval suite from --eval-suite flag or auto-discover from skill dir."""
    from pathlib import Path
    from shared import load_eval_suite, MAX_SKILL_SIZE

    if getattr(args, "eval_suite", None):
        eval_path = Path(args.eval_suite)
        if not eval_path.exists():
            print(f"Error: eval-suite not found: {args.eval_suite}", file=sys.stderr)
            sys.exit(1)
        if eval_path.stat().st_size > MAX_SKILL_SIZE:
            print(f"Error: eval-suite exceeds {MAX_SKILL_SIZE} byte size limit", file=sys.stderr)
            sys.exit(1)
        return json.loads(eval_path.read_text(encoding="utf-8"))
    return load_eval_suite(args.skill_path)


def cmd_score(args: argparse.Namespace) -> None:
    """Run the structural scorer on a single SKILL.md file."""
    from pathlib import Path
    from scoring import compute_composite
    from shared import build_scores

    if not Path(args.skill_path).exists():
        print(f"Error: file not found: {args.skill_path}", file=sys.stderr)
        sys.exit(1)

    eval_suite = _load_eval_suite_from_args(args)
    scores = build_scores(args.skill_path, eval_suite, include_runtime=True)

    composite = compute_composite(scores)

    if getattr(args, "json", False):
        result = {
            "skill_path": args.skill_path,
            "composite_score": composite["score"],
            "dimensions": {k: round(v["score"], 1) if isinstance(v["score"], float) else v["score"] for k, v in scores.items()},
            "warnings": composite["warnings"],
        }
        print(json.dumps(result, indent=2))
    else:
        from terminal_art import format_score_display
        import text_gradient

        # Extract contradictions from clarity details
        clarity_data = scores.get("clarity", {})
        contradictions = clarity_data.get("details", {}).get("contradictions", [])

        # Count available deterministic fixes
        try:
            gradients = text_gradient.compute_gradients(
                args.skill_path, eval_suite, include_clarity=True,
            )
            fix_count = len(gradients)
        except Exception:
            fix_count = 0

        # Get version
        try:
            from importlib.metadata import version
            ver = version("schliff")
        except Exception:
            ver = "6.3.0"

        output = format_score_display(
            scores=scores,
            composite=composite,
            version=ver,
            contradictions=contradictions if contradictions else None,
            fix_count=fix_count,
        )
        print(output)


def cmd_verify(args: argparse.Namespace) -> None:
    """CI gate — score a skill and exit with appropriate code."""
    from pathlib import Path
    from shared import load_eval_suite, MAX_SKILL_SIZE
    import verify as verify_mod

    if not Path(args.skill_path).exists():
        print(f"Error: file not found: {args.skill_path}", file=sys.stderr)
        sys.exit(2)

    eval_suite = None
    if args.eval_suite:
        eval_path = Path(args.eval_suite)
        if not eval_path.exists():
            print(f"Error: eval-suite not found: {args.eval_suite}", file=sys.stderr)
            sys.exit(2)
        if eval_path.stat().st_size > MAX_SKILL_SIZE:
            print(f"Error: eval-suite exceeds {MAX_SKILL_SIZE} byte size limit", file=sys.stderr)
            sys.exit(2)
        eval_suite = json.loads(eval_path.read_text(encoding="utf-8"))
    else:
        eval_suite = load_eval_suite(args.skill_path)

    try:
        verdict = verify_mod.run_verify(
            skill_path=args.skill_path,
            min_score=args.min_score,
            check_regression=args.regression,
            history_path=args.history,
            eval_suite=eval_suite,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

    if getattr(args, "json", False):
        print(json.dumps(verdict, indent=2))
    else:
        print(verify_mod.format_verdict(verdict))

    sys.exit(verdict["exit_code"])


def cmd_doctor(args: argparse.Namespace) -> None:
    """Run doctor scan across all installed skills."""
    import doctor as doctor_mod

    verbose = getattr(args, "verbose", False)
    report = doctor_mod.run_doctor(
        skill_dirs=getattr(args, "skill_dirs", None),
        verbose=verbose,
    )

    if getattr(args, "json", False):
        print(json.dumps(report, indent=2))
    else:
        formatted = doctor_mod.format_doctor_report(report, verbose=verbose)
        print(formatted)


def cmd_badge(args: argparse.Namespace) -> None:
    """Generate a markdown badge for a skill's score."""
    import urllib.parse
    from pathlib import Path
    from scoring import compute_composite
    from shared import build_scores
    from terminal_art import score_to_grade

    if not Path(args.skill_path).exists():
        print(f"Error: file not found: {args.skill_path}", file=sys.stderr)
        sys.exit(1)

    eval_suite = _load_eval_suite_from_args(args)
    scores = build_scores(args.skill_path, eval_suite)

    composite = compute_composite(scores)
    score = composite["score"]
    grade = score_to_grade(score)

    colors = {
        "S": "brightgreen", "A": "green", "B": "yellowgreen",
        "C": "yellow", "D": "orange", "E": "red", "F": "red",
    }
    color = colors.get(grade, "lightgrey")

    label = urllib.parse.quote(f"{score:.0f}/100 [{grade}]", safe="")
    badge_md = f"[![Schliff: {score:.0f} [{grade}]](https://img.shields.io/badge/Schliff-{label}-{color})](https://github.com/Zandereins/schliff)"

    print(badge_md)


def cmd_demo(_args: argparse.Namespace) -> None:
    """Score a built-in demo skill to showcase schliff's output."""
    import tempfile
    from pathlib import Path

    demo_content = '''---
name: deploy-helper
description: Helps with deployment stuff
---

# Deploy Helper

This skill probably helps with deployment. You might want to use it when deploying things.

## What It Does

- Setting up deployment configurations
- Running deploy commands
- Checking if deployment worked

## How To Use

1. Tell Claude you want to deploy something
2. It will try to help you
3. Check if it worked
'''

    with tempfile.TemporaryDirectory() as tmpdir:
        skill_path = str(Path(tmpdir) / "SKILL.md")
        Path(skill_path).write_text(demo_content, encoding="utf-8")

        # Reuse cmd_score logic
        import argparse as _ap
        fake_args = _ap.Namespace(skill_path=skill_path, json=False, eval_suite=None)
        cmd_score(fake_args)

    print("\n  This is a deliberately bad skill. Try schliff on your own skills!")
    print("  Usage: schliff score path/to/SKILL.md\n")


def cmd_diff(args: argparse.Namespace) -> None:
    """Explain score changes between git commits."""
    import re
    import subprocess
    import tempfile
    from pathlib import Path
    from scoring import compute_composite
    from scoring.diff import score_diff, explain_score_change
    from shared import build_scores, MAX_SKILL_SIZE

    skill_path = args.skill_path
    if not Path(skill_path).exists():
        print(f"Error: file not found: {skill_path}", file=sys.stderr)
        sys.exit(1)

    ref = args.ref

    # Validate ref to prevent git flag injection
    if ref.startswith("-") or not re.match(r'^[a-zA-Z0-9_.~^@/\-]+$', ref):
        print(f"Error: invalid git reference: {ref}", file=sys.stderr)
        sys.exit(1)

    # Score current version
    eval_suite = _load_eval_suite_from_args(args)
    new_scores = build_scores(skill_path, eval_suite)
    new_composite = compute_composite(new_scores)

    # Reconstruct old version via git show
    try:
        # Get the path relative to git root
        git_root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if git_root.returncode != 0:
            print("Error: not a git repository", file=sys.stderr)
            sys.exit(1)

        abs_skill = str(Path(skill_path).resolve())
        root = git_root.stdout.strip()

        # Ensure skill path is inside the git repository
        if not abs_skill.startswith(root + os.sep):
            print("Error: skill path must be inside the git repository", file=sys.stderr)
            sys.exit(1)

        rel_path = os.path.relpath(abs_skill, root)

        old_content = subprocess.run(
            ["git", "show", f"{ref}:{rel_path}"],
            capture_output=True, text=True, timeout=10,
        )
        if old_content.returncode != 0:
            print(f"Error: cannot read {rel_path} at ref '{ref}' — file may not exist in that commit", file=sys.stderr)
            sys.exit(1)

        # Guard against oversized content from git history
        if len(old_content.stdout) > MAX_SKILL_SIZE:
            print(f"Error: file at ref '{ref}' exceeds {MAX_SKILL_SIZE} byte size limit", file=sys.stderr)
            sys.exit(1)
    except FileNotFoundError:
        print("Error: git not available", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("Error: git command timed out", file=sys.stderr)
        sys.exit(1)

    # Score old version in a temp file
    with tempfile.TemporaryDirectory() as tmpdir:
        old_path = str(Path(tmpdir) / "SKILL.md")
        Path(old_path).write_text(old_content.stdout, encoding="utf-8")
        old_scores = build_scores(old_path, eval_suite)
        old_composite = compute_composite(old_scores)

    # Diff analysis (signal/noise classification) — use resolved path
    diff_analysis = score_diff(abs_skill, ref)

    # Build per-dimension deltas
    old_flat = {k: v["score"] for k, v in old_scores.items() if isinstance(v, dict)}
    new_flat = {k: v["score"] for k, v in new_scores.items() if isinstance(v, dict)}
    explanations = explain_score_change(old_flat, new_flat, diff_analysis)

    if getattr(args, "json", False):
        result = {
            "skill_path": skill_path,
            "ref": ref,
            "old_composite": old_composite["score"],
            "new_composite": new_composite["score"],
            "composite_delta": round(new_composite["score"] - old_composite["score"], 1),
            "dimensions": explanations,
        }
        if diff_analysis.get("available"):
            result["diff_summary"] = diff_analysis["net_change"]
        print(json.dumps(result, indent=2))
    else:
        from terminal_art import score_to_grade

        old_score = old_composite["score"]
        new_score = new_composite["score"]
        delta = new_score - old_score

        old_grade = score_to_grade(old_score)
        new_grade = score_to_grade(new_score)

        print(f"\n  schliff diff  {ref} → current\n")
        print(f"  Composite: {old_score:.1f} [{old_grade}] → {new_score:.1f} [{new_grade}]  ({delta:+.1f})\n")

        if explanations:
            for exp in explanations:
                arrow = "+" if exp["delta"] > 0 else ""
                print(f"  {exp['dimension']:16s}  {exp['old']:6.1f} → {exp['new']:6.1f}  ({arrow}{exp['delta']:.1f})")
            print()
        else:
            print("  No significant dimension changes.\n")

        if diff_analysis.get("available"):
            net = diff_analysis["net_change"]
            print(f"  Diff: {net['signal']:+d} signal, {net['noise']:+d} noise, {net['lines']:+d} lines total\n")


def cmd_version(_args: argparse.Namespace) -> None:
    """Print version string."""
    try:
        from importlib.metadata import version
        print(f"schliff {version('schliff')}")
    except Exception:
        print("schliff 6.3.0")


def main():
    parser = argparse.ArgumentParser(
        prog="schliff",
        description="The finishing cut for Claude Code skills",
        epilog="Quick start:\n"
               "  schliff demo              See it in action instantly\n"
               "  schliff score SKILL.md    Score a skill\n"
               "  schliff doctor            Scan all installed skills",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # score command
    score_parser = subparsers.add_parser("score", help="Score a SKILL.md file")
    score_parser.add_argument("skill_path", help="Path to SKILL.md")
    score_parser.add_argument("--json", action="store_true", help="JSON output")
    score_parser.add_argument("--eval-suite", help="Path to eval-suite.json")

    # verify command
    verify_parser = subparsers.add_parser("verify", help="CI gate — exit 0/1 based on score")
    verify_parser.add_argument("skill_path", help="Path to SKILL.md")
    verify_parser.add_argument("--min-score", type=float, default=75.0,
                               help="Minimum passing score (default: 75)")
    verify_parser.add_argument("--regression", action="store_true",
                               help="Fail if score dropped vs previous run")
    verify_parser.add_argument("--history", default=".schliff/history.jsonl",
                               help="Path to history file (default: .schliff/history.jsonl)")
    verify_parser.add_argument("--eval-suite", help="Path to eval-suite.json")
    verify_parser.add_argument("--json", action="store_true", help="JSON output")

    # doctor command
    doctor_parser = subparsers.add_parser("doctor", help="Scan all installed skills")
    doctor_parser.add_argument("--json", action="store_true", help="JSON output")
    doctor_parser.add_argument("--skill-dirs", nargs="+", default=None,
                               help="Directories to scan")
    doctor_parser.add_argument("--verbose", "-v", action="store_true",
                               help="Show per-skill issues")

    # badge command
    badge_parser = subparsers.add_parser("badge", help="Generate markdown badge for a skill")
    badge_parser.add_argument("skill_path", help="Path to SKILL.md")
    badge_parser.add_argument("--eval-suite", help="Path to eval-suite.json")

    # diff command
    diff_parser = subparsers.add_parser("diff", help="Explain score changes between git commits")
    diff_parser.add_argument("skill_path", help="Path to SKILL.md")
    diff_parser.add_argument("--ref", default="HEAD~1",
                              help="Git ref to compare against (default: HEAD~1)")
    diff_parser.add_argument("--json", action="store_true", help="JSON output")
    diff_parser.add_argument("--eval-suite", help="Path to eval-suite.json")

    # demo command
    subparsers.add_parser("demo", help="Score a built-in bad skill to see schliff in action")

    # version command
    subparsers.add_parser("version", help="Show version")

    args = parser.parse_args()

    commands = {
        "score": cmd_score,
        "diff": cmd_diff,
        "verify": cmd_verify,
        "doctor": cmd_doctor,
        "badge": cmd_badge,
        "demo": cmd_demo,
        "version": cmd_version,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
