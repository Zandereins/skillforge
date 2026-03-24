#!/usr/bin/env python3
"""Anti-gaming benchmark — demonstrates Schliff's gaming detection.

Scores 6 synthetic SKILL.md files designed to exploit specific dimensions.
Each skill targets a different gaming vector. The benchmark verifies that
Schliff's anti-gaming checks catch and penalize each attempt.

Usage:
    python3 benchmarks/anti-gaming/run.py            # markdown report
    python3 benchmarks/anti-gaming/run.py --json      # machine-readable
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Add scoring modules to path
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "skills" / "schliff" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from scoring import (
    score_structure,
    score_triggers,
    score_quality,
    score_edges,
    score_efficiency,
    score_composability,
    score_clarity,
    compute_composite,
)

# Skills dir relative to this script
_SKILLS_DIR = Path(__file__).resolve().parent / "skills"

# Each benchmark defines: the skill file, the dimension it targets,
# and the anti-gaming mechanism that should catch it.
BENCHMARKS = [
    {
        "file": "inflated-headers.md",
        "target_dimension": "structure",
        "gaming_vector": "Empty section headers to inflate structure score",
        "detection": "Empty-header penalty: sections without content don't count",
    },
    {
        "file": "keyword-stuffing.md",
        "target_dimension": "triggers",
        "gaming_vector": "Repeating the same keyword 50+ times",
        "detection": "TF-IDF weighting: repeated terms get diminishing returns",
    },
    {
        "file": "fake-examples.md",
        "target_dimension": "efficiency",
        "gaming_vector": "Copy-pasting identical examples 15 times",
        "detection": "Near-duplicate dedup: repeated lines count once",
    },
    {
        "file": "contradiction-skill.md",
        "target_dimension": "clarity",
        "gaming_vector": "Contradictory always/never instructions",
        "detection": "Contradiction detection: always X vs never X on same topic",
    },
    {
        "file": "bloated-preamble.md",
        "target_dimension": "efficiency",
        "gaming_vector": "200 lines of filler, 10 lines of instructions",
        "detection": "Signal-to-noise ratio: hedging/filler language penalized",
    },
    {
        "file": "no-scope.md",
        "target_dimension": "composability",
        "gaming_vector": "No scope boundaries, handoffs, or error behavior",
        "detection": "10 sub-checks: scope, state, I/O, handoffs, errors, etc.",
    },
]


def score_skill(skill_path: str) -> dict:
    """Score a single skill across all dimensions."""
    scores = {
        "structure": score_structure(skill_path),
        "triggers": score_triggers(skill_path, None),
        "quality": score_quality(skill_path, None),
        "edges": score_edges(skill_path, None),
        "efficiency": score_efficiency(skill_path),
        "composability": score_composability(skill_path),
        "clarity": score_clarity(skill_path),
    }
    composite = compute_composite(scores)
    return {
        "scores": scores,
        "composite": composite["score"],
    }


def run_benchmarks() -> list[dict]:
    """Run all benchmarks and return results."""
    results = []
    for bench in BENCHMARKS:
        skill_path = str(_SKILLS_DIR / bench["file"])
        if not Path(skill_path).exists():
            results.append({
                **bench,
                "error": f"File not found: {skill_path}",
            })
            continue

        scored = score_skill(skill_path)
        dim_scores = scored["scores"]
        target_dim = bench["target_dimension"]
        target_data = dim_scores.get(target_dim, {})
        target_score = target_data.get("score", -1)
        target_issues = target_data.get("issues", [])
        target_details = target_data.get("details", {})

        results.append({
            "file": bench["file"],
            "target_dimension": target_dim,
            "gaming_vector": bench["gaming_vector"],
            "detection": bench["detection"],
            "target_score": target_score,
            "target_issues": target_issues,
            "target_details": target_details,
            "composite": scored["composite"],
            "all_scores": {k: v["score"] for k, v in dim_scores.items()},
            # A gaming attempt is "caught" if the targeted dimension
            # scores below 80 (penalized) or has anti-gaming issues flagged.
            "caught": target_score < 80 or any(
                "contradiction" in str(i) or "empty" in str(i)
                or "stuffing" in str(i) or "duplicate" in str(i)
                for i in target_issues
            ),
        })

    return results


def format_markdown(results: list[dict]) -> str:
    """Format results as a markdown report."""
    lines: list[str] = []
    lines.append("# Anti-Gaming Benchmark Results")
    lines.append("")

    caught = sum(1 for r in results if r.get("caught"))
    total = len(results)
    lines.append(f"**{caught}/{total} gaming attempts detected and penalized.**")
    lines.append("")

    lines.append("| Skill | Target Dim | Gaming Vector | Score | Caught |")
    lines.append("|-------|-----------|---------------|-------|--------|")

    for r in results:
        if "error" in r:
            lines.append(f"| {r['file']} | - | ERROR | - | - |")
            continue
        caught_str = "YES" if r["caught"] else "NO"
        lines.append(
            f"| {r['file']} | {r['target_dimension']} "
            f"| {r['gaming_vector'][:50]} | {r['target_score']:.0f}/100 "
            f"| {caught_str} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Detail")
    lines.append("")

    for r in results:
        if "error" in r:
            continue
        lines.append(f"### {r['file']}")
        lines.append("")
        lines.append(f"**Gaming vector:** {r['gaming_vector']}")
        lines.append(f"**Detection mechanism:** {r['detection']}")
        lines.append(f"**Target dimension ({r['target_dimension']}):** {r['target_score']:.0f}/100")
        lines.append(f"**Composite:** {r['composite']}/100")
        if r["target_issues"]:
            lines.append(f"**Issues:** {', '.join(str(i) for i in r['target_issues'])}")
        lines.append(f"**Caught:** {'YES' if r['caught'] else 'NO'}")
        lines.append("")
        lines.append("All dimensions:")
        for dim, score in r["all_scores"].items():
            indicator = " " if score < 0 else "<" if score < 70 else " "
            lines.append(f"  {indicator} {dim}: {score:.0f}/100")
        lines.append("")

    return "\n".join(lines)


def main():
    use_json = "--json" in sys.argv

    results = run_benchmarks()

    if use_json:
        # Serialize, filtering out non-serializable details
        output = []
        for r in results:
            entry = {k: v for k, v in r.items() if k != "target_details"}
            output.append(entry)
        print(json.dumps(output, indent=2))
    else:
        print(format_markdown(results))


if __name__ == "__main__":
    main()
