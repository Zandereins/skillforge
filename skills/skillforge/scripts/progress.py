#!/usr/bin/env python3
"""
Progress tracking and reporting for SkillForge improvement cycles.

Reads JSONL results logs and produces formatted progress summaries with
trend analysis, velocity tracking, and goal estimation.

Usage:
    python progress.py <results.jsonl> [--json] [--since N] [--chart]

Options:
    --json      Output machine-readable JSON format
    --since N   Show only the last N experiments
    --chart     Include ASCII chart of score progression
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
import math


class ProgressAnalyzer:
    """Analyzes experiment progression from JSONL results."""

    def __init__(self, results_path: str) -> None:
        """
        Initialize analyzer with a results JSONL file.

        Args:
            results_path: Path to skillforge-results.jsonl file
        """
        self.results_path = Path(results_path)
        self.experiments: List[Dict[str, Any]] = []
        self._load_experiments()

    def _load_experiments(self) -> None:
        """Load and parse all experiments from JSONL file."""
        if not self.results_path.exists():
            raise FileNotFoundError(f"Results file not found: {self.results_path}")

        with open(self.results_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        self.experiments.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        print(f"Warning: Invalid JSON on line: {line[:50]}...", file=sys.stderr)
                        continue

    def get_baseline(self) -> Optional[Dict[str, Any]]:
        """Get the baseline (first) experiment if available."""
        if self.experiments and self.experiments[0].get("status") == "baseline":
            return self.experiments[0]
        # Find first with status=baseline
        for exp in self.experiments:
            if exp.get("status") == "baseline":
                return exp
        return None

    def get_current_best(self) -> Optional[Dict[str, Any]]:
        """Get the best kept experiment."""
        best = None
        for exp in self.experiments:
            if exp.get("status") == "keep":
                if best is None or exp.get("composite", 0) > best.get("composite", 0):
                    best = exp
        return best

    def get_latest_kept(self) -> Optional[Dict[str, Any]]:
        """Get the most recent kept experiment."""
        for exp in reversed(self.experiments):
            if exp.get("status") == "keep":
                return exp
        return None

    def count_outcomes(self) -> Tuple[int, int, int]:
        """
        Count experiment outcomes.

        Returns:
            Tuple of (keep_count, discard_count, crash_count)
        """
        keep = sum(1 for e in self.experiments if e.get("status") == "keep")
        discard = sum(1 for e in self.experiments if e.get("status") == "discard")
        crash = sum(1 for e in self.experiments if e.get("status") == "crash")
        return keep, discard, crash

    def analyze_trends(self) -> Dict[str, str]:
        """
        Analyze per-dimension trends.

        Returns:
            Dict mapping dimension name to trend ('improving', 'stable', 'declining')
        """
        kept_exps = [e for e in self.experiments if e.get("status") == "keep"]
        if len(kept_exps) < 2:
            return {}

        scores = {e.get("exp"): e.get("scores", {}) for e in kept_exps}
        dimensions = set()
        for score_dict in scores.values():
            dimensions.update(score_dict.keys())

        trends = {}
        for dim in dimensions:
            values = [scores[e_num].get(dim, 0) for e_num in sorted(scores.keys())]
            if len(values) >= 2:
                early = values[: len(values) // 2]
                late = values[len(values) // 2 :]
                early_avg = sum(early) / len(early)
                late_avg = sum(late) / len(late)

                if late_avg > early_avg * 1.02:
                    trends[dim] = "improving"
                elif late_avg < early_avg * 0.98:
                    trends[dim] = "declining"
                else:
                    trends[dim] = "stable"

        return trends

    def get_pass_rate_trend(self) -> List[Tuple[int, str]]:
        """
        Get binary eval pass rate trend across kept experiments.

        Returns:
            List of (exp_number, pass_rate_string) tuples
        """
        trend = []
        for exp in self.experiments:
            if exp.get("status") == "keep" and "pass_rate" in exp:
                trend.append((exp.get("exp"), exp.get("pass_rate")))
        return trend

    def get_streaks(self) -> Tuple[int, str, int]:
        """
        Analyze consecutive keep/discard streaks.

        Returns:
            Tuple of (streak_length, streak_type, streak_end_exp)
        """
        if not self.experiments:
            return 0, "", 0

        current_streak = 1
        current_type = self.experiments[-1].get("status")
        streak_type = current_type if current_type in ("keep", "discard") else ""
        streak_end = self.experiments[-1].get("exp", 0)

        for exp in reversed(self.experiments[:-1]):
            status = exp.get("status")
            if status == current_type and status in ("keep", "discard"):
                current_streak += 1
            else:
                break

        return current_streak, streak_type, streak_end

    def estimate_iterations_to_goal(self, goal: float) -> Optional[int]:
        """
        Estimate iterations needed to reach goal composite score.

        Args:
            goal: Target composite score (0-100)

        Returns:
            Estimated iterations, or None if no clear trend
        """
        kept_exps = [e for e in self.experiments if e.get("status") == "keep"]
        if len(kept_exps) < 2:
            return None

        # Simple linear regression on composite scores
        x_vals = list(range(len(kept_exps)))
        y_vals = [e.get("composite", 0) for e in kept_exps]

        mean_x = sum(x_vals) / len(x_vals)
        mean_y = sum(y_vals) / len(y_vals)

        if mean_y >= goal:
            return 0

        numerator = sum((x_vals[i] - mean_x) * (y_vals[i] - mean_y) for i in range(len(x_vals)))
        denominator = sum((x_vals[i] - mean_x) ** 2 for i in range(len(x_vals)))

        if denominator == 0:
            return None

        slope = numerator / denominator
        if slope <= 0:
            return None

        current = y_vals[-1]
        remaining = goal - current
        iterations = int(math.ceil(remaining / slope))
        return max(1, iterations)

    def get_time_metrics(self) -> Tuple[float, float]:
        """
        Get time elapsed and average time per iteration.

        Returns:
            Tuple of (total_seconds, avg_seconds_per_iteration)
        """
        if not self.experiments:
            return 0, 0

        total_ms = sum(e.get("duration_ms", 0) for e in self.experiments)
        total_sec = total_ms / 1000
        avg_per_iter = total_sec / len(self.experiments) if self.experiments else 0

        return total_sec, avg_per_iter

    def get_experiment_velocity(self) -> float:
        """
        Get experiments per hour.

        Returns:
            Experiments per hour
        """
        total_sec, _ = self.get_time_metrics()
        if total_sec == 0:
            return 0
        hours = total_sec / 3600
        return len(self.experiments) / hours if hours > 0 else 0

    def format_duration(self, seconds: float) -> str:
        """Format duration in human-readable form."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            return f"{seconds / 60:.1f}m"
        else:
            return f"{seconds / 3600:.1f}h"

    # --- Strategy types for meta-learning ---
    STRATEGY_TYPES = [
        "trigger_expansion",
        "example_addition",
        "noise_reduction",
        "edge_coverage",
        "structural_fix",
        "progressive_disclosure",
        "composability_fix",
        "recovery_combo",
    ]

    # Keywords used to infer strategy type from experiment descriptions
    _STRATEGY_KEYWORDS = {
        "trigger_expansion": ["synonym", "trigger", "description", "boundary", "negative boundary"],
        "example_addition": ["example", "input/output", "before/after", "sample"],
        "noise_reduction": ["compress", "trim", "remove", "verbose", "noise", "filler", "concise", "lean"],
        "edge_coverage": ["edge", "malformed", "corner", "error", "fallback", "unicode"],
        "structural_fix": ["frontmatter", "header", "section", "structure", "format", "lint"],
        "progressive_disclosure": ["reference", "extract", "progressive", "disclosure", "split"],
        "composability_fix": ["scope", "handoff", "composab", "conflict", "boundary"],
        "recovery_combo": ["recovery", "combo", "revert", "fix", "workaround"],
    }

    def _infer_strategy(self, description: str) -> Optional[str]:
        """Infer strategy type from experiment description using keywords."""
        desc_lower = description.lower()
        best_match = None
        best_count = 0
        for strategy, keywords in self._STRATEGY_KEYWORDS.items():
            count = sum(1 for kw in keywords if kw in desc_lower)
            if count > best_count:
                best_count = count
                best_match = strategy
        return best_match if best_count > 0 else None

    def compute_strategy_stats(self) -> Dict[str, Dict[str, Any]]:
        """Compute effectiveness stats per strategy type.

        Groups experiments by strategy_type (explicit field or inferred from
        description), then computes keep_rate and avg_delta per strategy.
        """
        strategy_data: Dict[str, List[Dict[str, Any]]] = {}

        for exp in self.experiments:
            if exp.get("status") in ("baseline",):
                continue

            # Explicit strategy_type takes precedence
            strategy = exp.get("strategy_type")
            if not strategy:
                strategy = self._infer_strategy(exp.get("description", ""))
            if not strategy:
                strategy = "unknown"

            if strategy not in strategy_data:
                strategy_data[strategy] = []
            strategy_data[strategy].append(exp)

        stats = {}
        for strategy, exps in strategy_data.items():
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
            }

        return stats

    def get_recommended_strategy_order(self) -> List[str]:
        """Return strategies sorted by effectiveness (keep_rate * avg_delta)."""
        stats = self.compute_strategy_stats()
        return sorted(
            stats.keys(),
            key=lambda s: stats[s]["effectiveness"],
            reverse=True,
        )

    def classify_eval_health(self, window: int = 10) -> Dict[str, List[str]]:
        """Classify eval test cases as mastered, blocked, or flaky.

        Looks at the last `window` kept experiments to determine test health:
        - mastered: always passes for 10+ iterations (reduce weight)
        - blocked: always fails (needs investigation)
        - flaky: inconsistent (unreliable signal)
        """
        kept_exps = [e for e in self.experiments if e.get("status") == "keep"][-window:]

        if len(kept_exps) < 3:
            return {"mastered": [], "blocked": [], "flaky": [], "healthy": []}

        # Collect pass/fail history per test case from pass_rate or binary results
        # Since we track composite scores, not individual test results,
        # classify based on score stability per dimension
        dim_scores: Dict[str, List[float]] = {}
        for exp in kept_exps:
            scores = exp.get("scores", {})
            for dim, val in scores.items():
                if not isinstance(val, (int, float)) or val < 0:
                    continue  # skip unmeasured sentinel (-1)
                if dim not in dim_scores:
                    dim_scores[dim] = []
                dim_scores[dim].append(val)

        result: Dict[str, List[str]] = {"mastered": [], "blocked": [], "flaky": [], "healthy": []}

        for dim, values in dim_scores.items():
            if not values:
                continue
            avg = sum(values) / len(values)
            variance = sum((v - avg) ** 2 for v in values) / len(values)

            if avg >= 95 and variance < 5:
                result["mastered"].append(dim)
            elif avg < 50 and variance < 10:
                result["blocked"].append(dim)
            elif variance > 50:
                result["flaky"].append(dim)
            else:
                result["healthy"].append(dim)

        return result

    def generate_summary(
        self,
        goal: Optional[float] = None,
        since: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate comprehensive progress summary.

        Args:
            goal: Optional target composite score
            since: If set, only include last N experiments

        Returns:
            Dictionary with all progress metrics
        """
        exps = self.experiments
        if since:
            exps = exps[-since:]

        baseline = self.get_baseline()
        current_best = self.get_current_best()
        latest_kept = self.get_latest_kept()
        keep, discard, crash = self.count_outcomes()
        trends = self.analyze_trends()
        pass_rates = self.get_pass_rate_trend()
        streak_len, streak_type, streak_end = self.get_streaks()
        total_sec, avg_per_iter = self.get_time_metrics()
        velocity = self.get_experiment_velocity()

        summary: Dict[str, Any] = {
            "total_experiments": len(exps),
            "current_exp": exps[-1].get("exp", 0) if exps else 0,
            "baseline": baseline,
            "current_best": current_best,
            "latest_kept": latest_kept,
            "outcomes": {"keep": keep, "discard": discard, "crash": crash},
            "trends": trends,
            "pass_rate_trend": pass_rates,
            "streak": {
                "length": streak_len,
                "type": streak_type,
                "end_exp": streak_end,
            },
            "time": {
                "total_seconds": total_sec,
                "avg_per_iteration": avg_per_iter,
                "velocity_per_hour": velocity,
            },
        }

        if goal and current_best:
            est = self.estimate_iterations_to_goal(goal)
            summary["goal_estimate"] = {
                "target": goal,
                "current": current_best.get("composite", 0),
                "estimated_iterations": est,
            }

        # Strategy meta-learning
        strategy_stats = self.compute_strategy_stats()
        if strategy_stats:
            summary["strategies"] = {
                "stats": strategy_stats,
                "recommended_order": self.get_recommended_strategy_order(),
            }

        # Eval health classification
        eval_health = self.classify_eval_health()
        if any(eval_health.values()):
            summary["eval_health"] = eval_health

        return summary

    def format_summary(
        self, summary: Dict[str, Any], include_chart: bool = False
    ) -> str:
        """
        Format summary as human-readable text.

        Args:
            summary: Summary dictionary from generate_summary
            include_chart: Whether to include ASCII chart

        Returns:
            Formatted text string
        """
        lines = []

        current_exp = summary["current_exp"]
        baseline = summary["baseline"]
        current_best = summary["current_best"]
        outcomes = summary["outcomes"]
        trends = summary["trends"]
        pass_rates = summary["pass_rate_trend"]
        streak = summary["streak"]
        time_data = summary["time"]

        lines.append("=" * 60)
        lines.append("SkillForge Progress Report")
        lines.append("=" * 60)
        lines.append("")

        lines.append(f"Experiment {current_exp} | Total: {summary['total_experiments']}")
        keep, discard, crash = outcomes["keep"], outcomes["discard"], outcomes["crash"]
        total = keep + discard + crash
        if total > 0:
            lines.append(
                f"Outcomes: {keep} kept "
                f"({100*keep/total:.0f}%) | "
                f"{discard} discarded | "
                f"{crash} crashed"
            )
        lines.append("")

        if baseline and current_best:
            baseline_comp = baseline.get("composite", 0)
            best_comp = current_best.get("composite", 0)
            delta = best_comp - baseline_comp

            lines.append(f"Baseline Composite: {baseline_comp:.1f}")
            lines.append(f"Current Best:       {best_comp:.1f}")
            lines.append(f"Improvement:        +{delta:.1f}")
            lines.append("")

            if "scores" in baseline and "scores" in current_best:
                lines.append("Per-Dimension Scores:")
                lines.append("-" * 40)
                base_scores = baseline["scores"]
                curr_scores = current_best["scores"]
                for dim in sorted(base_scores.keys()):
                    b = base_scores.get(dim, 0)
                    c = curr_scores.get(dim, 0)
                    d = c - b
                    trend_marker = ""
                    if dim in trends:
                        if trends[dim] == "improving":
                            trend_marker = " ↑"
                        elif trends[dim] == "declining":
                            trend_marker = " ↓"
                        else:
                            trend_marker = " →"
                    lines.append(f"  {dim:15} {b:6.1f} → {c:6.1f} ({d:+6.1f}){trend_marker}")
                lines.append("")

        if pass_rates:
            lines.append("Binary Eval Pass Rates:")
            for exp_num, rate in pass_rates[-5:]:  # Show last 5
                lines.append(f"  Exp {exp_num}: {rate}")
            lines.append("")

        if streak["type"]:
            lines.append(f"Current Streak: {streak['length']} {streak['type']} "
                        f"(through exp {streak['end_exp']})")
            lines.append("")

        # Time metrics
        total_time = self.format_duration(time_data["total_seconds"])
        avg_time = self.format_duration(time_data["avg_per_iteration"])
        velocity = time_data["velocity_per_hour"]
        lines.append(f"Time: {total_time} total | {avg_time}/iter | {velocity:.1f} exp/hour")
        lines.append("")

        if "goal_estimate" in summary:
            goal_data = summary["goal_estimate"]
            current = goal_data["current"]
            target = goal_data["target"]
            est = goal_data["estimated_iterations"]
            if est:
                lines.append(
                    f"Goal Estimate: {current:.1f} → {target:.1f} "
                    f"(~{est} more iterations)"
                )
                lines.append("")

        # Strategy effectiveness
        if "strategies" in summary and summary["strategies"]["stats"]:
            lines.append("Strategy Effectiveness:")
            lines.append("-" * 50)
            for strategy in summary["strategies"]["recommended_order"]:
                s = summary["strategies"]["stats"][strategy]
                lines.append(
                    f"  {strategy:25s} "
                    f"keep={s['keep_rate']:.0%} "
                    f"avg_delta={s['avg_delta']:+.1f} "
                    f"eff={s['effectiveness']:.2f} "
                    f"({s['kept']}/{s['total']})"
                )
            lines.append("")

        if include_chart and "latest_kept" in summary and summary["latest_kept"]:
            chart = self._generate_chart()
            if chart:
                lines.append("Score Progression (kept exps):")
                lines.append(chart)
                lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)

    def _generate_chart(self, width: int = 50, height: int = 10) -> str:
        """
        Generate ASCII chart of composite scores over kept experiments.

        Args:
            width: Chart width in characters
            height: Chart height in lines

        Returns:
            ASCII chart string
        """
        kept_exps = [e for e in self.experiments if e.get("status") == "keep"]
        if len(kept_exps) < 2:
            return ""

        scores = [e.get("composite", 0) for e in kept_exps]
        min_score = min(scores)
        max_score = max(scores)

        if max_score == min_score:
            return ""

        # Normalize scores to chart height
        normalized = []
        for score in scores:
            norm = (score - min_score) / (max_score - min_score)
            norm = max(0, min(1, norm))
            y = int(norm * (height - 1))
            normalized.append(y)

        # Create chart grid
        chart = [[" " for _ in range(width)] for _ in range(height)]

        # Plot points
        step = max(1, len(normalized) // width)
        for i, y in enumerate(normalized):
            if i % step == 0:
                x = min((i // step), width - 1)
                chart[height - 1 - y][x] = "●"

        # Draw axes
        for row in chart:
            row[0] = "│"
        chart[-1][0] = "└"
        for col in range(width):
            chart[-1][col] = "─"

        result = "\n".join("".join(row) for row in chart)
        result += f"\n{min_score:.0f}" + " " * (width - 10) + f"{max_score:.0f}"
        return result


def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze SkillForge improvement progress"
    )
    parser.add_argument("results_file", help="Path to skillforge-results.jsonl")
    parser.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    parser.add_argument(
        "--since", type=int, help="Show only last N experiments"
    )
    parser.add_argument(
        "--chart", action="store_true", help="Include ASCII chart"
    )
    parser.add_argument(
        "--goal", type=float, help="Target composite score for estimation"
    )
    parser.add_argument(
        "--strategies", action="store_true",
        help="Include strategy meta-learning analysis"
    )

    args = parser.parse_args()

    try:
        analyzer = ProgressAnalyzer(args.results_file)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    summary = analyzer.generate_summary(goal=args.goal, since=args.since)

    if args.json:
        # Convert datetime objects for JSON serialization
        def serialize(obj: Any) -> Any:
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")

        print(json.dumps(summary, default=serialize, indent=2))
    else:
        print(analyzer.format_summary(summary, include_chart=args.chart))


if __name__ == "__main__":
    main()
