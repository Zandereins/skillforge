#!/usr/bin/env python3
"""SkillForge Meta-Learning Report — Data-Informed Insights

Reads collected meta-learning data (calibration, strategy, trigger logs)
and surfaces correlations, strategy effectiveness, and threshold
recommendations. Does NOT auto-calibrate — provides data for user decisions.

Usage:
    python3 meta-report.py [--json] [--meta-dir DIR]

Default meta dir: ~/.skillforge/meta/
"""

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional


META_DIR_DEFAULT = Path.home() / ".skillforge" / "meta"


def _load_jsonl(path: Path) -> list[dict]:
    """Load all entries from a JSONL file."""
    entries = []
    if not path.exists():
        return entries
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def analyze_calibration(meta_dir: Path) -> dict:
    """Analyze correlation between static scores and runtime pass rates.

    Shows per-dimension Pearson correlation with runtime_pass_rate.
    """
    entries = _load_jsonl(meta_dir / "calibration-log.jsonl")
    if not entries:
        return {"available": False, "reason": "No calibration data yet. Run evals with --runtime to collect."}

    # Filter entries that have both static scores and runtime results
    valid = [e for e in entries if e.get("static_scores") and e.get("runtime_pass_rate") is not None]
    if len(valid) < 3:
        return {
            "available": True,
            "entries": len(valid),
            "reason": f"Need 3+ entries with runtime data for correlation (have {len(valid)}). Keep running evals.",
        }

    # Compute Pearson correlation per dimension
    dimensions = set()
    for e in valid:
        dimensions.update(e["static_scores"].keys())

    correlations = {}
    runtime_values = [e["runtime_pass_rate"] for e in valid]
    runtime_mean = sum(runtime_values) / len(runtime_values)

    for dim in sorted(dimensions):
        dim_values = [e["static_scores"].get(dim, 0) for e in valid]
        dim_mean = sum(dim_values) / len(dim_values)

        numerator = sum(
            (dim_values[i] - dim_mean) * (runtime_values[i] - runtime_mean)
            for i in range(len(valid))
        )
        denom_x = math.sqrt(sum((v - dim_mean) ** 2 for v in dim_values))
        denom_y = math.sqrt(sum((v - runtime_mean) ** 2 for v in runtime_values))

        if denom_x > 0 and denom_y > 0:
            r = numerator / (denom_x * denom_y)
        else:
            r = 0.0

        correlations[dim] = round(r, 3)

    # Suggest weight adjustments based on correlation
    suggestions = []
    for dim, r in sorted(correlations.items(), key=lambda x: abs(x[1]), reverse=True):
        if r > 0.5:
            suggestions.append(f"  {dim}: r={r:+.3f} — strong positive correlation, consider increasing weight")
        elif r < -0.3:
            suggestions.append(f"  {dim}: r={r:+.3f} — negative correlation, consider decreasing weight")
        else:
            suggestions.append(f"  {dim}: r={r:+.3f} — weak correlation")

    # Generate --weights suggestion
    positive_dims = {d: max(0.05, abs(r)) for d, r in correlations.items() if r > 0}
    if positive_dims:
        total = sum(positive_dims.values())
        weights_str = ",".join(f"{d}={v/total:.2f}" for d, v in sorted(positive_dims.items()))
    else:
        weights_str = None

    return {
        "available": True,
        "entries": len(valid),
        "correlations": correlations,
        "suggestions": suggestions,
        "recommended_weights": weights_str,
    }


def analyze_strategies(meta_dir: Path) -> dict:
    """Analyze strategy effectiveness across all skills.

    Shows keep_rate, avg_delta, and effectiveness per strategy type.
    """
    entries = _load_jsonl(meta_dir / "strategy-log.jsonl")
    if not entries:
        return {"available": False, "reason": "No strategy data yet. Run improvement loops to collect."}

    # Group by strategy_type
    by_strategy: dict[str, list] = defaultdict(list)
    by_domain: dict[str, list] = defaultdict(list)

    for e in entries:
        strategy = e.get("strategy_type", "unknown")
        by_strategy[strategy].append(e)
        domain = e.get("domain", "unknown")
        by_domain[domain].append(e)

    stats = {}
    for strategy, exps in sorted(by_strategy.items()):
        kept = [e for e in exps if e.get("status") == "keep"]
        keep_rate = len(kept) / len(exps) if exps else 0
        deltas = [e.get("delta", 0) for e in kept]
        avg_delta = sum(deltas) / len(deltas) if deltas else 0

        stats[strategy] = {
            "total": len(exps),
            "kept": len(kept),
            "keep_rate": round(keep_rate, 2),
            "avg_delta": round(avg_delta, 2),
            "effectiveness": round(keep_rate * avg_delta, 2),
            "skills": list(set(e.get("skill", "?") for e in exps)),
        }

    # Sort by effectiveness
    ranked = sorted(stats.keys(), key=lambda s: stats[s]["effectiveness"], reverse=True)

    return {
        "available": True,
        "entries": len(entries),
        "strategies": stats,
        "ranked": ranked,
        "domains": {d: len(es) for d, es in by_domain.items()},
    }


def analyze_triggers(meta_dir: Path) -> dict:
    """Analyze trigger threshold effectiveness.

    Shows F1 at current vs alternative thresholds.
    """
    entries = _load_jsonl(meta_dir / "trigger-calibration.jsonl")
    if not entries:
        return {"available": False, "reason": "No trigger calibration data yet."}

    if len(entries) < 5:
        return {
            "available": True,
            "entries": len(entries),
            "reason": f"Need 5+ trigger entries for threshold analysis (have {len(entries)}).",
        }

    # Compute F1 at different thresholds
    thresholds = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
    threshold_results = {}

    for thresh in thresholds:
        tp = fp = tn = fn = 0
        for e in entries:
            expected = e.get("should_trigger", True)
            score = e.get("overlap_score", 0)
            predicted = score >= thresh

            if predicted and expected:
                tp += 1
            elif predicted and not expected:
                fp += 1
            elif not predicted and not expected:
                tn += 1
            else:
                fn += 1

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        threshold_results[thresh] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        }

    best_thresh = max(threshold_results, key=lambda t: threshold_results[t]["f1"])

    return {
        "available": True,
        "entries": len(entries),
        "thresholds": threshold_results,
        "best_threshold": best_thresh,
        "best_f1": threshold_results[best_thresh]["f1"],
    }


def generate_report(meta_dir: Path) -> dict:
    """Generate complete meta-learning report."""
    return {
        "calibration": analyze_calibration(meta_dir),
        "strategies": analyze_strategies(meta_dir),
        "triggers": analyze_triggers(meta_dir),
        "meta_dir": str(meta_dir),
    }


def format_report(report: dict) -> str:
    """Format meta-learning report as human-readable text."""
    lines = []
    lines.append("=" * 70)
    lines.append("  SkillForge Meta-Learning Report")
    lines.append("=" * 70)
    lines.append("")

    # Calibration section
    cal = report.get("calibration", {})
    lines.append("  [1] Static Score ↔ Runtime Correlation")
    lines.append("  " + "-" * 50)
    if not cal.get("available"):
        lines.append(f"  {cal.get('reason', 'No data')}")
    elif cal.get("correlations"):
        for s in cal.get("suggestions", []):
            lines.append(s)
        if cal.get("recommended_weights"):
            lines.append("")
            lines.append(f"  Suggested: --weights \"{cal['recommended_weights']}\"")
    else:
        lines.append(f"  {cal.get('reason', 'Insufficient data')}")
    lines.append("")

    # Strategy section
    strat = report.get("strategies", {})
    lines.append("  [2] Strategy Effectiveness")
    lines.append("  " + "-" * 50)
    if not strat.get("available"):
        lines.append(f"  {strat.get('reason', 'No data')}")
    elif strat.get("ranked"):
        stats = strat["strategies"]
        for strategy in strat["ranked"]:
            s = stats[strategy]
            lines.append(
                f"  {strategy:25s} "
                f"keep={s['keep_rate']:.0%} "
                f"avg_delta={s['avg_delta']:+.1f} "
                f"eff={s['effectiveness']:.2f} "
                f"({s['kept']}/{s['total']})"
            )
    lines.append("")

    # Trigger section
    trig = report.get("triggers", {})
    lines.append("  [3] Trigger Threshold Analysis")
    lines.append("  " + "-" * 50)
    if not trig.get("available"):
        lines.append(f"  {trig.get('reason', 'No data')}")
    elif trig.get("thresholds"):
        for thresh, res in sorted(trig["thresholds"].items()):
            marker = " <-- best" if thresh == trig.get("best_threshold") else ""
            lines.append(
                f"  threshold={thresh:.1f}  "
                f"F1={res['f1']:.3f}  "
                f"P={res['precision']:.3f}  "
                f"R={res['recall']:.3f}"
                f"{marker}"
            )
    else:
        lines.append(f"  {trig.get('reason', 'Insufficient data')}")
    lines.append("")

    lines.append(f"  Data dir: {report.get('meta_dir', 'unknown')}")
    lines.append("=" * 70)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="SkillForge Meta-Learning Report")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--meta-dir", default=None, help=f"Meta data directory (default: {META_DIR_DEFAULT})")
    args = parser.parse_args()

    meta_dir = Path(args.meta_dir) if args.meta_dir else META_DIR_DEFAULT

    report = generate_report(meta_dir)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_report(report))


if __name__ == "__main__":
    main()
