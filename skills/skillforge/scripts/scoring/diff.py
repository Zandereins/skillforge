"""Analyze git diff to explain WHY a score changed.

Classifies added/removed lines using signal/noise patterns from
score_efficiency() to determine net quality impact.
"""
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scoring.patterns import _RE_DIFF_SIGNAL, _RE_DIFF_EXAMPLE, _RE_DIFF_NOISE


def score_diff(skill_path: str, diff_ref: str = "HEAD~1") -> dict:
    """Analyze git diff to explain WHY a score changed.

    Classifies added/removed lines using signal/noise patterns from
    score_efficiency() to determine net quality impact.
    """
    if diff_ref.startswith("-"):
        print(f"Invalid diff reference (must not start with '-'): {diff_ref}", file=sys.stderr)
        sys.exit(1)
    if not re.match(r'^[a-zA-Z0-9_.~^@/\-]+$', diff_ref):
        print(f"Invalid diff reference: {diff_ref}", file=sys.stderr)
        sys.exit(1)
    try:
        result = subprocess.run(
            ["git", "diff", diff_ref, "--", skill_path],
            capture_output=True, text=True, timeout=10, errors="replace"
        )
        if result.returncode != 0:
            return {"available": False, "reason": "git diff failed (invalid ref or not in git repo)"}
        if not result.stdout.strip():
            return {"available": False, "reason": "no changes between refs"}
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {"available": False, "reason": "git not available"}

    diff_text = result.stdout
    added_lines = [line[1:] for line in diff_text.split("\n") if line.startswith("+") and not line.startswith("+++")]
    removed_lines = [line[1:] for line in diff_text.split("\n") if line.startswith("-") and not line.startswith("---")]

    def classify_lines(lines: list[str]) -> dict:
        signals = sum(1 for l in lines if _RE_DIFF_SIGNAL.search(l) or _RE_DIFF_EXAMPLE.search(l))
        noise = sum(1 for l in lines if _RE_DIFF_NOISE.search(l))
        neutral = max(0, len(lines) - signals - noise)
        return {"signal": signals, "noise": noise, "neutral": neutral, "total": len(lines)}

    added = classify_lines(added_lines)
    removed = classify_lines(removed_lines)

    net_signal = added["signal"] - removed["signal"]
    net_noise = added["noise"] - removed["noise"]

    return {
        "available": True,
        "diff_ref": diff_ref,
        "added": added,
        "removed": removed,
        "net_change": {
            "signal": net_signal,
            "noise": net_noise,
            "lines": added["total"] - removed["total"],
        },
    }


def explain_score_change(old_scores: dict, new_scores: dict, diff_analysis: dict) -> list:
    """Generate per-dimension explanations for score changes.

    Returns a list of explanation dicts with dimension, delta, and reason.
    """
    explanations = []
    all_dims = set(list(old_scores.keys()) + list(new_scores.keys()))

    for dim in sorted(all_dims):
        old_val = old_scores.get(dim, 0)
        new_val = new_scores.get(dim, 0)
        delta = new_val - old_val

        if abs(delta) < 0.5:
            continue

        reason = f"{dim}: {old_val} -> {new_val} ({delta:+.1f})"

        # Add context from diff if available
        if diff_analysis.get("available"):
            net = diff_analysis.get("net_change", {})
            if dim == "efficiency" and net.get("noise", 0) < 0:
                reason += " (noise removed)"
            elif dim == "efficiency" and net.get("signal", 0) > 0:
                reason += " (signal added)"
            elif dim == "structure" and net.get("lines", 0) < 0:
                reason += " (file shortened)"

        explanations.append({
            "dimension": dim,
            "old": old_val,
            "new": new_val,
            "delta": round(delta, 1),
            "explanation": reason,
        })

    return explanations
