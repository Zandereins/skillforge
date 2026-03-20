#!/usr/bin/env python3
"""SkillForge Text Gradients — Directed Improvement via Scorer Inversion

Inverts scorer diagnostics into a prioritized fix list with estimated
composite impact. Each gradient maps: specific issue → concrete edit
instruction → predicted score delta.

Usage:
    python3 text-gradient.py SKILL.md [--eval-suite eval.json] [--json] [--top N] [--clarity]

Output: Ranked list of improvements sorted by predicted_delta / effort.
"""

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

# Import scorer functions directly — no reimplementation
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

# importlib handles the hyphenated module name
import importlib
scorer = importlib.import_module("score-skill")


# --- Effort classification ---
EFFORT_SIMPLE = 1    # Add/remove a line or keyword
EFFORT_MODERATE = 2  # Add a section, rewrite a paragraph
EFFORT_COMPLEX = 3   # Refactor structure, extract files
EFFORT_MAJOR = 4     # Multi-file restructuring


def _compute_structure_gradients(skill_path: str) -> list[dict]:
    """Invert structure scorer issues into fix instructions."""
    result = scorer.score_structure(skill_path)
    gradients = []

    for issue in result.get("issues", []):
        if issue == "no_frontmatter":
            gradients.append({
                "dimension": "structure",
                "issue": "no_frontmatter",
                "target": "line:1",
                "op": "insert",
                "instruction": "Add YAML frontmatter: ---\\nname: <skill-name>\\ndescription: <what it does>\\n---",
                "delta": 6.0,
                "confidence": "high",
                "effort": EFFORT_SIMPLE,
            })
        elif issue == "missing_name":
            gradients.append({
                "dimension": "structure",
                "issue": "missing_name",
                "target": "frontmatter",
                "op": "add",
                "instruction": "Add 'name: <skill-name>' to frontmatter",
                "delta": 1.5,
                "confidence": "high",
                "effort": EFFORT_SIMPLE,
            })
        elif issue == "missing_description":
            gradients.append({
                "dimension": "structure",
                "issue": "missing_description",
                "target": "frontmatter",
                "op": "add",
                "instruction": "Add 'description: <what this skill does and when to use it>' to frontmatter",
                "delta": 1.5,
                "confidence": "high",
                "effort": EFFORT_SIMPLE,
            })
        elif issue == "no_real_examples":
            gradients.append({
                "dimension": "structure",
                "issue": "no_real_examples",
                "target": "body",
                "op": "add",
                "instruction": "Add 2+ concrete examples with input/output pairs or 'Example 1:', 'Example 2:' format",
                "delta": 1.5,
                "confidence": "high",
                "effort": EFFORT_MODERATE,
            })
        elif issue == "no_progressive_disclosure":
            gradients.append({
                "dimension": "structure",
                "issue": "no_progressive_disclosure",
                "target": "directory",
                "op": "create",
                "instruction": "Create a references/ directory and extract detailed content from SKILL.md into reference files",
                "delta": 1.5,
                "confidence": "high",
                "effort": EFFORT_COMPLEX,
            })
        elif issue == "long_skill_md":
            gradients.append({
                "dimension": "structure",
                "issue": "long_skill_md",
                "target": "body",
                "op": "reduce",
                "instruction": "Reduce SKILL.md to under 500 lines by extracting verbose sections to references/",
                "delta": 0.75,
                "confidence": "high",
                "effort": EFFORT_COMPLEX,
            })
        elif issue.startswith("has_todo"):
            count = issue.split(":")[-1] if ":" in issue else "N"
            gradients.append({
                "dimension": "structure",
                "issue": issue,
                "target": "body",
                "op": "remove",
                "instruction": f"Remove {count} TODO/FIXME/HACK/placeholder markers — complete or delete them",
                "delta": 1.5,
                "confidence": "high",
                "effort": EFFORT_SIMPLE,
            })
        elif issue.startswith("has_empty_sections"):
            gradients.append({
                "dimension": "structure",
                "issue": issue,
                "target": "body",
                "op": "fill_or_remove",
                "instruction": "Fill empty sections with content or remove them entirely",
                "delta": 0.5,
                "confidence": "high",
                "effort": EFFORT_MODERATE,
            })
        elif issue.startswith("missing_refs"):
            gradients.append({
                "dimension": "structure",
                "issue": issue,
                "target": "references",
                "op": "create",
                "instruction": f"Create missing referenced files: {issue.split(': ', 1)[-1] if ': ' in issue else 'check references'}",
                "delta": 0.75,
                "confidence": "high",
                "effort": EFFORT_MODERATE,
            })

    return gradients


def _compute_trigger_gradients(skill_path: str, eval_suite: Optional[dict]) -> list[dict]:
    """Invert trigger scorer issues into fix instructions."""
    result = scorer.score_triggers(skill_path, eval_suite)
    gradients = []

    if result["score"] < 0:
        gradients.append({
            "dimension": "triggers",
            "issue": "no_trigger_eval_suite",
            "target": "eval-suite.json",
            "op": "create",
            "instruction": "Create eval-suite.json with trigger test cases (should_trigger: true/false prompts)",
            "delta": "~25.0",
            "confidence": "low",
            "effort": EFFORT_MODERATE,
        })
        return gradients

    details = result.get("details", {})
    per_trigger = details.get("per_trigger", [])

    # Analyze false negatives — skill should trigger but doesn't
    false_negs = [t for t in per_trigger if t.get("expected") and not t.get("predicted")]
    if false_negs:
        # Extract keywords from false negative prompts that aren't in the description
        try:
            content = scorer._read_skill_safe(skill_path)
            description = scorer._extract_description(content)
            desc_terms = set(scorer._tokenize_meaningful(description.lower(), expand_reverse=True))
        except (FileNotFoundError, ValueError):
            desc_terms = set()

        missing_terms = set()
        for fn in false_negs:
            prompt = fn.get("prompt", "")
            prompt_terms = set(scorer._tokenize_meaningful(prompt))
            missing = prompt_terms - desc_terms
            missing_terms.update(missing)

        if missing_terms:
            top_terms = sorted(missing_terms)[:8]
            gradients.append({
                "dimension": "triggers",
                "issue": f"false_negatives:{len(false_negs)}",
                "target": "description",
                "op": "add_keywords",
                "instruction": f"Add these keywords to the description to match missed prompts: {', '.join(top_terms)}",
                "delta": "~2.0-5.0",
                "confidence": "medium",
                "effort": EFFORT_SIMPLE,
            })

    # Analyze false positives — skill triggers when it shouldn't
    false_pos = [t for t in per_trigger if not t.get("expected") and t.get("predicted")]
    if false_pos:
        gradients.append({
            "dimension": "triggers",
            "issue": f"false_positives:{len(false_pos)}",
            "target": "description",
            "op": "add_negative_boundary",
            "instruction": "Add 'Do NOT use for...' boundaries to exclude false-positive scenarios from triggering",
            "delta": "~2.0-5.0",
            "confidence": "medium",
            "effort": EFFORT_SIMPLE,
        })

    return gradients


def _compute_efficiency_gradients(skill_path: str) -> list[dict]:
    """Invert efficiency scorer issues into fix instructions."""
    result = scorer.score_efficiency(skill_path)
    gradients = []

    for issue in result.get("issues", []):
        if issue.startswith("excessive_hedging"):
            count = issue.split(":")[-1] if ":" in issue else "N"
            gradients.append({
                "dimension": "efficiency",
                "issue": issue,
                "target": "body",
                "op": "remove",
                "instruction": f"Remove {count} hedging phrases ('you might want to consider', 'you could possibly') — use imperative voice",
                "delta": "~1.0-3.0",
                "confidence": "medium",
                "effort": EFFORT_SIMPLE,
            })
        elif issue.startswith("filler_phrases"):
            count = issue.split(":")[-1] if ":" in issue else "N"
            gradients.append({
                "dimension": "efficiency",
                "issue": issue,
                "target": "body",
                "op": "remove",
                "instruction": f"Remove {count} filler phrases ('it is important to note that', 'as mentioned above')",
                "delta": "~0.5-2.0",
                "confidence": "medium",
                "effort": EFFORT_SIMPLE,
            })
        elif issue.startswith("obvious_instructions"):
            count = issue.split(":")[-1] if ":" in issue else "N"
            gradients.append({
                "dimension": "efficiency",
                "issue": issue,
                "target": "body",
                "op": "remove",
                "instruction": f"Remove {count} obvious instructions Claude already knows ('make sure to save', 'remember to commit')",
                "delta": "~0.5-2.0",
                "confidence": "medium",
                "effort": EFFORT_SIMPLE,
            })
        elif issue.startswith("verbose"):
            gradients.append({
                "dimension": "efficiency",
                "issue": issue,
                "target": "body",
                "op": "compress",
                "instruction": "Compress verbose content — skill exceeds 2000 words. Extract detail to references/ or tighten phrasing",
                "delta": "~2.0-5.0",
                "confidence": "medium",
                "effort": EFFORT_COMPLEX,
            })

    return gradients


def _compute_composability_gradients(skill_path: str) -> list[dict]:
    """Invert composability scorer issues into fix instructions."""
    result = scorer.score_composability(skill_path)
    gradients = []

    for issue in result.get("issues", []):
        if issue == "no_scope_boundaries":
            gradients.append({
                "dimension": "composability",
                "issue": issue,
                "target": "body",
                "op": "add",
                "instruction": "Add 'Use this skill when...' (positive scope) AND 'Do NOT use for...' (negative scope) sections",
                "delta": 2.0,
                "confidence": "high",
                "effort": EFFORT_SIMPLE,
            })
        elif issue == "partial_scope_boundaries":
            gradients.append({
                "dimension": "composability",
                "issue": issue,
                "target": "body",
                "op": "add",
                "instruction": "Add both positive AND negative scope boundaries (currently only one is present)",
                "delta": 1.0,
                "confidence": "high",
                "effort": EFFORT_SIMPLE,
            })
        elif issue == "no_io_contract":
            gradients.append({
                "dimension": "composability",
                "issue": issue,
                "target": "body",
                "op": "add",
                "instruction": "Add clear input/output contract: what the skill expects (files, args) and what it produces",
                "delta": 2.0,
                "confidence": "high",
                "effort": EFFORT_MODERATE,
            })
        elif issue == "partial_io_contract":
            gradients.append({
                "dimension": "composability",
                "issue": issue,
                "target": "body",
                "op": "add",
                "instruction": "Complete the I/O contract — add the missing input spec or output spec",
                "delta": 1.0,
                "confidence": "high",
                "effort": EFFORT_SIMPLE,
            })
        elif issue == "no_handoff_points":
            gradients.append({
                "dimension": "composability",
                "issue": issue,
                "target": "body",
                "op": "add",
                "instruction": "Add handoff points: 'Then use X skill for...', 'If Y, instead use Z skill'",
                "delta": 2.0,
                "confidence": "high",
                "effort": EFFORT_SIMPLE,
            })
        elif "global_state" in issue:
            gradients.append({
                "dimension": "composability",
                "issue": issue,
                "target": "body",
                "op": "refactor",
                "instruction": "Remove or isolate global state assumptions (system-wide configs, global installs)",
                "delta": 1.0,
                "confidence": "medium",
                "effort": EFFORT_MODERATE,
            })
        elif "tool_requirements" in issue:
            gradients.append({
                "dimension": "composability",
                "issue": issue,
                "target": "body",
                "op": "add",
                "instruction": "Add fallback alternatives for hard tool requirements ('alternatively, use X')",
                "delta": 1.0,
                "confidence": "high",
                "effort": EFFORT_SIMPLE,
            })

    return gradients


def _compute_quality_gradients(skill_path: str, eval_suite: Optional[dict]) -> list[dict]:
    """Invert quality scorer issues — targets eval-suite.json, not SKILL.md."""
    result = scorer.score_quality(skill_path, eval_suite)
    gradients = []

    if result["score"] < 0:
        gradients.append({
            "dimension": "quality",
            "issue": "no_eval_suite_test_cases",
            "target": "eval-suite.json",
            "op": "create",
            "instruction": "Create eval-suite.json with 3+ test cases, each with typed assertions (contains, pattern, excludes, format)",
            "delta": "~7.5",
            "confidence": "low",
            "effort": EFFORT_MODERATE,
        })
        return gradients

    for issue in result.get("issues", []):
        if issue == "no_well_formed_test_cases":
            gradients.append({
                "dimension": "quality",
                "issue": issue,
                "target": "eval-suite.json",
                "op": "add",
                "instruction": "Add 3+ test cases with well-formed assertions (each needs 'type' and 'value' fields)",
                "delta": "~7.5",
                "confidence": "medium",
                "effort": EFFORT_MODERATE,
            })
        elif issue == "no_known_assertion_types":
            gradients.append({
                "dimension": "quality",
                "issue": issue,
                "target": "eval-suite.json",
                "op": "diversify",
                "instruction": "Use multiple assertion types: contains, pattern, excludes, format (currently missing known types)",
                "delta": "~6.0",
                "confidence": "high",
                "effort": EFFORT_MODERATE,
            })
        elif issue == "narrow_feature_coverage":
            gradients.append({
                "dimension": "quality",
                "issue": issue,
                "target": "eval-suite.json",
                "op": "add",
                "instruction": "Add test cases covering different features (analyze, improve, report) — not just one type",
                "delta": "~6.0",
                "confidence": "high",
                "effort": EFFORT_MODERATE,
            })
        elif issue.startswith("missing_assertion_descriptions"):
            gradients.append({
                "dimension": "quality",
                "issue": issue,
                "target": "eval-suite.json",
                "op": "add",
                "instruction": "Add 'description' field to all assertions in eval-suite.json",
                "delta": "~3.0-5.0",
                "confidence": "high",
                "effort": EFFORT_SIMPLE,
            })

    return gradients


def _compute_edges_gradients(skill_path: str, eval_suite: Optional[dict]) -> list[dict]:
    """Invert edges scorer issues — targets eval-suite.json."""
    result = scorer.score_edges(skill_path, eval_suite)
    gradients = []

    if result["score"] < 0:
        gradients.append({
            "dimension": "edges",
            "issue": "no_eval_suite_edge_cases",
            "target": "eval-suite.json",
            "op": "create",
            "instruction": "Add 'edge_cases' section to eval-suite.json with 5+ cases across categories (minimal, invalid, scale, malformed, missing)",
            "delta": "~7.5",
            "confidence": "low",
            "effort": EFFORT_MODERATE,
        })
        return gradients

    details = result.get("details", {})
    edge_count = details.get("edge_case_count", 0)
    known_cats = details.get("known_categories_covered", [])

    if edge_count < 5:
        needed = 5 - edge_count
        gradients.append({
            "dimension": "edges",
            "issue": f"insufficient_edge_cases:{edge_count}",
            "target": "eval-suite.json",
            "op": "add",
            "instruction": f"Add {needed} more edge cases to eval-suite.json (currently {edge_count}, need 5+)",
            "delta": "~3.0-7.0",
            "confidence": "medium",
            "effort": EFFORT_MODERATE,
        })

    all_categories = {"minimal_input", "invalid_path", "scale_extreme", "malformed_input", "missing_deps"}
    missing_cats = all_categories - set(known_cats)
    if missing_cats:
        gradients.append({
            "dimension": "edges",
            "issue": f"missing_categories:{','.join(sorted(missing_cats))}",
            "target": "eval-suite.json",
            "op": "add",
            "instruction": f"Add edge cases for missing categories: {', '.join(sorted(missing_cats))}",
            "delta": "~3.0-7.0",
            "confidence": "medium",
            "effort": EFFORT_MODERATE,
        })

    for issue in result.get("issues", []):
        if issue == "no_expected_behaviors":
            gradients.append({
                "dimension": "edges",
                "issue": issue,
                "target": "eval-suite.json",
                "op": "add",
                "instruction": "Add 'expected_behavior' field to all edge cases",
                "delta": "~5.0",
                "confidence": "high",
                "effort": EFFORT_SIMPLE,
            })
        elif issue == "no_edge_assertions":
            gradients.append({
                "dimension": "edges",
                "issue": issue,
                "target": "eval-suite.json",
                "op": "add",
                "instruction": "Add assertions to all edge cases in eval-suite.json",
                "delta": "~5.0",
                "confidence": "high",
                "effort": EFFORT_SIMPLE,
            })

    return gradients


def _compute_clarity_gradients(skill_path: str) -> list[dict]:
    """Invert clarity scorer issues into fix instructions."""
    result = scorer.score_clarity(skill_path)
    gradients = []

    details = result.get("details", {})

    if details.get("contradictions"):
        for contradiction in details["contradictions"]:
            gradients.append({
                "dimension": "clarity",
                "issue": f"contradiction:{contradiction}",
                "target": "body",
                "op": "resolve",
                "instruction": f"Resolve contradiction: 'always {contradiction}' conflicts with 'never {contradiction}' — pick one",
                "delta": "~3.0-10.0",
                "confidence": "medium",
                "effort": EFFORT_MODERATE,
            })

    if details.get("vague_references", 0) > 0:
        gradients.append({
            "dimension": "clarity",
            "issue": f"vague_references:{details['vague_references']}",
            "target": "body",
            "op": "replace",
            "instruction": f"Replace {details['vague_references']} vague references ('the file', 'the script') with specific paths or backtick-quoted names",
            "delta": "~2.0-5.0",
            "confidence": "medium",
            "effort": EFFORT_SIMPLE,
        })

    if details.get("ambiguous_pronouns", 0) > 0:
        gradients.append({
            "dimension": "clarity",
            "issue": f"ambiguous_pronouns:{details['ambiguous_pronouns']}",
            "target": "body",
            "op": "replace",
            "instruction": f"Replace {details['ambiguous_pronouns']} ambiguous pronouns (sentences starting with 'It is', 'This does') with explicit subjects",
            "delta": "~1.0-4.0",
            "confidence": "medium",
            "effort": EFFORT_SIMPLE,
        })

    if details.get("incomplete_instructions", 0) > 0:
        gradients.append({
            "dimension": "clarity",
            "issue": f"incomplete_instructions:{details['incomplete_instructions']}",
            "target": "body",
            "op": "complete",
            "instruction": f"Complete {details['incomplete_instructions']} 'Run/Execute/Install' instructions with concrete commands or paths",
            "delta": "~2.0-5.0",
            "confidence": "medium",
            "effort": EFFORT_MODERATE,
        })

    return gradients


def _parse_delta(delta: Any) -> float:
    """Parse delta value — handles both float and '~X.Y-Z.W' range strings."""
    if isinstance(delta, (int, float)):
        return float(delta)
    if isinstance(delta, str):
        # Parse range like "~2.0-5.0" → midpoint 3.5
        match = re.search(r"(\d+\.?\d*)\s*-\s*(\d+\.?\d*)", delta)
        if match:
            return (float(match.group(1)) + float(match.group(2))) / 2
        # Parse single value like "~7.5"
        match = re.search(r"(\d+\.?\d*)", delta)
        if match:
            return float(match.group(1))
    return 0.0


def compute_gradients(
    skill_path: str,
    eval_suite: Optional[dict] = None,
    include_clarity: bool = False,
    top_n: Optional[int] = None,
) -> list[dict]:
    """Compute all gradients, rank by priority (delta/effort), return top N."""
    gradients = []

    gradients.extend(_compute_structure_gradients(skill_path))
    gradients.extend(_compute_trigger_gradients(skill_path, eval_suite))
    gradients.extend(_compute_efficiency_gradients(skill_path))
    gradients.extend(_compute_composability_gradients(skill_path))
    gradients.extend(_compute_quality_gradients(skill_path, eval_suite))
    gradients.extend(_compute_edges_gradients(skill_path, eval_suite))

    if include_clarity:
        gradients.extend(_compute_clarity_gradients(skill_path))

    # Compute priority: predicted_delta / effort
    for g in gradients:
        delta = _parse_delta(g["delta"])
        effort = g.get("effort", EFFORT_MODERATE)
        g["priority"] = round(delta / effort, 2)

    # Sort by priority descending
    gradients.sort(key=lambda g: g["priority"], reverse=True)

    if top_n:
        gradients = gradients[:top_n]

    return gradients


def format_gradients(gradients: list[dict]) -> str:
    """Format gradients as human-readable text."""
    if not gradients:
        return "No improvement gradients found — skill scores well across all dimensions."

    lines = []
    lines.append("=" * 70)
    lines.append("  SkillForge Text Gradients — Prioritized Fix List")
    lines.append("=" * 70)
    lines.append("")

    for i, g in enumerate(gradients, 1):
        delta_str = g["delta"] if isinstance(g["delta"], str) else f"+{g['delta']:.1f}"
        conf = g.get("confidence", "medium")
        effort_labels = {1: "simple", 2: "moderate", 3: "complex", 4: "major"}
        effort_str = effort_labels.get(g.get("effort", 2), "moderate")

        lines.append(f"  #{i}  [{g['dimension']}] {g['issue']}")
        lines.append(f"      {g['instruction']}")
        lines.append(f"      delta: {delta_str}  |  effort: {effort_str}  |  confidence: {conf}  |  priority: {g['priority']}")
        lines.append(f"      target: {g['target']}  |  op: {g['op']}")
        lines.append("")

    lines.append("=" * 70)
    lines.append(f"  Total: {len(gradients)} improvements identified")
    lines.append("=" * 70)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="SkillForge Text Gradients")
    parser.add_argument("skill_path", help="Path to SKILL.md")
    parser.add_argument("--eval-suite", help="Path to eval suite JSON", default=None)
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--top", type=int, default=None, help="Show only top N gradients")
    parser.add_argument("--clarity", action="store_true", help="Include clarity dimension")
    args = parser.parse_args()

    eval_suite = None
    if args.eval_suite and Path(args.eval_suite).exists():
        eval_suite = json.loads(Path(args.eval_suite).read_text())
    else:
        # Auto-discover eval-suite.json
        skill_dir = Path(args.skill_path).parent
        auto_path = skill_dir / "eval-suite.json"
        if auto_path.exists():
            eval_suite = json.loads(auto_path.read_text())

    gradients = compute_gradients(
        args.skill_path,
        eval_suite=eval_suite,
        include_clarity=args.clarity,
        top_n=args.top,
    )

    if args.json:
        print(json.dumps({"gradients": gradients, "count": len(gradients)}, indent=2))
    else:
        print(format_gradients(gradients))


if __name__ == "__main__":
    main()
