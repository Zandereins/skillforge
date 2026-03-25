#!/usr/bin/env python3
"""Schliff CLI — The finishing cut for Claude Code skills.

Usage:
    schliff score <path>        Score a SKILL.md file
    schliff verify <path>       CI gate — exit 0 if pass, 1 if fail
    schliff doctor              Scan all installed skills
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


def cmd_score(args):
    """Run the structural scorer on a single SKILL.md file."""
    from pathlib import Path
    from scoring import (
        score_structure, score_triggers, score_efficiency,
        score_composability, score_quality, score_edges,
        score_runtime, score_clarity, compute_composite,
    )
    from shared import load_eval_suite, MAX_SKILL_SIZE

    if not Path(args.skill_path).exists():
        print(f"Error: file not found: {args.skill_path}", file=sys.stderr)
        sys.exit(1)

    eval_suite = None
    if args.eval_suite:
        eval_path = Path(args.eval_suite)
        if not eval_path.exists():
            print(f"Error: eval-suite not found: {args.eval_suite}", file=sys.stderr)
            sys.exit(1)
        if eval_path.stat().st_size > MAX_SKILL_SIZE:
            print(f"Error: eval-suite exceeds {MAX_SKILL_SIZE} byte size limit", file=sys.stderr)
            sys.exit(1)
        eval_suite = json.loads(eval_path.read_text(encoding="utf-8"))
    else:
        eval_suite = load_eval_suite(args.skill_path)

    scores = {
        "structure": score_structure(args.skill_path),
        "triggers": score_triggers(args.skill_path, eval_suite),
        "quality": score_quality(args.skill_path, eval_suite),
        "edges": score_edges(args.skill_path, eval_suite),
        "efficiency": score_efficiency(args.skill_path),
        "composability": score_composability(args.skill_path),
        "clarity": score_clarity(args.skill_path),
        "runtime": score_runtime(args.skill_path, eval_suite, enabled=False),
    }

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
            ver = "6.2.0"

        output = format_score_display(
            scores=scores,
            composite=composite,
            version=ver,
            contradictions=contradictions if contradictions else None,
            fix_count=fix_count,
        )
        print(output)


def cmd_verify(args):
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


def cmd_doctor(args):
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


def cmd_badge(args):
    """Generate a markdown badge for a skill's score."""
    from pathlib import Path
    from scoring import (
        score_structure, score_triggers, score_efficiency,
        score_composability, score_quality, score_edges,
        score_clarity, compute_composite,
    )
    from shared import load_eval_suite
    from terminal_art import score_to_grade

    if not Path(args.skill_path).exists():
        print(f"Error: file not found: {args.skill_path}", file=sys.stderr)
        sys.exit(1)

    eval_suite = load_eval_suite(args.skill_path)

    scores = {
        "structure": score_structure(args.skill_path),
        "triggers": score_triggers(args.skill_path, eval_suite),
        "quality": score_quality(args.skill_path, eval_suite),
        "edges": score_edges(args.skill_path, eval_suite),
        "efficiency": score_efficiency(args.skill_path),
        "composability": score_composability(args.skill_path),
        "clarity": score_clarity(args.skill_path),
    }

    composite = compute_composite(scores)
    score = composite["score"]
    grade = score_to_grade(score)

    # Color based on grade
    colors = {
        "S": "brightgreen", "A": "green", "B": "yellowgreen",
        "C": "yellow", "D": "orange", "E": "red", "F": "red",
    }
    color = colors.get(grade, "lightgrey")

    # URL-encode the label
    import urllib.parse
    label = urllib.parse.quote(f"{score:.0f}/100 [{grade}]", safe="")

    badge_md = f"[![Schliff: {score:.0f} [{grade}]](https://img.shields.io/badge/Schliff-{label}-{color})](https://github.com/Zandereins/schliff)"

    print(badge_md)


def cmd_demo(_args):
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


def cmd_version(_args):
    """Print version string."""
    try:
        from importlib.metadata import version
        print(f"schliff {version('schliff')}")
    except Exception:
        print("schliff 6.2.0")


def main():
    parser = argparse.ArgumentParser(
        prog="schliff",
        description="The finishing cut for Claude Code skills",
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

    # demo command
    subparsers.add_parser("demo", help="Score a built-in bad skill to see schliff in action")

    # version command
    subparsers.add_parser("version", help="Show version")

    args = parser.parse_args()

    commands = {
        "score": cmd_score,
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
