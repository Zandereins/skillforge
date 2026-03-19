#!/usr/bin/env python3
"""SkillForge — Skill Quality Scorer

Computes a composite quality score across 6 dimensions.
Used during the autonomous improvement loop to decide keep/discard.

Usage:
    python score-skill.py /path/to/SKILL.md [--eval-suite eval.json] [--json]

Outputs composite score and per-dimension breakdown.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Optional
from pathlib import Path


def score_structure(skill_path: str) -> dict:
    """Run the bash analyzer and return structure score."""
    script_dir = Path(__file__).parent
    analyze_script = script_dir / "analyze-skill.sh"

    if analyze_script.exists():
        try:
            result = subprocess.run(
                ["bash", str(analyze_script), skill_path],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return {
                    "score": data.get("structure_score", 0),
                    "issues": data.get("issues", []),
                    "details": data
                }
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            pass

    # Fallback: basic inline checks
    return _score_structure_inline(skill_path)


def _score_structure_inline(skill_path: str) -> dict:
    """Fallback structural scoring without the bash script."""
    score = 0
    issues = []

    try:
        content = Path(skill_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"score": 0, "issues": ["file_not_found"], "details": {}}

    lines = content.split("\n")

    # Frontmatter
    if lines and lines[0].strip() == "---":
        score += 10
        if re.search(r"^name:\s*\S+", content, re.MULTILINE):
            score += 10
        else:
            issues.append("missing_name")
        if re.search(r"^description:", content, re.MULTILINE):
            score += 10
        else:
            issues.append("missing_description")
    else:
        issues.append("no_frontmatter")

    # Length
    if len(lines) <= 500:
        score += 10
    elif len(lines) <= 700:
        score += 5
        issues.append("long_skill_md")

    # Examples
    example_count = len(re.findall(r"(?i)(example|input.*output|```)", content))
    if example_count >= 3:
        score += 10
    elif example_count >= 1:
        score += 5

    # Headers
    header_count = len(re.findall(r"^##\s", content, re.MULTILINE))
    if header_count >= 3:
        score += 10
    elif header_count >= 1:
        score += 5

    # Progressive disclosure
    skill_dir = Path(skill_path).parent
    if (skill_dir / "references").is_dir() or len(lines) <= 200:
        score += 15
    else:
        score += 5
        issues.append("no_progressive_disclosure")

    # Imperative voice
    hedge_count = len(re.findall(
        r"you (might|could|should|may) (want to|consider|possibly)",
        content, re.IGNORECASE
    ))
    if hedge_count == 0:
        score += 5
    elif hedge_count <= 2:
        score += 3

    # Referenced files exist
    refs = set(re.findall(r"(references|scripts|templates)/[\w./-]+", content))
    missing = [r for r in refs if not (skill_dir / r).exists()]
    if not missing:
        score += 10
    else:
        score += 5
        issues.append(f"missing_refs: {missing}")

    return {"score": min(score, 100), "issues": issues, "details": {"line_count": len(lines)}}


def score_triggers(skill_path: str, eval_suite: Optional[dict]) -> dict:
    """Score trigger accuracy using eval suite."""
    if not eval_suite or "triggers" not in eval_suite:
        return {"score": -1, "issues": ["no_trigger_eval_suite"], "details": {}}

    content = Path(skill_path).read_text(encoding="utf-8")

    # Extract description from frontmatter
    desc_match = re.search(
        r"^description:\s*>?\s*\n((?:\s+.+\n)*)", content, re.MULTILINE
    )
    if not desc_match:
        desc_match = re.search(r"^description:\s*(.+)$", content, re.MULTILINE)

    description = desc_match.group(1).strip() if desc_match else ""
    desc_lower = description.lower()

    correct = 0
    total = 0

    for trigger in eval_suite["triggers"]:
        prompt = trigger.get("prompt", "").lower()
        expected = trigger.get("should_trigger", True)
        total += 1

        # Simple heuristic: check if key terms from the prompt appear in description
        prompt_words = set(re.findall(r"\b\w{4,}\b", prompt))
        desc_words = set(re.findall(r"\b\w{4,}\b", desc_lower))
        overlap = len(prompt_words & desc_words)
        would_trigger = overlap >= 2

        if would_trigger == expected:
            correct += 1

    score = int((correct / total) * 100) if total > 0 else 0
    return {"score": score, "issues": [], "details": {"correct": correct, "total": total}}


def score_efficiency(skill_path: str) -> dict:
    """Score token efficiency — instruction density.
    
    Rewards concise instructions that explain WHY, not just WHAT.
    Penalizes hedging and repetition, not thoughtful reasoning.
    """
    content = Path(skill_path).read_text(encoding="utf-8")

    # Strip frontmatter
    if content.startswith("---"):
        end = content.find("---", 3)
        if end > 0:
            content = content[end + 3:]

    words = len(content.split())
    headers = len(re.findall(r"^##\s", content, re.MULTILINE))
    code_blocks = len(re.findall(r"```", content))
    examples = len(re.findall(r"(?i)example", content))
    # Count imperative verbs as capabilities too
    imperatives = len(re.findall(
        r"^(?:Read|Run|Check|Create|Add|Remove|Move|Use|Set|If|When)\b",
        content, re.MULTILINE
    ))

    capabilities = max(headers + (code_blocks // 2) + examples + (imperatives // 3), 1)
    words_per_cap = words / capabilities

    # Scoring: lower words_per_capability = better
    if words_per_cap <= 30:
        score = 95
    elif words_per_cap <= 50:
        score = 85
    elif words_per_cap <= 80:
        score = 75
    elif words_per_cap <= 120:
        score = 60
    else:
        score = 40

    # Penalty for hedging (vague language wastes tokens)
    hedge_count = len(re.findall(
        r"you (might|could|should|may) (want to|consider|possibly)",
        content, re.IGNORECASE
    ))
    score = max(0, score - (hedge_count * 3))

    # Bonus for using examples instead of prose (+5)
    if examples >= 3:
        score = min(100, score + 5)

    # Bonus for WHY-based reasoning (+5) — explains rationale, not just rules
    why_indicators = len(re.findall(
        r"\b(because|since|this enables|this prevents|this means|the reason)\b",
        content, re.IGNORECASE
    ))
    if why_indicators >= 3:
        score = min(100, score + 5)

    # Bonus for explicit boundaries (+3) — scope clarity saves tokens downstream
    if re.search(r"(?i)(do not|don't) use (for|when|if)", content):
        score = min(100, score + 3)

    return {
        "score": score,
        "issues": [],
        "details": {
            "total_words": words,
            "capabilities": capabilities,
            "words_per_capability": round(words_per_cap, 1),
            "hedge_count": hedge_count
        }
    }


def compute_composite(scores: dict) -> float:
    """Compute weighted composite score."""
    weights = {
        "structure": 0.15,
        "triggers": 0.25,
        "quality": 0.25,
        "edges": 0.15,
        "efficiency": 0.10,
        "composability": 0.10,
    }

    total = 0.0
    weight_sum = 0.0

    for dim, weight in weights.items():
        s = scores.get(dim, {}).get("score", -1)
        if s >= 0:  # Only count dimensions we could measure
            total += s * weight
            weight_sum += weight

    return round(total / weight_sum * 1.0, 1) if weight_sum > 0 else 0.0


def main():
    parser = argparse.ArgumentParser(description="SkillForge Quality Scorer")
    parser.add_argument("skill_path", help="Path to SKILL.md")
    parser.add_argument("--eval-suite", help="Path to eval suite JSON", default=None)
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    eval_suite = None
    if args.eval_suite and Path(args.eval_suite).exists():
        eval_suite = json.loads(Path(args.eval_suite).read_text())

    scores = {
        "structure": score_structure(args.skill_path),
        "triggers": score_triggers(args.skill_path, eval_suite),
        "efficiency": score_efficiency(args.skill_path),
        # These require runtime eval (placeholder scores)
        "quality": {"score": -1, "issues": ["requires_runtime_eval"], "details": {}},
        "edges": {"score": -1, "issues": ["requires_runtime_eval"], "details": {}},
        "composability": {"score": -1, "issues": ["requires_runtime_eval"], "details": {}},
    }

    composite = compute_composite(scores)

    result = {
        "skill_path": args.skill_path,
        "composite_score": composite,
        "dimensions": {k: v["score"] for k, v in scores.items()},
        "issues": {k: v["issues"] for k, v in scores.items() if v["issues"]},
        "details": {k: v["details"] for k, v in scores.items() if v["details"]},
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n{'='*50}")
        print(f"  SkillForge Quality Score: {composite}/100")
        print(f"{'='*50}")
        for dim, data in scores.items():
            s = data["score"]
            indicator = "✓" if s >= 70 else "△" if s >= 50 else "✗" if s >= 0 else "—"
            score_str = f"{s}" if s >= 0 else "n/a"
            print(f"  {indicator} {dim:15s} {score_str:>5s}")
        print(f"{'='*50}")
        all_issues = [i for v in scores.values() for i in v["issues"]]
        if all_issues:
            print(f"\n  Issues found:")
            for issue in all_issues:
                print(f"    • {issue}")
        print()


if __name__ == "__main__":
    main()
