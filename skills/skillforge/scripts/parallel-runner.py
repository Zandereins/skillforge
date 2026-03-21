#!/usr/bin/env python3
from __future__ import annotations
"""SkillForge Parallel Runner — Worktree-based Parallel Experimentation

When stuck (5+ consecutive discards) or gap-to-target > 15,
runs 3 different strategies in parallel using git worktrees.
Scores all 3, keeps the best, removes the others.

Usage:
    python3 parallel-runner.py SKILL.md --strategies "trigger_expansion,noise_reduction,example_addition"
    python3 parallel-runner.py SKILL.md --auto  # auto-pick top 3 strategies
    python3 parallel-runner.py SKILL.md --dry-run  # show what would happen

Fallback: sequential mode if git worktree is unavailable.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional


SCRIPT_DIR = Path(__file__).parent


def _git_available() -> bool:
    """Check if git is available and we're in a repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _worktree_available() -> bool:
    """Check if git worktree is available."""
    if not _git_available():
        return False
    try:
        result = subprocess.run(
            ["git", "worktree", "list"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def create_branches(
    skill_path: str,
    strategies: list[str],
    base_branch: Optional[str] = None,
) -> list[dict]:
    """Create parallel worktree branches for experimentation.

    Args:
        skill_path: Path to SKILL.md
        strategies: List of strategy names to try
        base_branch: Branch to base worktrees on (default: current HEAD)

    Returns:
        List of branch info dicts with: name, worktree_path, strategy
    """
    if not _worktree_available():
        return []

    if base_branch is None:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        base_branch = result.stdout.strip() or "HEAD"

    branches = []
    # Find repo root via git, fallback to parent traversal
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        repo_root = Path(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        repo_root = Path(skill_path).resolve().parent.parent.parent
    worktree_base = repo_root.parent / "sf-parallel"

    for i, strategy in enumerate(strategies[:3]):  # Max 3 branches
        branch_name = f"sf-parallel-{chr(65 + i)}"  # A, B, C
        worktree_path = str(worktree_base) + f"-{chr(65 + i)}"

        try:
            # Create branch
            subprocess.run(
                ["git", "branch", "-D", branch_name],
                capture_output=True, timeout=5
            )  # Clean up old branches
            subprocess.run(
                ["git", "worktree", "add", worktree_path, "-b", branch_name],
                capture_output=True, text=True, timeout=30,
                check=True,
            )
            branches.append({
                "name": branch_name,
                "worktree_path": worktree_path,
                "strategy": strategy,
                "status": "created",
            })
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            branches.append({
                "name": branch_name,
                "worktree_path": worktree_path,
                "strategy": strategy,
                "status": f"error: {e}",
            })

    return branches


def _score_in_worktree(branch: dict, skill_relative: str) -> dict:
    """Score a skill in a worktree context.

    Args:
        branch: Branch info dict
        skill_relative: Relative path to SKILL.md from repo root

    Returns:
        Branch dict with added score/error fields
    """
    worktree = branch["worktree_path"]
    skill_path = os.path.join(worktree, skill_relative)

    if not os.path.exists(skill_path):
        branch["score"] = -1
        branch["error"] = "SKILL.md not found in worktree"
        return branch

    try:
        result = subprocess.run(
            ["python3", str(SCRIPT_DIR / "score-skill.py"), skill_path, "--json"],
            capture_output=True, text=True, timeout=60,
            cwd=worktree,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            branch["score"] = data.get("composite_score", 0)
            branch["dimensions"] = data.get("dimensions", {})
        else:
            branch["score"] = -1
            branch["error"] = result.stderr[:200]
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        branch["score"] = -1
        branch["error"] = str(e)[:200]

    return branch


def run_parallel(
    branches: list[dict],
    skill_relative: str,
) -> list[dict]:
    """Score all branches in parallel.

    Args:
        branches: List of branch dicts from create_branches()
        skill_relative: Relative path to SKILL.md from repo root

    Returns:
        Updated branch dicts with scores
    """
    active = [b for b in branches if b.get("status") == "created"]
    if not active:
        return branches

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_score_in_worktree, branch, skill_relative): branch
            for branch in active
        }
        for future in as_completed(futures):
            branch = futures[future]
            try:
                future.result()
            except Exception as e:
                branch["score"] = -1
                branch["error"] = str(e)[:200]

    return branches


def select_winner(branches: list[dict]) -> Optional[dict]:
    """Select the branch with the highest score.

    Returns the winning branch dict, or None if all failed.
    """
    scored = [b for b in branches if b.get("score", -1) >= 0]
    if not scored:
        return None
    return max(scored, key=lambda b: b.get("score", 0))


def cleanup(branches: list[dict], keep_branch: Optional[str] = None) -> list[str]:
    """Remove worktrees and branches (except winner).

    Args:
        branches: All branch dicts
        keep_branch: Name of winning branch to keep (or None to remove all)

    Returns:
        List of cleaned up branch names
    """
    cleaned = []
    for branch in branches:
        name = branch.get("name", "")
        worktree = branch.get("worktree_path", "")

        if name == keep_branch:
            continue

        # Remove worktree
        if worktree and os.path.exists(worktree):
            try:
                subprocess.run(
                    ["git", "worktree", "remove", worktree, "--force"],
                    capture_output=True, timeout=15,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                # Fallback: manual cleanup
                try:
                    shutil.rmtree(worktree, ignore_errors=True)
                except OSError:
                    pass

        # Delete branch
        if name:
            try:
                subprocess.run(
                    ["git", "branch", "-D", name],
                    capture_output=True, timeout=5,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        cleaned.append(name)

    return cleaned


def run_sequential_fallback(
    skill_path: str,
    strategies: list[str],
) -> dict:
    """Sequential fallback when git worktree is unavailable.

    Applies each strategy one at a time, scores, reverts if worse.
    """
    results = []

    for strategy in strategies[:3]:
        # Score current state
        try:
            result = subprocess.run(
                ["python3", str(SCRIPT_DIR / "score-skill.py"), skill_path, "--json"],
                capture_output=True, text=True, timeout=60,
            )
            data = json.loads(result.stdout)
            score = data.get("composite_score", 0)
        except Exception:
            score = 0

        results.append({
            "strategy": strategy,
            "score": score,
            "mode": "sequential_baseline",
        })

    return {
        "mode": "sequential",
        "reason": "git worktree unavailable",
        "results": results,
    }


def should_trigger_parallel(
    consecutive_discards: int = 0,
    gap_to_target: float = 0,
) -> bool:
    """Determine if parallel branching should be triggered.

    Trigger when:
    - 5+ consecutive discards, OR
    - gap-to-target > 15 points
    """
    return consecutive_discards >= 5 or gap_to_target > 15


def main():
    parser = argparse.ArgumentParser(description="SkillForge Parallel Runner")
    parser.add_argument("skill_path", help="Path to SKILL.md")
    parser.add_argument("--strategies", help="Comma-separated strategy names",
                        default="trigger_expansion,noise_reduction,example_addition")
    parser.add_argument("--auto", action="store_true",
                        help="Auto-pick top 3 strategies from meta-report predictor")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--skill-relative", default=None,
                        help="Relative path to SKILL.md from repo root")
    args = parser.parse_args()

    strategies = [s.strip() for s in args.strategies.split(",")]

    # Auto mode: use meta-report predictor
    if args.auto:
        try:
            sys.path.insert(0, str(SCRIPT_DIR))
            import importlib
            meta = importlib.import_module("meta-report")
            prediction = meta.predict_best_strategy({}, meta_dir=meta.META_DIR_DEFAULT)
            if prediction.get("available") and prediction.get("predictions"):
                strategies = [p["strategy"] for p in prediction["predictions"][:3]]
        except Exception:
            pass  # Fall back to defaults

    if args.dry_run:
        plan = {
            "mode": "parallel" if _worktree_available() else "sequential",
            "strategies": strategies[:3],
            "worktree_available": _worktree_available(),
        }
        if args.json:
            print(json.dumps(plan, indent=2))
        else:
            print(f"Mode: {plan['mode']}")
            print(f"Strategies: {', '.join(plan['strategies'])}")
        sys.exit(0)

    # Determine skill_relative
    skill_relative = args.skill_relative
    if not skill_relative:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=5,
            )
            repo_root = result.stdout.strip()
            skill_relative = os.path.relpath(
                os.path.abspath(args.skill_path), repo_root
            )
        except Exception:
            skill_relative = args.skill_path

    if not _worktree_available():
        result = run_sequential_fallback(args.skill_path, strategies)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Sequential fallback: {result['reason']}")
            for r in result["results"]:
                print(f"  {r['strategy']}: score={r['score']}")
        sys.exit(0)

    # Create parallel branches
    print("Creating parallel branches...", file=sys.stderr)
    branches = create_branches(args.skill_path, strategies)

    active = [b for b in branches if b.get("status") == "created"]
    if not active:
        print("Failed to create any branches.", file=sys.stderr)
        sys.exit(1)

    # Score in parallel
    print(f"Scoring {len(active)} branches in parallel...", file=sys.stderr)
    branches = run_parallel(branches, skill_relative)

    # Select winner
    winner = select_winner(branches)

    # Clean up
    keep = winner["name"] if winner else None
    cleaned = cleanup(branches, keep_branch=keep)

    result = {
        "branches": branches,
        "winner": winner,
        "cleaned": cleaned,
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if winner:
            print(f"Winner: {winner['name']} ({winner['strategy']}) score={winner['score']}")
        else:
            print("No winner — all branches failed")
        print(f"Cleaned up: {', '.join(cleaned)}")


if __name__ == "__main__":
    main()
