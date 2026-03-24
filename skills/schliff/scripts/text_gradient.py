#!/usr/bin/env python3
"""Schliff Text Gradients — Directed Improvement via Scorer Inversion

Inverts scorer diagnostics into a prioritized fix list with estimated
composite impact. Each gradient maps: specific issue → concrete edit
instruction → predicted score delta.

Usage:
    python3 text-gradient.py SKILL.md [--eval-suite eval.json] [--json] [--top N] [--clarity]

Output: Ranked list of improvements sorted by predicted_delta / effort.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

# Import scorer functions directly — no reimplementation
SCRIPT_DIR = Path(__file__).parent

import score_skill as scorer
from shared import read_skill_safe, extract_description, strip_frontmatter
from nlp import tokenize_meaningful


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
            content = read_skill_safe(skill_path)
            description = extract_description(content)
            desc_terms = set(tokenize_meaningful(description.lower(), expand_reverse=True))
        except (FileNotFoundError, ValueError):
            desc_terms = set()

        missing_terms = set()
        for fn in false_negs:
            prompt = fn.get("prompt", "")
            prompt_terms = set(tokenize_meaningful(prompt))
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

    # Dimension weights from scorer (match composite formula)
    DIM_WEIGHTS = {
        "structure": 0.15, "triggers": 0.20, "quality": 0.20,
        "edges": 0.15, "efficiency": 0.10, "composability": 0.10, "clarity": 0.05,
    }
    CONFIDENCE_MULT = {"high": 1.0, "medium": 0.6, "low": 0.3}

    # Normalize delta to float and compute composite-weighted priority
    for g in gradients:
        raw_delta = g["delta"]
        parsed = _parse_delta(raw_delta)
        # Keep original string as display hint, normalize delta to float
        if isinstance(raw_delta, str):
            g["delta_display"] = raw_delta
        g["delta"] = parsed
        dim_weight = DIM_WEIGHTS.get(g["dimension"], 0.10)
        conf_mult = CONFIDENCE_MULT.get(g.get("confidence", "medium"), 0.6)
        effort = g.get("effort", EFFORT_MODERATE)
        g["priority"] = round((parsed * dim_weight * conf_mult) / effort, 4)

    # Sort by priority descending, with stable secondary sort by dimension+issue
    gradients.sort(key=lambda g: (-g["priority"], g["dimension"], g["issue"]))

    if top_n:
        gradients = gradients[:top_n]

    return gradients


def format_gradients(gradients: list[dict]) -> str:
    """Format gradients as human-readable text."""
    if not gradients:
        return "No improvement gradients found — skill scores well across all dimensions."

    lines = []
    lines.append("=" * 70)
    lines.append("  Schliff Text Gradients — Prioritized Fix List")
    lines.append("=" * 70)
    lines.append("")

    for i, g in enumerate(gradients, 1):
        delta_str = g.get("delta_display", f"+{g['delta']:.1f}")
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


def generate_patches(skill_path: str, gradients: list[dict]) -> list[dict]:
    """Generate concrete patches for deterministic gradients.

    Only high-confidence, simple-effort gradients get patches.
    Returns a list of patch dicts with op, line, and content fields.
    """
    try:
        content = read_skill_safe(skill_path)
    except (FileNotFoundError, ValueError):
        return []

    lines = content.split("\n")
    patches = []

    # Extract skill name from frontmatter if present
    name_match = re.search(r"^name:\s*(.+?)$", content, re.MULTILINE)
    skill_name = name_match.group(1).strip() if name_match else Path(skill_path).parent.name

    # Extract body text (after frontmatter) for context-aware patch generation
    body_text = strip_frontmatter(content)

    # Extract meaningful terms from body for auto-generated descriptions
    body_terms = tokenize_meaningful(body_text.lower())[:5] if body_text else []

    # Extract first header text
    first_header_match = re.search(r"^##?\s+(.+)$", body_text, re.MULTILINE)
    first_header_text = first_header_match.group(1).strip() if first_header_match else ""

    # Try to extract first sentence from ## Overview or first ## section
    first_section_sentence = ""
    overview_match = re.search(
        r"^##\s+(?:Overview|Introduction)\s*\n+((?:[^\n#].*\n?)+)", body_text, re.MULTILINE
    )
    if not overview_match:
        overview_match = re.search(
            r"^##\s+\S.*\n+((?:[^\n#].*\n?)+)", body_text, re.MULTILINE
        )
    if overview_match:
        section_text = overview_match.group(1).strip()
        sentence_match = re.match(r"([^.!?]+[.!?])", section_text)
        if sentence_match:
            first_section_sentence = sentence_match.group(1).strip()

    def _build_description() -> str:
        """Build a meaningful description from skill body context."""
        if first_section_sentence:
            return first_section_sentence
        if len(body_terms) >= 3:
            return f"Skill for {body_terms[0]}, {body_terms[1]}, and {body_terms[2]}" + (
                f" — {first_header_text}" if first_header_text else ""
            )
        if first_header_text:
            return first_header_text
        return f"TODO: describe what {skill_name} does and when to use it"

    # Extract existing description and "when" clauses for scope patches
    existing_desc = extract_description(content)
    when_clauses = re.findall(r"(?i)(?:when|if)\s+(?:you|the|a)\s+(.+?)(?:\.|$)", body_text)
    when_clauses = [c.strip() for c in when_clauses[:3] if len(c.strip()) > 10]

    for g in gradients:
        if g.get("confidence") != "high" or g.get("effort", 2) > EFFORT_SIMPLE:
            continue

        patch = None

        if g["issue"] == "no_frontmatter":
            desc = _build_description()
            patch = {
                "op": "insert_before",
                "line": 1,
                "content": f"---\nname: {skill_name}\ndescription: >-\n  {desc}\n---\n",
            }
        elif g["issue"] == "missing_name" and lines and lines[0].strip() == "---":
            # Find end of frontmatter to insert name
            for i, line in enumerate(lines[1:], 1):
                if line.strip() == "---":
                    patch = {
                        "op": "insert_before",
                        "line": i + 1,
                        "content": f"name: {skill_name}\n",
                    }
                    break
        elif g["issue"] == "missing_description" and lines and lines[0].strip() == "---":
            desc = _build_description()
            for i, line in enumerate(lines[1:], 1):
                if line.strip() == "---":
                    patch = {
                        "op": "insert_before",
                        "line": i + 1,
                        "content": f"description: >-\n  {desc}\n",
                    }
                    break
        elif g["issue"].startswith("has_todo"):
            # Find and list TODO/FIXME lines for removal
            todo_lines = []
            for i, line in enumerate(lines):
                if re.search(r"(?i)(TODO|FIXME|HACK|XXX|placeholder)", line):
                    todo_lines.append(i + 1)
            if todo_lines:
                patch = {
                    "op": "remove_lines",
                    "lines": todo_lines,
                    "content": "",
                }
        elif g["issue"] == "no_scope_boundaries":
            # Build scope from description and existing "when" clauses
            if when_clauses:
                positive_items = "\n".join(f"- {c}" for c in when_clauses)
            elif existing_desc:
                desc_terms = tokenize_meaningful(existing_desc.lower())[:4]
                positive_items = "\n".join(f"- Working with {t}" for t in desc_terms) if desc_terms else f"- TODO: describe when to use {skill_name} vs alternatives"
            else:
                positive_items = f"- TODO: describe when to use {skill_name} vs alternatives"
            patch = {
                "op": "append",
                "line": len(lines),
                "content": f"\n## When to Use\n\nUse this skill when:\n{positive_items}\n\nDo NOT use for:\n- TODO: describe when to use {skill_name} vs alternatives\n",
            }
        elif g["issue"] == "no_handoff_points":
            # Try to extract related skill references from body
            if when_clauses:
                handoff_items = "\n".join(f"- If {c}, consider a dedicated skill" for c in when_clauses[:2])
            else:
                handoff_items = f"- TODO: describe when to use {skill_name} vs alternatives"
            patch = {
                "op": "append",
                "line": len(lines),
                "content": f"\n## Related Skills\n\nThen use:\n- TODO: describe when to use {skill_name} vs alternatives\n\nIf instead:\n{handoff_items}\n",
            }

        if patch:
            patch["gradient_id"] = f"{g['dimension']}:{g['issue']}"
            patch["dimension"] = g["dimension"]
            patch["issue"] = g["issue"]
            patch["delta"] = g["delta"]
            patches.append(patch)

    # Generate regex-based removal patches for efficiency issues
    for g in gradients:
        if g["dimension"] != "efficiency":
            continue

        if g["issue"].startswith("excessive_hedging"):
            patches.append({
                "op": "remove_regex",
                "pattern": r"you (might|could|should|may) (want to|consider|possibly) ",
                "replacement": "",
                "gradient_id": f"efficiency:{g['issue']}",
                "dimension": "efficiency",
                "issue": g["issue"],
                "delta": 1.5,
                "confidence": "high",
            })
        elif g["issue"].startswith("filler_phrases"):
            patches.append({
                "op": "remove_regex",
                "pattern": r"(?i)(it is important to note that |as mentioned (above|earlier|before)[,.]?\s*|in other words[,.]?\s*|keep in mind that |note that |please note[,.]?\s*|remember that |be aware that )",
                "replacement": "",
                "gradient_id": f"efficiency:{g['issue']}",
                "dimension": "efficiency",
                "issue": g["issue"],
                "delta": 1.0,
                "confidence": "high",
            })

    return patches


def apply_patches(skill_path: str, patches: list[dict], dry_run: bool = False) -> dict:
    """Apply deterministic patches to a skill file.

    Applies patches in reverse line order to keep line numbers stable.
    Validates YAML frontmatter after all patches are applied.

    Returns:
        ApplyResult dict with: applied, skipped, errors, new_content
    """
    try:
        content = read_skill_safe(skill_path)
    except (FileNotFoundError, ValueError) as e:
        return {"applied": 0, "skipped": 0, "errors": [str(e)], "new_content": None}

    lines = content.split("\n")
    applied = 0
    skipped = 0
    errors = []

    # Sort patches by line number descending (reverse order for stable application)
    line_patches = []
    other_patches = []
    for p in patches:
        if "line" in p:
            line_patches.append(p)
        elif "lines" in p:
            line_patches.append(p)
        else:
            other_patches.append(p)

    line_patches.sort(key=lambda p: p.get("line", p.get("lines", [0])[0] if p.get("lines") else 0), reverse=True)

    for patch in line_patches + other_patches:
        op = patch.get("op", "")
        try:
            if op == "insert_before":
                line_idx = patch["line"] - 1
                if line_idx < 0 or line_idx > len(lines):
                    errors.append(f"insert_before: line {patch['line']} out of range")
                    skipped += 1
                    continue
                new_lines = patch["content"].rstrip("\n").split("\n")
                lines[line_idx:line_idx] = new_lines
                applied += 1
            elif op == "append":
                new_lines = patch["content"].rstrip("\n").split("\n")
                lines.extend(new_lines)
                applied += 1
            elif op == "remove_lines":
                # Remove lines in reverse order to keep indices stable
                for ln in sorted(patch["lines"], reverse=True):
                    idx = ln - 1
                    if 0 <= idx < len(lines):
                        lines.pop(idx)
                applied += 1
            elif op == "remove_regex":
                pattern = patch.get("pattern", "")
                replacement = patch.get("replacement")
                if pattern:
                    try:
                        compiled = re.compile(pattern, re.IGNORECASE)
                    except re.error:
                        skipped += 1
                        continue
                    # Skip lines inside code blocks to avoid mangling examples
                    in_code_block = False
                    new_lines = []
                    for l in lines:
                        if l.strip().startswith("```"):
                            in_code_block = not in_code_block
                            new_lines.append(l)
                        elif in_code_block:
                            new_lines.append(l)  # preserve code block content
                        elif replacement is not None:
                            new_lines.append(compiled.sub(replacement, l))
                        elif not compiled.search(l):
                            new_lines.append(l)
                        # else: line removed (not in code block)
                    lines = new_lines
                    applied += 1
                else:
                    skipped += 1
            elif op == "replace_line":
                line_idx = patch["line"] - 1
                if 0 <= line_idx < len(lines):
                    lines[line_idx] = patch["content"]
                    applied += 1
                else:
                    errors.append(f"replace_line: line {patch['line']} out of range")
                    skipped += 1
            elif op == "append_section":
                new_lines = patch["content"].rstrip("\n").split("\n")
                lines.extend([""] + new_lines)
                applied += 1
            else:
                skipped += 1
        except (KeyError, IndexError) as e:
            errors.append(f"{op}: {e}")
            skipped += 1

    new_content = "\n".join(lines)

    # Validate YAML frontmatter integrity
    if new_content.startswith("---"):
        end_idx = new_content.find("---", 3)
        if end_idx < 0:
            errors.append("YAML frontmatter broken after patching (no closing ---)")
        else:
            fm = new_content[3:end_idx].strip()
            if not re.search(r"^name:\s*\S", fm, re.MULTILINE):
                errors.append("YAML frontmatter missing 'name' field after patching")

    if not dry_run and applied > 0 and not errors:
        resolved = Path(skill_path).resolve()
        if not resolved.is_file():
            return {"applied": 0, "errors": ["skill path is not a file"]}
        tmp_path = Path(skill_path).with_suffix(".skill.tmp")
        tmp_path.write_text(new_content, encoding="utf-8")
        tmp_path.replace(Path(skill_path))
        # Invalidate scorer cache for this file
        scorer.invalidate_cache(skill_path)

    return {
        "applied": applied,
        "skipped": skipped,
        "errors": errors,
        "new_content": new_content if dry_run else None,
    }


def main():
    parser = argparse.ArgumentParser(description="Schliff Text Gradients")
    parser.add_argument("skill_path", help="Path to SKILL.md")
    parser.add_argument("--eval-suite", help="Path to eval suite JSON", default=None)
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--top", type=int, default=None, help="Show only top N gradients")
    parser.add_argument("--clarity", action="store_true", help="Include clarity dimension")
    parser.add_argument("--patch", action="store_true", help="Generate concrete patches for deterministic fixes")
    parser.add_argument("--apply", action="store_true", help="Apply deterministic patches directly to file")
    parser.add_argument("--dry-run", action="store_true", help="Show what --apply would do without writing")
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

    # Validate eval-suite structure before processing
    if eval_suite is not None:
        if not isinstance(eval_suite, dict):
            print(
                f"Error: eval-suite must be a JSON object, got {type(eval_suite).__name__}. Ignoring.",
                file=sys.stderr,
            )
            eval_suite = None
        elif "skill_name" not in eval_suite and "test_cases" not in eval_suite and "triggers" not in eval_suite:
            print(
                "Error: eval-suite is missing required keys ('skill_name', and at least one of 'test_cases' or 'triggers'). Ignoring.",
                file=sys.stderr,
            )
            eval_suite = None

    gradients = compute_gradients(
        args.skill_path,
        eval_suite=eval_suite,
        include_clarity=args.clarity,
        top_n=args.top,
    )

    if args.apply or (args.patch and args.dry_run):
        patches = generate_patches(args.skill_path, gradients)
        if not patches:
            if args.json:
                print(json.dumps({"applied": 0, "skipped": 0, "errors": [], "message": "no patches available"}, indent=2))
            else:
                print("No deterministic patches available — all gradients require manual intervention.")
        else:
            result = apply_patches(args.skill_path, patches, dry_run=args.dry_run or not args.apply)
            if args.json:
                # Don't include full new_content in JSON output
                output = {k: v for k, v in result.items() if k != "new_content"}
                output["patches_attempted"] = len(patches)
                print(json.dumps(output, indent=2))
            else:
                mode = "DRY RUN" if args.dry_run else "APPLIED"
                print(f"[{mode}] {result['applied']} patches applied, {result['skipped']} skipped")
                if result["errors"]:
                    for err in result["errors"]:
                        print(f"  ERROR: {err}")
                for p in patches:
                    status = "✓" if result["applied"] > 0 else "⊘"
                    print(f"  {status} [{p['dimension']}] {p['issue']} → {p['op']}")
    elif args.patch:
        patches = generate_patches(args.skill_path, gradients)
        if args.json:
            print(json.dumps({"patches": patches, "count": len(patches)}, indent=2))
        else:
            if not patches:
                print("No deterministic patches available — all gradients require manual intervention.")
            else:
                print(f"Generated {len(patches)} concrete patches:")
                for p in patches:
                    print(f"  [{p['dimension']}] {p['issue']} → {p['op']} at line {p.get('line', '?')}")
                    if p.get("content"):
                        for cl in p["content"].split("\n")[:3]:
                            print(f"    | {cl}")
                        if len(p["content"].split("\n")) > 3:
                            print(f"    | ... ({len(p['content'].split(chr(10)))} lines)")
    elif args.json:
        print(json.dumps({"gradients": gradients, "count": len(gradients)}, indent=2))
    else:
        print(format_gradients(gradients))


if __name__ == "__main__":
    main()
