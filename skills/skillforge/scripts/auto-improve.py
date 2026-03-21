#!/usr/bin/env python3
from __future__ import annotations
"""SkillForge Auto-Improve — Autonomous Self-Driving Loop

Drives the entire improvement loop without a Claude session:
  baseline score → gradient → auto-apply top-1 → score → keep/revert → log → repeat

60-70% of gradients are deterministic (frontmatter fixes, noise removal, TODO cleanup).
These are applied directly. Medium/low-confidence changes fall back to claude -p.

Usage:
    python3 auto-improve.py SKILL.md [--max-iterations N] [--dry-run] [--json]
    python3 auto-improve.py SKILL.md --resume  # Resume from JSONL state file

ROI-based stopping:
  - marginal_roi < 0.2 for 3 consecutive windows → stop
  - composite >= 98 → stop
  - all dims >= 90 → stop
"""

import argparse
import copy
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


SCRIPT_DIR = Path(__file__).parent


# --- Imports from sibling modules ---

sys.path.insert(0, str(SCRIPT_DIR))
import importlib
scorer = importlib.import_module("score-skill")
gradient_mod = importlib.import_module("text-gradient")

# Optional imports
try:
    episodic_store = importlib.import_module("episodic-store")
except ImportError as e:
    episodic_store = None
    print(f"Warning: episodic-store unavailable: {e}", file=sys.stderr)

try:
    meta_report = importlib.import_module("meta-report")
except ImportError as e:
    meta_report = None
    print(f"Warning: meta-report unavailable: {e}", file=sys.stderr)

try:
    parallel_runner = importlib.import_module("parallel-runner")
except ImportError as e:
    parallel_runner = None
    print(f"Warning: parallel-runner unavailable: {e}", file=sys.stderr)


# --- State Management ---

def _state_path(skill_path: str) -> Path:
    """Get JSONL state file path for a skill."""
    skill_dir = Path(skill_path).parent
    state_dir = skill_dir / ".skillforge"
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
            print(f"Warning: state file exceeds {MAX_STATE_SIZE} bytes, truncating to recent entries", file=sys.stderr)
            # Read only tail of file (last ~100 entries)
            lines = path.read_text(encoding="utf-8").splitlines()
            lines = lines[-100:]
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


def _load_eval_suite(skill_path: str) -> Optional[dict]:
    """Auto-discover eval-suite.json."""
    skill_dir = Path(skill_path).parent
    auto_path = skill_dir / "eval-suite.json"
    if auto_path.exists():
        try:
            return json.loads(auto_path.read_text())
        except json.JSONDecodeError:
            pass
    return None


# --- ROI Stopping ---

def _compute_marginal_roi(state: list[dict], window: int = 5) -> float:
    """Compute marginal ROI over the last N iterations.

    ROI = sum of positive deltas in window / window size.
    """
    if len(state) < window:
        return float("inf")  # Not enough data

    recent = state[-window:]
    total_delta = sum(e.get("delta", 0) for e in recent if e.get("status") == "keep")
    return total_delta / window


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

    # ROI-based stopping: marginal_roi < 0.2 for 3 consecutive windows
    if len(state) >= 15:
        window = 5
        low_roi_count = 0
        for offset in range(3):
            start = -(window * (offset + 1))
            end = -(window * offset) if offset > 0 else None
            window_entries = state[start:end] if end else state[start:]
            roi = _compute_marginal_roi(window_entries, window=len(window_entries))
            if roi < 0.2:
                low_roi_count += 1

        if low_roi_count >= 3:
            return True, "marginal ROI < 0.2 for 3 consecutive windows"

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
    eval_suite = _load_eval_suite(skill_path)

    # Load existing state for resume
    state = _load_state(skill_path)
    start_iteration = len(state)

    # Baseline score
    if verbose:
        print(f"Scoring baseline...", file=sys.stderr)

    # Clear scorer cache for fresh reads
    scorer._file_cache.pop(str(Path(skill_path).resolve()), None)
    baseline = _score_skill(skill_path, eval_suite)

    if start_iteration == 0:
        baseline_entry = {
            "iteration": 0,
            "status": "baseline",
            "composite": baseline["composite"],
            "dimensions": baseline["dimensions"],
            "delta": 0,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
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
        scorer._file_cache.pop(str(Path(skill_path).resolve()), None)
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

        # Save backup
        backup_content = Path(skill_path).read_text(encoding="utf-8")

        # Apply top patch
        top_patch = patches[0]
        if verbose:
            print(f"Applying: [{top_patch['dimension']}] {top_patch['issue']}", file=sys.stderr)

        if dry_run:
            result = gradient_mod.apply_patches(skill_path, [top_patch], dry_run=True)
        else:
            result = gradient_mod.apply_patches(skill_path, [top_patch], dry_run=False)

        if result["errors"]:
            if verbose:
                print(f"Patch errors: {result['errors']}", file=sys.stderr)
            # Restore backup
            if not dry_run:
                Path(skill_path).write_text(backup_content, encoding="utf-8")
            entry = {
                "iteration": iteration,
                "status": "error",
                "composite": current_score["composite"],
                "dimensions": current_score["dimensions"],
                "delta": 0,
                "patch_applied": f"{top_patch['dimension']}:{top_patch['issue']}",
                "errors": result["errors"],
                "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            if not dry_run:
                _append_state(skill_path, entry)
            state.append(entry)
            continue

        if result["applied"] == 0:
            if verbose:
                print("Patch had no effect — skipping", file=sys.stderr)
            continue

        # Score after patch
        scorer._file_cache.pop(str(Path(skill_path).resolve()), None)
        new_score = _score_skill(skill_path, eval_suite)
        delta = round(new_score["composite"] - current_score["composite"], 1)

        if verbose:
            print(f"Score: {current_score['composite']} → {new_score['composite']} (delta: {delta:+.1f})", file=sys.stderr)

        # Keep or revert
        if delta >= 0:
            status = "keep"
            current_score = new_score
            improvements += 1
            total_delta += delta
            if verbose:
                print(f"✓ Keep (composite: {new_score['composite']})", file=sys.stderr)
        else:
            status = "discard"
            # Revert
            if not dry_run:
                Path(skill_path).write_text(backup_content, encoding="utf-8")
                scorer._file_cache.pop(str(Path(skill_path).resolve()), None)
            if verbose:
                print(f"✗ Discard (regression: {delta:+.1f})", file=sys.stderr)

        entry = {
            "iteration": iteration,
            "status": status,
            "composite": new_score["composite"] if status == "keep" else current_score["composite"],
            "dimensions": new_score["dimensions"] if status == "keep" else current_score["dimensions"],
            "delta": delta,
            "patch_applied": f"{top_patch['dimension']}:{top_patch['issue']}",
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
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
    final_score = _score_skill(skill_path, eval_suite) if not dry_run else current_score

    summary = {
        "skill_path": skill_path,
        "iterations": len(state) - 1,  # Exclude baseline
        "improvements": improvements,
        "total_delta": round(total_delta, 1),
        "baseline_composite": baseline["composite"],
        "final_composite": final_score["composite"],
        "final_dimensions": final_score["dimensions"],
        "stop_reason": reason if should_stop else "max_iterations" if iteration >= start_iteration + max_iterations else "no_patches",
        "dry_run": dry_run,
    }

    return summary


def main():
    parser = argparse.ArgumentParser(description="SkillForge Auto-Improve — Autonomous Loop Driver")
    parser.add_argument("skill_path", help="Path to SKILL.md")
    parser.add_argument("--max-iterations", type=int, default=30, help="Maximum iterations (default: 30)")
    parser.add_argument("--dry-run", action="store_true", help="Don't write changes, just show plan")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose progress output")
    parser.add_argument("--resume", action="store_true", help="Resume from previous state")
    args = parser.parse_args()

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
        print(f"\n{'='*60}")
        print(f"  Auto-Improve Complete")
        print(f"{'='*60}")
        print(f"  Iterations:  {summary['iterations']}")
        print(f"  Improvements: {summary['improvements']}")
        print(f"  Score:       {summary['baseline_composite']} → {summary['final_composite']} "
              f"({summary['total_delta']:+.1f})")
        print(f"  Stop reason: {summary['stop_reason']}")
        if summary['dry_run']:
            print(f"  (DRY RUN — no changes written)")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
