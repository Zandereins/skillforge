#!/usr/bin/env python3
"""SkillForge Report Generator

Combines improvement history (JSONL) + current score into a shareable
GitHub-flavored markdown report.

Usage:
    python3 generate-report.py results.jsonl SKILL.md [--output FILE] [--json]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCRIPT_DIR = Path(__file__).parent

from shared import load_jsonl_safe, read_skill_safe

# Import terminal_art for grade system and heatmap
from terminal_art import score_to_grade, render_heatmap

# Optional: achievements
try:
    import importlib as _il
    achievements_mod = _il.import_module("achievements")
except Exception:
    achievements_mod = None


# ---------------------------------------------------------------------------
# Cached progress module loader (avoids redundant spec_from_file_location)
# ---------------------------------------------------------------------------

_progress_mod_cache: Optional[Any] = None


def _get_progress_module():
    """Load progress.py once and cache the module object."""
    global _progress_mod_cache
    if _progress_mod_cache is not None:
        return _progress_mod_cache
    spec_path = SCRIPT_DIR / "progress.py"
    spec = importlib.util.spec_from_file_location("progress", str(spec_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _progress_mod_cache = mod
    return mod


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_current_score(skill_path: str) -> dict[str, Any]:
    """Run score-skill.py --json and return parsed output."""
    scorer = SCRIPT_DIR / "score-skill.py"
    try:
        result = subprocess.run(
            [sys.executable, str(scorer), skill_path, "--json"],
            capture_output=True,
            text=True,
            timeout=60,
            errors="replace",
        )
        if result.returncode != 0:
            return {
                "composite_score": 0,
                "dimensions": {},
                "error": result.stderr.strip() or "scorer exited non-zero",
            }
        data = json.loads(result.stdout)
        dimensions = data.get("dimensions", {})
        return {
            "composite_score": data.get("composite_score", 0),
            "dimensions": {k: v for k, v in dimensions.items() if isinstance(v, (int, float)) and v >= 0},
        }
    except subprocess.TimeoutExpired:
        return {"composite_score": 0, "dimensions": {}, "error": "scorer timed out"}
    except (json.JSONDecodeError, OSError) as exc:
        return {"composite_score": 0, "dimensions": {}, "error": str(exc)}


def load_progress(results_path: str) -> dict[str, Any]:
    """Load ProgressAnalyzer summary from the JSONL results file."""
    try:
        mod = _get_progress_module()
    except Exception as exc:
        return {"error": f"failed to import progress module: {exc}"}

    try:
        analyzer = mod.ProgressAnalyzer(results_path)
        summary = analyzer.generate_summary()
        strategy_stats = analyzer.compute_strategy_stats()
        summary["strategy_stats"] = strategy_stats
        summary["_results_path"] = results_path
        return summary
    except (FileNotFoundError, ValueError) as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"progress analysis failed: {exc}"}


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

from terminal_art import progress_bar as render_progress_bar


def trend_arrow(trend: str) -> str:
    """Map trend string to a unicode arrow."""
    return {"improving": "\u2191", "stable": "\u2192", "declining": "\u2193"}.get(trend, "\u2014")


def _fmt(score: Optional[float]) -> str:
    """Format a score for table display, falling back to n/a."""
    if score is None:
        return "n/a"
    return f"{score:.1f}"


def _delta_str(delta: float) -> str:
    """Format a signed delta for display."""
    if delta > 0:
        return f"+{delta:.1f}"
    return f"{delta:.1f}"


def _grade_badge_color(grade: str) -> str:
    """Return a shields.io color string for a letter grade."""
    return {
        "S": "brightgreen",
        "A": "green",
        "B": "yellowgreen",
        "C": "yellow",
        "D": "orange",
        "F": "red",
    }.get(grade, "lightgrey")


def _build_badge_markdown(score: float, grade: str) -> str:
    """Build a shields.io badge markdown string for a SkillForge score."""
    badge_score = f"{score:.1f}"
    color = _grade_badge_color(grade)
    return (
        f"[![SkillForge: {score:.1f} [{grade}]]"
        f"(https://img.shields.io/badge/SkillForge-{badge_score}%2F100_%5B{grade}%5D-{color})]"
        f"(https://github.com/Zandereins/skillforge)"
    )


def _extract_skill_name_from_frontmatter(skill_path: str) -> Optional[str]:
    """Extract the name field from YAML frontmatter, returns None on failure."""
    try:
        content = read_skill_safe(skill_path)
    except (OSError, ValueError):
        return None
    match = re.search(r'^name:\s*"?(.+?)"?\s*$', content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


# ---------------------------------------------------------------------------
# Report renderer
# ---------------------------------------------------------------------------

def format_report(skill_name: str, progress: dict[str, Any], current: dict[str, Any]) -> str:
    """Render the full GitHub-flavored markdown report."""
    lines: list[str] = []
    now = datetime.now(tz=timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Handle empty/error progress gracefully
    if "error" in progress and not progress.get("total_experiments"):
        lines.append(f"# SkillForge Report: {skill_name}")
        lines.append("")
        lines.append("> No improvement data yet. Run `/skillforge:auto` first.")
        lines.append("")
        lines.append(f"---\n*Generated by [SkillForge](https://github.com/Zandereins/skillforge) | {timestamp}*")
        return "\n".join(lines)

    outcomes = progress.get("outcomes", {})
    keeps = outcomes.get("keep", 0)
    discards = outcomes.get("discard", 0)
    errors = outcomes.get("crash", 0)
    total = progress.get("total_experiments", 0)

    baseline_entry = progress.get("baseline")
    current_best_entry = progress.get("current_best")

    baseline_composite: Optional[float] = None
    baseline_scores: dict[str, float] = {}
    if baseline_entry:
        baseline_composite = baseline_entry.get("composite")
        baseline_scores = baseline_entry.get("scores", {})

    current_composite = current.get("composite_score", 0.0)
    current_dims = current.get("dimensions", {})

    if baseline_composite is None and current_best_entry:
        baseline_composite = current_best_entry.get("composite")
        baseline_scores = current_best_entry.get("scores", {})

    trends = progress.get("trends", {})

    # --- Header ---
    lines.append(f"# SkillForge Report: {skill_name}")
    lines.append("")
    lines.append(f"**Date:** {date_str}  ")
    lines.append(f"**Iterations:** {total} ({keeps} kept / {discards} discarded / {errors} errors)")
    lines.append("")

    # --- Score Summary table ---
    lines.append("## Structural Score Summary")
    lines.append("")
    lines.append("> These scores measure file structure, keyword coverage, and eval suite")
    lines.append("> completeness — not runtime effectiveness. Enable `--runtime` for validated scoring.")
    lines.append("")
    lines.append("| Dimension | Baseline | Current | Delta | Grade | Trend |")
    lines.append("|-----------|----------|---------|-------|-------|-------|")

    all_dims = sorted(set(list(baseline_scores.keys()) + list(current_dims.keys())))
    for dim in all_dims:
        b = baseline_scores.get(dim)
        c = current_dims.get(dim)
        if b is None and c is None:
            continue
        delta = (c - b) if (b is not None and c is not None) else None
        arrow = trend_arrow(trends.get(dim, ""))
        delta_cell = _delta_str(delta) if delta is not None else "n/a"
        dim_grade = score_to_grade(c) if c is not None else "n/a"
        lines.append(f"| {dim.capitalize()} | {_fmt(b)} | {_fmt(c)} | {delta_cell} | {dim_grade} | {arrow} |")

    # Composite row
    comp_baseline = baseline_composite
    comp_delta = (current_composite - comp_baseline) if comp_baseline is not None else None
    comp_delta_cell = _delta_str(comp_delta) if comp_delta is not None else "n/a"
    current_grade = score_to_grade(current_composite)
    lines.append(
        f"| **Composite** | **{_fmt(comp_baseline)}** | **{_fmt(current_composite)}** "
        f"| **{comp_delta_cell}** | **{current_grade}** | **\u2014** |"
    )
    lines.append("")

    # --- Progress bars ---
    lines.append("## Progress")
    lines.append("")
    lines.append("```")
    if comp_baseline is not None:
        bar_b = render_progress_bar(comp_baseline)
        lines.append(f"Baseline:  {bar_b}  {comp_baseline:.0f}/100")
    bar_c = render_progress_bar(current_composite)
    delta_label = f"  ({_delta_str(comp_delta)})" if comp_delta is not None else ""
    lines.append(f"Current:   {bar_c}  {current_composite:.0f}/100  [{current_grade}]{delta_label}")
    lines.append("```")
    lines.append("")

    # --- Dimension Heatmap ---
    # Load iteration data from JSONL for heatmap rendering
    _results_path = progress.get("_results_path")
    if render_heatmap is not None and _results_path:
        try:
            _raw_entries = load_jsonl_safe(_results_path)
            _heatmap_iters = [
                {"dimensions": e["scores"]}
                for e in _raw_entries
                if e.get("scores") and isinstance(e["scores"], dict)
            ]

            if len(_heatmap_iters) >= 3:
                # Collect all dimension names
                _hdims = sorted(set(
                    d for it in _heatmap_iters for d in it.get("dimensions", {}).keys()
                ))
                if _hdims:
                    hmap = render_heatmap(_hdims, _heatmap_iters)
                    lines.append("## Dimension Heatmap")
                    lines.append("")
                    lines.append("```")
                    lines.append(hmap)
                    lines.append("```")
                    lines.append("")
        except (OSError, ValueError):
            pass

    # --- Top Improvements ---
    lines.append("## Top Improvements")
    lines.append("")
    all_exps: list[dict[str, Any]] = []
    # Collect kept experiments from progress summary
    # ProgressAnalyzer doesn't expose the raw list in generate_summary, so we
    # reconstruct from current_best and latest_kept references where available.
    # The best we can do without re-importing is to surface current_best + latest_kept.
    # For a richer list, we re-use the strategy stats' kept counts as a signal.
    kept_exps: list[dict[str, Any]] = []
    for candidate in (progress.get("current_best"), progress.get("latest_kept")):
        if candidate and candidate.get("status") == "keep":
            if candidate not in kept_exps:
                kept_exps.append(candidate)

    # Re-load raw experiments for the top improvements section
    try:
        mod = _get_progress_module()
        _raw_path = progress.get("_results_path")
        if _raw_path:
            analyzer = mod.ProgressAnalyzer(_raw_path)
            kept_exps = [e for e in analyzer.experiments if e.get("status") == "keep"]
    except Exception:
        pass

    if kept_exps:
        sorted_exps = sorted(kept_exps, key=lambda e: e.get("delta", 0), reverse=True)
        for i, exp in enumerate(sorted_exps[:5], start=1):
            exp_num = exp.get("exp", "?")
            desc = exp.get("description", "no description")[:80]
            delta_val = exp.get("delta", 0)
            lines.append(f"{i}. **Exp {exp_num}** — {desc} ({_delta_str(delta_val)})")
        lines.append("")
    else:
        lines.append("No improvements yet.")
        lines.append("")

    # --- Strategy Effectiveness ---
    strategy_stats: dict[str, Any] = progress.get("strategy_stats", {})
    if strategy_stats:
        lines.append("## Strategy Effectiveness")
        lines.append("")
        lines.append("| Strategy | Keep Rate | Avg Delta | Uses |")
        lines.append("|----------|-----------|-----------|------|")
        sorted_strategies = sorted(
            strategy_stats.items(),
            key=lambda kv: kv[1].get("keep_rate", 0),
            reverse=True,
        )
        for strategy, stats in sorted_strategies:
            keep_rate = f"{stats.get('keep_rate', 0):.0%}"
            avg_delta = _delta_str(stats.get("avg_delta", 0))
            uses = stats.get("total", 0)
            lines.append(f"| {strategy} | {keep_rate} | {avg_delta} | {uses} |")
        lines.append("")

    # --- Recommendation ---
    lines.append("## Recommendation")
    lines.append("")

    if current_composite >= 90:
        lines.append("Skill is production-ready.")
    elif all_dims and all(current_dims.get(d, 0) >= 80 for d in all_dims if current_dims.get(d, -1) >= 0):
        lines.append("All dimensions healthy. Consider runtime evaluation for final polish.")
    else:
        # Find lowest-scoring measured dimension
        scored = {d: s for d, s in current_dims.items() if isinstance(s, (int, float)) and s >= 0}
        if scored:
            weakest_dim = min(scored, key=lambda d: scored[d])
            weakest_score = scored[weakest_dim]
            lines.append(
                f"Focus on **{weakest_dim}** ({weakest_score:.0f}/100) \u2014 largest remaining gap."
            )
        else:
            lines.append("Run the scorer with an eval suite to get dimension-level guidance.")

    lines.append("")

    # Achievements badge line
    if achievements_mod is not None and _results_path:
        try:
            _ach_state = load_jsonl_safe(_results_path)
            _ach_current = {
                "composite": current_composite,
                "dimensions": current_dims,
            }
            _ach_result = achievements_mod.check_achievements(
                _ach_state, _ach_current, skill_name, check_only=True
            )
            _all_ach = _ach_result.get("all_unlocked", [])
            if _all_ach:
                badges = " ".join(a.get("badge", "") for a in _all_ach)
                total_ach = _ach_result["total_unlocked"]
                avail_ach = _ach_result["total_available"]
                lines.append(f"**Achievements:** {badges} ({total_ach}/{avail_ach})")
                lines.append("")
        except Exception:
            pass

    # Share section with badge
    total_iters = progress.get("total_experiments", 0)
    before_str = f"{comp_baseline:.1f}" if comp_baseline is not None else "?"
    after_str = f"{current_composite:.1f}"
    badge_md = _build_badge_markdown(current_composite, current_grade)

    lines.append("---")
    lines.append("")
    lines.append("## Share")
    lines.append("")
    lines.append("Add this badge to your skill's README:")
    lines.append("")
    lines.append("```markdown")
    lines.append(badge_md)
    lines.append("```")
    lines.append("")
    lines.append("Share your result:")
    lines.append(f"> Just ran SkillForge on my Claude Code skill: {before_str} \u2192 {after_str}"
                 f" in {total_iters} iterations, zero manual work."
                 f" https://github.com/Zandereins/skillforge")
    lines.append("")
    lines.append(
        f"---\n*Generated by [SkillForge](https://github.com/Zandereins/skillforge) | {timestamp}*"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON output builder
# ---------------------------------------------------------------------------

def build_json_output(
    skill_name: str,
    progress: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    """Build the structured JSON output dict."""
    outcomes = progress.get("outcomes", {})
    keeps = outcomes.get("keep", 0)
    discards = outcomes.get("discard", 0)
    errors = outcomes.get("crash", 0)
    total = progress.get("total_experiments", 0)

    baseline_entry = progress.get("baseline")
    baseline_composite: Optional[float] = baseline_entry.get("composite") if baseline_entry else None

    current_composite = current.get("composite_score", 0.0)
    delta = round(current_composite - baseline_composite, 1) if baseline_composite is not None else None

    # Top improvements
    kept_exps: list[dict[str, Any]] = []
    top_improvements: list[dict[str, Any]] = []
    try:
        mod = _get_progress_module()
        _raw_path = progress.get("_results_path")
        if _raw_path:
            analyzer = mod.ProgressAnalyzer(_raw_path)
            kept_exps = [e for e in analyzer.experiments if e.get("status") == "keep"]
    except Exception:
        pass

    if kept_exps:
        for exp in sorted(kept_exps, key=lambda e: e.get("delta", 0), reverse=True)[:5]:
            top_improvements.append({
                "exp": exp.get("exp"),
                "description": exp.get("description", ""),
                "delta": exp.get("delta", 0),
            })

    # Recommendation
    current_dims = current.get("dimensions", {})
    scored = {d: s for d, s in current_dims.items() if isinstance(s, (int, float)) and s >= 0}
    if current_composite >= 90:
        recommendation = "Skill is production-ready."
    elif scored and all(s >= 80 for s in scored.values()):
        recommendation = "All dimensions healthy. Consider runtime evaluation for final polish."
    elif scored:
        weakest_dim = min(scored, key=lambda d: scored[d])
        recommendation = f"Focus on {weakest_dim} ({scored[weakest_dim]:.0f}/100)"
    else:
        recommendation = "Run scorer with eval suite for dimension guidance."

    grade = score_to_grade(current_composite)
    badge_markdown = _build_badge_markdown(current_composite, grade)

    return {
        "skill_name": skill_name,
        "baseline_composite": baseline_composite,
        "current_composite": current_composite,
        "delta": delta,
        "grade": grade,
        "iterations": total,
        "keeps": keeps,
        "discards": discards,
        "errors": errors,
        "top_improvements": top_improvements,
        "strategy_stats": progress.get("strategy_stats", {}),
        "recommendation": recommendation,
        "badge_markdown": badge_markdown,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a shareable SkillForge markdown report"
    )
    parser.add_argument("results_path", help="Path to skillforge-results.jsonl")
    parser.add_argument("skill_path", help="Path to SKILL.md")
    parser.add_argument("--output", help="Write report to FILE instead of stdout")
    parser.add_argument("--json", action="store_true", help="Output structured JSON")
    args = parser.parse_args()

    skill_path = Path(args.skill_path)
    if not skill_path.exists():
        print(f"Error: skill file not found: {Path(args.skill_path).name}", file=sys.stderr)
        sys.exit(1)

    progress = load_progress(args.results_path)
    current = load_current_score(args.skill_path)

    # Resolve skill name: prefer scorer output, then frontmatter, then filename
    skill_name = (
        _extract_skill_name_from_frontmatter(args.skill_path)
        or skill_path.stem
    )

    if args.json:
        output = json.dumps(build_json_output(skill_name, progress, current), indent=2)
    else:
        output = format_report(skill_name, progress, current)

    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
