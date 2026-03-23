#!/usr/bin/env python3
"""SkillForge — Skill Structural Scorer

Computes a composite structural score across 6 dimensions.
Used during the autonomous improvement loop to decide keep/discard.

IMPORTANT: This is a STRUCTURAL score — it measures file organization,
keyword coverage, and eval suite completeness. It does NOT measure whether
the skill actually works correctly at runtime. For runtime validation,
use the --runtime flag or run runtime-evaluator.py separately.

Usage:
    python score-skill.py /path/to/SKILL.md [--eval-suite eval.json] [--json]

Outputs composite score and per-dimension breakdown.
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure scripts directory is on path for shared module imports
sys.path.insert(0, str(Path(__file__).parent))
from shared import read_skill_safe, extract_description, VALID_DIMENSIONS, invalidate_cache as _shared_invalidate_cache
from scoring import (
    score_structure, score_triggers, score_efficiency,
    score_composability, score_coherence, score_quality,
    score_edges, score_runtime, score_clarity,
    score_diff, explain_score_change, compute_composite,
)


def invalidate_cache(skill_path: str) -> None:
    """Invalidate the file cache for a given skill path.

    Public API — delegates to shared.invalidate_cache (single cache).
    """
    _shared_invalidate_cache(skill_path)


def main():
    parser = argparse.ArgumentParser(description="SkillForge Structural Scorer")
    parser.add_argument("skill_path", help="Path to SKILL.md")
    parser.add_argument("--eval-suite", help="Path to eval suite JSON", default=None)
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--diff", action="store_true", help="Include diff analysis")
    parser.add_argument("--diff-ref", default="HEAD~1", help="Git ref to diff against (default: HEAD~1)")
    parser.add_argument("--clarity", action="store_true", help="Include clarity dimension (zero weight by default)")
    parser.add_argument("--runtime", action="store_true",
                        help="Enable runtime scoring dimension (invokes claude CLI)")
    parser.add_argument("--weights", default=None,
                        help="Custom dimension weights as key=value pairs, e.g. "
                             "'structure=0.3,triggers=0.4,efficiency=0.3'. "
                             "Values are normalized to sum to 1.0.")
    args = parser.parse_args()

    eval_suite = None
    if args.eval_suite and Path(args.eval_suite).exists():
        try:
            eval_suite = json.loads(Path(args.eval_suite).read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"Error: malformed eval-suite JSON '{args.eval_suite}': {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Auto-discover eval-suite.json as sibling of SKILL.md
        skill_dir = Path(args.skill_path).parent
        auto_path = skill_dir / "eval-suite.json"
        if auto_path.exists():
            try:
                eval_suite = json.loads(auto_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                print(f"Warning: malformed eval-suite.json: {e}", file=sys.stderr)

    scores = {
        "structure": score_structure(args.skill_path),
        "triggers": score_triggers(args.skill_path, eval_suite),
        "quality": score_quality(args.skill_path, eval_suite),
        "edges": score_edges(args.skill_path, eval_suite),
        "efficiency": score_efficiency(args.skill_path),
        "composability": score_composability(args.skill_path),
        "runtime": score_runtime(args.skill_path, eval_suite, enabled=args.runtime),
    }

    # Clarity dimension (opt-in, zero default weight)
    if args.clarity:
        scores["clarity"] = score_clarity(args.skill_path)

    # Parse custom weights if provided
    custom_weights = None
    if args.weights:
        custom_weights = {}
        for pair in args.weights.split(","):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                dim_name = k.strip()
                if dim_name not in VALID_DIMENSIONS:
                    print(f"Error: unknown dimension '{dim_name}' — valid: {', '.join(sorted(VALID_DIMENSIONS))}", file=sys.stderr)
                    sys.exit(1)
                try:
                    custom_weights[dim_name] = float(v.strip())
                except ValueError:
                    print(f"Error: invalid weight value for '{dim_name}': '{v.strip()}' — expected a number", file=sys.stderr)
                    sys.exit(1)

    composite_result = compute_composite(scores, custom_weights)

    result = {
        "skill_path": args.skill_path,
        "composite_score": composite_result["score"],
        "score_type": composite_result["score_type"],
        "confidence": {
            "measured": composite_result["measured_dimensions"],
            "total": composite_result["total_dimensions"],
            "weight_coverage": composite_result["weight_coverage"],
            "unmeasured": composite_result["unmeasured"],
        },
        "warnings": composite_result["warnings"],
        "confidence_notes": composite_result.get("confidence_notes", {}),
        "dimensions": {k: v["score"] for k, v in scores.items()},
        "issues": {k: v["issues"] for k, v in scores.items() if v["issues"]},
        "details": {k: v["details"] for k, v in scores.items() if v["details"]},
    }

    # Diff analysis (opt-in)
    if args.diff:
        diff_analysis = score_diff(args.skill_path, args.diff_ref)
        result["diff_analysis"] = diff_analysis
        # Wire explain_score_change into diff output
        # Use current scores as "new" and zeros as "old" placeholder
        # (real old scores would come from previous run's JSON)
        current_scores = {k: v["score"] for k, v in scores.items() if v["score"] >= 0}
        explanations = explain_score_change({}, current_scores, diff_analysis)
        if explanations:
            result["score_explanations"] = explanations

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n{'='*60}")
        score_type = "Structural+Runtime" if args.runtime else "Structural"
        print(f"  SkillForge {score_type} Score: {composite_result['score']}/100")

        # Show confidence warning
        mc = composite_result['measured_dimensions']
        tc = composite_result['total_dimensions']
        wc = composite_result['weight_coverage']
        if mc < tc:
            print(f"  [{mc}/{tc} dimensions measured, {wc:.0%} weight coverage]")

        print(f"{'='*60}")
        for dim, data in scores.items():
            s = data["score"]
            indicator = "\u2713" if s >= 70 else "\u25b3" if s >= 50 else "\u2717" if s >= 0 else "\u2014"
            score_str = f"{s}" if s >= 0 else "n/a"
            print(f"  {indicator} {dim:15s} {score_str:>5s}")
        print(f"{'='*60}")

        # Show warnings
        for warning in composite_result.get("warnings", []):
            print(f"\n  \u26a0  {warning}")

        all_issues = [i for v in scores.values() for i in v["issues"]]
        if all_issues:
            print(f"\n  Issues found:")
            for issue in all_issues:
                print(f"    \u2022 {issue}")
        print()


if __name__ == "__main__":
    main()


# Backward compatibility for external importers
from scoring.diff import explain_score_change
from shared import extract_description as _extract_description
_read_skill_safe = read_skill_safe
