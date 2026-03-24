#!/usr/bin/env python3
"""Schliff Auto-Improve — Autonomous Self-Driving Loop

Drives the entire improvement loop without a Claude session:
  baseline score → gradient → top-3 exploration → score → keep best/revert → log → repeat

60-70% of gradients are deterministic (frontmatter fixes, noise removal, TODO cleanup).
These are applied directly. Medium/low-confidence changes fall back to claude -p.

Usage:
    python3 auto-improve.py SKILL.md [--max-iterations N] [--dry-run] [--json]
    python3 auto-improve.py SKILL.md --resume  # Resume from JSONL state file

Stopping conditions:
  - composite >= 98 → stop
  - all dims >= 90 → stop
  - 3 consecutive patch errors → stop (unpatchable skill)
  - EMA ROI < 0.1 for 5 consecutive keep/discard steps → stop
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


SCRIPT_DIR = Path(__file__).parent

# Import terminal_art for grade system
from terminal_art import score_to_grade, grade_colored, progress_bar, sparkline

# --- Imports from sibling modules ---

# Use underscore aliases for clean imports (wrapper modules for hyphenated originals)
import score_skill as scorer
import text_gradient as gradient_mod
from shared import load_eval_suite

# Optional imports — use underscore aliases where available
_MISSING_MODULES: list[tuple[str, str]] = []

try:
    import achievements as achievements_mod
except ImportError as e:
    achievements_mod = None
    _MISSING_MODULES.append(("achievements", str(e)))

try:
    import episodic_store
except ImportError as e:
    episodic_store = None
    _MISSING_MODULES.append(("episodic_store", str(e)))

try:
    import meta_report
except ImportError as e:
    meta_report = None
    _MISSING_MODULES.append(("meta_report", str(e)))

try:
    import parallel_runner
except ImportError as e:
    parallel_runner = None
    _MISSING_MODULES.append(("parallel_runner", str(e)))


# --- State Management ---

def _state_path(skill_path: str) -> Path:
    """Get JSONL state file path for a skill."""
    skill_dir = Path(skill_path).parent
    state_dir = skill_dir / ".schliff"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "auto-improve-state.jsonl"


MAX_STATE_SIZE = 5_000_000  # 5 MB


def _load_state(skill_path: str) -> list[dict]:
    """Load state entries from JSONL file."""
    path = _state_path(skill_path)
    if not path.exists():
        return []
    # Guard against unbounded state files
    try:
        if path.stat().st_size > MAX_STATE_SIZE:
            # Read all lines and backup removed entries before truncation
            lines = path.read_text(encoding="utf-8").splitlines()
            removed = lines[:-100]
            if removed:
                backup_path = Path.home() / ".schliff" / "state-backup.jsonl"
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                # Cap state-backup at 10MB
                try:
                    if backup_path.exists() and backup_path.stat().st_size > 10_485_760:
                        blines = backup_path.read_text(encoding="utf-8").splitlines()
                        backup_path.write_text("\n".join(blines[-500:]) + "\n", encoding="utf-8")
                except OSError:
                    pass
                with open(backup_path, "a", encoding="utf-8") as bf:
                    for rline in removed:
                        bf.write(rline + "\n")
                print(
                    f"Warning: state file exceeds {MAX_STATE_SIZE} bytes, "
                    f"truncating to recent entries. "
                    f"Backup of {len(removed)} removed entries at {backup_path}",
                    file=sys.stderr,
                )
            else:
                print(f"Warning: state file exceeds {MAX_STATE_SIZE} bytes, truncating to recent entries", file=sys.stderr)
            lines = lines[-100:]
            # Rewrite truncated file to actually reduce size on disk
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        else:
            lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        print(f"Warning: cannot read state file: {e}", file=sys.stderr)
        return []
    entries = []
    for line in lines:
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _append_state(skill_path: str, entry: dict) -> None:
    """Append a state entry to the JSONL file."""
    path = _state_path(skill_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# --- Scoring ---

def _score_skill(skill_path: str, eval_suite: Optional[dict] = None) -> dict:
    """Score a skill and return composite + dimensions."""
    scores = {
        "structure": scorer.score_structure(skill_path),
        "triggers": scorer.score_triggers(skill_path, eval_suite),
        "quality": scorer.score_quality(skill_path, eval_suite),
        "edges": scorer.score_edges(skill_path, eval_suite),
        "efficiency": scorer.score_efficiency(skill_path),
        "composability": scorer.score_composability(skill_path),
        "clarity": scorer.score_clarity(skill_path),
    }

    # Runtime is opt-in (expensive, invokes claude CLI)
    scores["runtime"] = scorer.score_runtime(skill_path, eval_suite, enabled=False)

    composite_result = scorer.compute_composite(scores)
    dimensions = {k: v["score"] for k, v in scores.items()}

    return {
        "composite": composite_result["score"],
        "dimensions": dimensions,
        "measured": composite_result["measured_dimensions"],
    }


# --- ROI Stopping ---

def _has_dimension_regression(
    current_score: dict, new_score: dict, threshold: float = 15
) -> Optional[tuple[str, float, float]]:
    """Check if any dimension regressed by more than threshold points.

    Returns (dim_name, old_val, new_val) if regression found, else None.
    """
    old_dims = current_score.get("dimensions", {})
    new_dims = new_score.get("dimensions", {})
    for dim_name, old_val in old_dims.items():
        if not isinstance(old_val, (int, float)) or old_val < 0:
            continue
        new_val = new_dims.get(dim_name, old_val)
        if not isinstance(new_val, (int, float)) or new_val < 0:
            continue
        dim_drop = old_val - new_val
        if dim_drop > threshold:
            return (dim_name, old_val, new_val)
    return None


def _compute_ema_roi(state: list[dict], alpha: float = 0.3) -> float:
    """Compute EMA of deltas for adaptive plateau detection.

    Uses exponential moving average over absolute deltas of keep/discard entries.
    Returns infinity if fewer than 3 qualifying entries exist.
    """
    qualifying = [e for e in state if e.get("status") in ("keep", "discard")]
    if len(qualifying) < 3:
        return float("inf")

    ema = 0.0
    for entry in qualifying:
        delta = entry.get("delta", 0)
        ema = alpha * abs(delta) + (1 - alpha) * ema
    return ema


def _compute_relative_roi(delta: float, current_composite: float) -> float:
    """Compute relative ROI: delta / remaining headroom.

    A +0.5 at score 95 (headroom 5) = 0.1 relative ROI.
    A +0.5 at score 50 (headroom 50) = 0.01 relative ROI.
    """
    headroom = 100 - current_composite
    if headroom <= 0:
        return float("inf") if delta > 0 else 0.0
    return delta / headroom


def _should_stop(state: list[dict], current_score: dict) -> tuple[bool, str]:
    """Determine if the loop should stop.

    Returns (should_stop, reason).
    """
    composite = current_score.get("composite", 0)
    dims = current_score.get("dimensions", {})

    # Stop if near-perfect
    if composite >= 98:
        return True, f"composite >= 98 ({composite})"

    # Stop if all measurable dims >= 90
    measurable = {k: v for k, v in dims.items() if isinstance(v, (int, float)) and v >= 0}
    if measurable and all(v >= 90 for v in measurable.values()):
        return True, f"all dimensions >= 90"

    # EMA-based plateau detection: EMA ROI < 0.1 for 5 consecutive steps
    qualifying = [e for e in state if e.get("status") in ("keep", "discard", "error")]

    # Fast stop: 3 consecutive errors means the file can't be improved further
    if len(qualifying) >= 3:
        last_3 = qualifying[-3:]
        if all(e.get("status") == "error" for e in last_3):
            return True, "3 consecutive errors — skill may not be patchable"

    # Filter to keep/discard only for EMA calculation
    qualifying = [e for e in qualifying if e.get("status") in ("keep", "discard")]
    if len(qualifying) >= 5:
        # Replay the EMA step-by-step (same alpha and formula as _compute_ema_roi)
        # and inspect the actual EMA value at each of the last 5 steps.
        alpha = 0.3
        ema_val = 0.0
        ema_values: list[float] = []
        for entry in qualifying:
            delta = abs(entry.get("delta", 0.0))
            ema_val = alpha * delta + (1 - alpha) * ema_val
            ema_values.append(ema_val)
        if len(ema_values) >= 5 and all(v < 0.1 for v in ema_values[-5:]):
            return True, f"EMA ROI plateau: last 5 EMA values all < 0.1 ({ema_values[-5:]!r})"

    return False, ""


# --- Parallel Trigger ---

def _should_trigger_parallel(state: list[dict], current_score: dict) -> bool:
    """Check if parallel branching should be triggered."""
    if parallel_runner is None:
        return False

    # Count consecutive discards at end of state
    consecutive_discards = 0
    for entry in reversed(state):
        if entry.get("status") == "discard":
            consecutive_discards += 1
        else:
            break

    # Compute gap to target
    composite = current_score.get("composite", 0)
    gap = 100 - composite

    return parallel_runner.should_trigger_parallel(
        consecutive_discards=consecutive_discards,
        gap_to_target=gap,
    )


# --- Main Loop ---

def run_auto_improve(
    skill_path: str,
    max_iterations: int = 30,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """Run the autonomous improvement loop.

    Args:
        skill_path: Path to SKILL.md
        max_iterations: Maximum number of iterations
        dry_run: If True, don't write to files
        verbose: Print progress to stderr

    Returns:
        Summary dict with iterations, final score, improvements
    """
    skill_path = str(Path(skill_path).resolve())
    eval_suite = load_eval_suite(skill_path)

    # Load existing state for resume
    state = _load_state(skill_path)
    start_iteration = len(state)

    # Baseline score
    if verbose:
        print(f"Scoring baseline...", file=sys.stderr)

    # Clear scorer cache for fresh reads
    scorer.invalidate_cache(skill_path)
    baseline = _score_skill(skill_path, eval_suite)

    if start_iteration == 0:
        baseline_entry = {
            "iteration": 0,
            "status": "baseline",
            "composite": baseline["composite"],
            "dimensions": baseline["dimensions"],
            "delta": 0,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "patch_applied": None,
        }
        if not dry_run:
            _append_state(skill_path, baseline_entry)
        state.append(baseline_entry)

    if verbose:
        print(f"Baseline: {baseline['composite']}/100 ({baseline['measured']} dims)", file=sys.stderr)

    # Recall relevant episodes if available
    if episodic_store and not dry_run:
        episodes = episodic_store.recall(f"improve skill {Path(skill_path).parent.name}", top_k=3)
        if episodes and verbose:
            print(f"Recalled {len(episodes)} relevant past episodes", file=sys.stderr)

    # Predict best strategy if available
    predicted_strategies = None
    if meta_report:
        try:
            prediction = meta_report.predict_best_strategy(
                baseline["dimensions"],
                skill_domain=Path(skill_path).parent.name,
            )
            if prediction.get("available") and prediction.get("predictions"):
                predicted_strategies = [p["strategy"] for p in prediction["predictions"]]
                if verbose:
                    print(f"Predicted best strategies: {predicted_strategies[:3]}", file=sys.stderr)
        except Exception as e:
            print(f"Warning: strategy prediction failed: {e}", file=sys.stderr)

    _loop_start = time.monotonic()
    current_score = baseline
    improvements = 0
    total_delta = 0
    reason = ""
    should_stop = False
    iteration = start_iteration

    for iteration in range(start_iteration + 1, start_iteration + max_iterations + 1):
        if verbose:
            print(f"\n--- Iteration {iteration} ---", file=sys.stderr)

        # Check stopping conditions
        should_stop, reason = _should_stop(state, current_score)
        if should_stop:
            if verbose:
                print(f"Stopping: {reason}", file=sys.stderr)
            break

        # Check parallel trigger
        if _should_trigger_parallel(state, current_score):
            if verbose:
                print("Triggering parallel branching (stuck or large gap)...", file=sys.stderr)
            # Parallel mode is informational only in auto-improve
            # (actual worktree management requires git context)

        # Clear cache and compute gradients
        scorer.invalidate_cache(skill_path)
        gradients = gradient_mod.compute_gradients(
            skill_path, eval_suite=eval_suite, include_clarity=True
        )

        if not gradients:
            if verbose:
                print("No gradients found — skill may be optimized", file=sys.stderr)
            break

        # Generate patches for deterministic fixes
        patches = gradient_mod.generate_patches(skill_path, gradients)

        if not patches:
            if verbose:
                print("No auto-applicable patches — only manual fixes remain", file=sys.stderr)
            break

        # Top-3 exploration: try up to 3 patches, keep the best result
        # (First 3 iterations use top-1 only to avoid wasted work on already-good skills)
        explore_width = 1 if iteration <= 3 else min(3, len(patches))
        candidates_to_try = patches[:explore_width]

        backup_content = Path(skill_path).read_text(encoding="utf-8")

        best_result = None  # (new_score, delta, patch, content_after)
        best_delta = -float("inf")
        patch_errors = []

        for patch_candidate in candidates_to_try:
            if verbose and explore_width > 1:
                print(f"  Trying: [{patch_candidate['dimension']}] {patch_candidate['issue']}", file=sys.stderr)
            elif verbose:
                print(f"Applying: [{patch_candidate['dimension']}] {patch_candidate['issue']}", file=sys.stderr)

            # Restore to baseline state before each candidate
            if not dry_run:
                Path(skill_path).write_text(backup_content, encoding="utf-8")
                scorer.invalidate_cache(skill_path)

            result = gradient_mod.apply_patches(skill_path, [patch_candidate], dry_run=dry_run)

            if result["errors"]:
                patch_errors.append((patch_candidate, result["errors"]))
                if verbose:
                    print(f"  Patch errors: {result['errors']}", file=sys.stderr)
                continue

            if result["applied"] == 0:
                if verbose:
                    print("  Patch had no effect — skipping", file=sys.stderr)
                continue

            # Score after patch
            scorer.invalidate_cache(skill_path)
            new_score = _score_skill(skill_path, eval_suite)
            delta = round(new_score["composite"] - current_score["composite"], 1)

            if verbose and explore_width > 1:
                print(f"  Score: {current_score['composite']} → {new_score['composite']} (delta: {delta:+.1f})", file=sys.stderr)

            # Dimension guard: reject patches that tank any dim by >15 points
            regression = _has_dimension_regression(current_score, new_score, threshold=15)
            if regression:
                if verbose:
                    dim_name, old_val, new_val = regression
                    print(f"  Dimension guard: {dim_name} dropped {old_val} → {new_val}", file=sys.stderr)
                continue

            if delta > best_delta:
                content_after = Path(skill_path).read_text(encoding="utf-8") if not dry_run else None
                best_result = (new_score, delta, patch_candidate, content_after)
                best_delta = delta

        # Determine outcome from exploration
        if best_result and best_delta >= 0:
            new_score, delta, chosen_patch, content_after = best_result
            status = "keep"
            if not dry_run and content_after is not None:
                Path(skill_path).write_text(content_after, encoding="utf-8")
                scorer.invalidate_cache(skill_path)
            old_composite = current_score["composite"]
            current_score = new_score
            if delta > 0:
                improvements += 1
            total_delta += delta
            top_patch = chosen_patch
            if verbose:
                rel_roi = _compute_relative_roi(delta, old_composite)
                print(f"✓ Keep (composite: {new_score['composite']}, rel_roi: {rel_roi:.3f})", file=sys.stderr)
        else:
            status = "discard"
            # Pick the first patch for logging if no best result
            top_patch = candidates_to_try[0]
            delta = best_delta if best_result else 0
            new_score = current_score
            # Revert
            if not dry_run:
                Path(skill_path).write_text(backup_content, encoding="utf-8")
                scorer.invalidate_cache(skill_path)
            if verbose:
                if patch_errors and not best_result:
                    print(f"✗ Discard (all {len(candidates_to_try)} patches had errors)", file=sys.stderr)
                else:
                    print(f"✗ Discard (best delta: {best_delta:+.1f})", file=sys.stderr)

        # Handle case where all patches errored
        if patch_errors and not best_result and len(patch_errors) == len(candidates_to_try):
            entry = {
                "iteration": iteration,
                "status": "error",
                "composite": current_score["composite"],
                "dimensions": current_score["dimensions"],
                "delta": 0,
                "patch_applied": f"{top_patch['dimension']}:{top_patch['issue']}",
                "errors": patch_errors[0][1],
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            if not dry_run:
                _append_state(skill_path, entry)
            state.append(entry)
            continue

        # Scoreboard line
        if verbose:
            sc = new_score['composite'] if status == "keep" else current_score['composite']
            bar_w = 20
            filled = min(bar_w, int(round(sc / 100 * bar_w)))
            bar = "\u2588" * filled + "\u2591" * (bar_w - filled)
            sym = "\u2713" if status == "keep" else "\u2717"
            explored = f" [{explore_width} explored]" if explore_width > 1 else ""
            print(f"Iter {iteration:>2}:  {bar}  {sc:.1f}/100  [{delta:+.1f}]  {sym} {status} ({top_patch['dimension']}){explored}", file=sys.stderr)

        entry = {
            "iteration": iteration,
            "status": status,
            "composite": new_score["composite"] if status == "keep" else current_score["composite"],
            "dimensions": new_score["dimensions"] if status == "keep" else current_score["dimensions"],
            "delta": delta,
            "patch_applied": f"{top_patch['dimension']}:{top_patch['issue']}",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if not dry_run:
            _append_state(skill_path, entry)
        state.append(entry)

        # Emit episode for cross-session learning
        if episodic_store and not dry_run:
            try:
                episodic_store.store_episode(
                    skill=Path(skill_path).parent.name,
                    strategy=top_patch["dimension"],
                    outcome=status,
                    delta=delta,
                    learning=f"Auto-applied {top_patch['issue']}: {status} (delta: {delta:+.1f})",
                    domain="auto-improve",
                )
            except Exception as e:
                print(f"Warning: episodic store failed: {e}", file=sys.stderr)

    # Final summary
    elapsed = time.monotonic() - _loop_start
    final_score = _score_skill(skill_path, eval_suite) if not dry_run else current_score

    # Sparkline of score progression
    score_history = [e.get("composite", 0) for e in state if e.get("status") in ("keep", "baseline")]
    sparkline_str = sparkline(score_history) if len(score_history) >= 2 else ""

    summary = {
        "skill_path": skill_path,
        "iterations": max(0, len(state) - 1),  # Exclude baseline
        "improvements": improvements,
        "total_delta": round(total_delta, 1),
        "baseline_composite": baseline["composite"],
        "final_composite": final_score["composite"],
        "final_dimensions": final_score["dimensions"],
        "stop_reason": reason if should_stop else "max_iterations" if iteration >= start_iteration + max_iterations else "no_patches",
        "dry_run": dry_run,
        "elapsed_seconds": round(elapsed, 1),
        "sparkline": sparkline_str,
    }

    return summary


def main():
    parser = argparse.ArgumentParser(description="Schliff Auto-Improve — Autonomous Loop Driver")
    parser.add_argument("skill_path", help="Path to SKILL.md")
    parser.add_argument("--max-iterations", type=int, default=30, help="Maximum iterations (default: 30)")
    parser.add_argument("--dry-run", action="store_true", help="Don't write changes, just show plan")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose progress output")
    # Resume is implicit: state is loaded from auto-improve-state.jsonl if it exists
    args = parser.parse_args()

    if _MISSING_MODULES:
        for mod_name, mod_err in _MISSING_MODULES:
            print(f"Warning: {mod_name} unavailable: {mod_err}", file=sys.stderr)

    if not Path(args.skill_path).exists():
        print(f"Error: {args.skill_path} not found", file=sys.stderr)
        sys.exit(1)

    summary = run_auto_improve(
        skill_path=args.skill_path,
        max_iterations=args.max_iterations,
        dry_run=args.dry_run,
        verbose=args.verbose or not args.json,
    )

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        elapsed = summary.get("elapsed_seconds", 0)
        mins, secs = divmod(int(elapsed), 60)
        time_str = f"{mins}m{secs:02d}s" if mins else f"{secs}s"

        print(f"\n  Schliff Auto-Improve Complete")
        print(f"  {'─' * 50}")
        sc = summary['final_composite']
        bar = progress_bar(sc, 20)
        grade = score_to_grade(sc)
        grade_str = grade_colored(grade)
        print(f"  Score:  {summary['baseline_composite']:.0f} \u2192 {sc:.0f}/100  {bar}  ({summary['total_delta']:+.1f})  {grade_str}")
        print(f"  Iters:  {summary['iterations']}  |  Kept: {summary['improvements']}  |  Time: {time_str}")
        if summary.get('sparkline'):
            print(f"  Trend:  {summary['sparkline']}  ({summary['baseline_composite']:.0f} \u2192 {sc:.0f})")
        print(f"  Stop:   {summary['stop_reason']}")
        if summary['dry_run']:
            print(f"  (dry run \u2014 no changes written)")

        # Check and display achievements
        if achievements_mod and not summary['dry_run']:
            try:
                skill_content = Path(summary['skill_path']).read_text(encoding="utf-8")
                _name_m = re.search(r"^name:\s*(.+?)$", skill_content, re.MULTILINE)
                _skill_name = _name_m.group(1).strip() if _name_m else Path(summary['skill_path']).parent.name
                _state = _load_state(summary['skill_path'])
                _current = {
                    "composite": sc,
                    "dimensions": summary.get('final_dimensions', {}),
                }
                _ach = achievements_mod.check_achievements(_state, _current, _skill_name)
                newly = _ach.get('newly_unlocked', [])
                if newly:
                    print()
                    for a in newly:
                        print(f"  {a.get('badge', '')}  Achievement Unlocked: {a.get('name', '?')} \u2014 {a.get('desc', '')}")
            except Exception:
                pass

        print()


if __name__ == "__main__":
    main()
