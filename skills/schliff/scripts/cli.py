#!/usr/bin/env python3
"""Schliff CLI — The finishing cut for Claude Code skills.

Usage:
    schliff score <path>        Score a SKILL.md file
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
    from shared import load_eval_suite

    if not Path(args.skill_path).exists():
        print(f"Error: file not found: {args.skill_path}", file=sys.stderr)
        sys.exit(1)

    eval_suite = None
    if args.eval_suite:
        eval_suite = json.loads(Path(args.eval_suite).read_text(encoding="utf-8"))
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
            "dimensions": {k: v["score"] for k, v in scores.items()},
            "warnings": composite["warnings"],
        }
        print(json.dumps(result, indent=2))
    else:
        score = composite["score"]
        grade = (
            "S" if score >= 95 else
            "A" if score >= 85 else
            "B" if score >= 75 else
            "C" if score >= 65 else
            "D" if score >= 50 else
            "F"
        )
        print(f"\nSchliff Score: {score}/100 [{grade}]")
        for dim, data in scores.items():
            s = data["score"]
            if s >= 0:
                indicator = "\u2713" if s >= 70 else "\u25b3" if s >= 50 else "\u2717"
                print(f"  {indicator} {dim:15s} {s:>5}")
        print()


def cmd_doctor(args):
    """Run doctor scan across all installed skills."""
    import doctor as doctor_mod

    report = doctor_mod.run_doctor(
        skill_dirs=getattr(args, "skill_dirs", None),
    )

    if getattr(args, "json", False):
        print(json.dumps(report, indent=2))
    else:
        formatted = doctor_mod.format_doctor_report(report)
        print(formatted)


def cmd_version(_args):
    """Print version string."""
    try:
        from importlib.metadata import version
        print(f"schliff {version('schliff')}")
    except Exception:
        print("schliff 6.0.0")


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

    # doctor command
    doctor_parser = subparsers.add_parser("doctor", help="Scan all installed skills")
    doctor_parser.add_argument("--json", action="store_true", help="JSON output")
    doctor_parser.add_argument("--skill-dirs", nargs="+", default=None,
                               help="Directories to scan")

    # version command
    subparsers.add_parser("version", help="Show version")

    args = parser.parse_args()

    commands = {
        "score": cmd_score,
        "doctor": cmd_doctor,
        "version": cmd_version,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
