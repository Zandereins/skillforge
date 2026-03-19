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
import math
import os
import re
import subprocess
import sys
from collections import Counter
from typing import Optional
from pathlib import Path


# --- Stopwords for trigger scoring (truly generic function words only) ---
# IMPORTANT: Do NOT include domain-relevant terms here. Words like "skill",
# "code", "create" are meaningful in skill-improvement contexts.
STOPWORDS = {
    "this", "that", "with", "from", "have", "will", "been", "were", "they",
    "their", "them", "what", "when", "where", "which", "about", "into",
    "your", "some", "than", "then", "also", "just", "more", "very", "here",
    "there", "each", "like", "help", "want", "need", "using", "used",
    "uses", "does", "doing", "done", "should", "could", "would", "please",
    "really", "actually", "currently", "basically", "think", "know",
    "sure", "well", "okay", "look", "show", "tell",
}


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

    # Examples — match the improved bash script logic
    real_examples = len(re.findall(
        r"(?i)(example\s*[0-9:#]|input.*output|e\.g\.|for instance|for example)",
        content
    ))
    code_block_pairs = len(re.findall(r"```", content)) // 2
    if real_examples >= 2:
        score += 10
    elif real_examples >= 1 or (real_examples + code_block_pairs // 3) >= 2:
        score += 5
    else:
        issues.append("no_real_examples")

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


def _extract_description(content: str) -> str:
    """Extract the description field from YAML frontmatter.

    Handles all common YAML formats:
      description: inline text
      description: >
        block text
      description: |
        block text
    """
    # Try block scalar first (> or |)
    match = re.search(
        r"^description:\s*[>|]-?\s*\n((?:[ \t]+.+\n)*)",
        content, re.MULTILINE
    )
    if match:
        return match.group(1).strip()

    # Try inline
    match = re.search(r'^description:\s*"?(.+?)"?\s*$', content, re.MULTILINE)
    if match:
        return match.group(1).strip()

    return ""


# --- Synonym expansion for trigger matching ---
# Maps common synonyms to canonical terms found in skill descriptions
SYNONYM_TABLE = {
    "enhance": "improve", "optimize": "improve", "refine": "improve",
    "polish": "improve", "boost": "improve", "upgrade": "improve",
    "fix up": "improve", "tune": "improve", "tweak": "improve",
    "activate": "trigger", "fire": "trigger", "match": "trigger",
    "invoke": "trigger", "detect": "trigger",
    "assess": "audit", "inspect": "audit", "review": "audit",
    "evaluate": "audit", "examine": "audit", "check": "audit",
    "test": "eval", "validate": "eval", "verify": "eval",
    "grind": "iterate", "loop": "iterate", "repeat": "iterate",
    "verbose": "efficiency", "bloated": "efficiency", "concise": "efficiency",
    "lean": "efficiency", "trim": "efficiency", "compact": "efficiency",
}


def _tokenize_meaningful(text: str) -> list[str]:
    """Extract meaningful words (4+ chars, not stopwords), with synonym expansion."""
    words = re.findall(r"\b[a-z]{4,}\b", text.lower())
    result = []
    for w in words:
        if w in STOPWORDS:
            continue
        # Expand synonyms: add both the original and canonical form
        canonical = SYNONYM_TABLE.get(w)
        result.append(w)
        if canonical and canonical not in result:
            result.append(canonical)
    return result


def _extract_key_phrases(text: str) -> list[str]:
    """Extract domain-specific bigrams and key phrases from text."""
    text_lower = text.lower()
    words = re.findall(r"\b[a-z]+\b", text_lower)
    bigrams = []
    for i in range(len(words) - 1):
        bigrams.append(f"{words[i]}_{words[i+1]}")
    return bigrams


def _has_skill_domain_signal(prompt: str) -> float:
    """Check if prompt is about skills (not generic code/config).

    Returns a multiplier: 1.5 for strong signal, 1.0 for neutral, 0.5 for anti-signal.
    """
    prompt_lower = prompt.lower()

    # Strong positive signals: explicitly about skill files or skill improvement
    strong_signals = [
        r"skill\.md", r"skill\s*forge",
        r"my\s+skill", r"this\s+skill", r"the\s+skill",
        r"skill\s+(?:trigger|description|improvement|quality|needs|work)",
        r"improve\s+(?:my|this|the)\s+skill",
        r"(?:trigger|eval)\s+(?:accuracy|suite|test)",
        r"skill\s+(?:and|but|needs|is|has)",
    ]
    for pat in strong_signals:
        if re.search(pat, prompt_lower):
            return 1.8

    # Weak positive: mentions "skill" at all
    if "skill" in prompt_lower:
        return 1.2

    # Anti-signals: clearly about code, not skills
    anti_signals = [
        r"python\s+function", r"rest\s+api", r"docker",
        r"security\s+vulnerab", r"\.py\b", r"\.ts\b", r"\.js\b",
        r"open\s+source\s+project", r"readme",
        r"prompt\s+template",
    ]
    for pat in anti_signals:
        if re.search(pat, prompt_lower):
            return 0.4

    return 1.0


def score_triggers(skill_path: str, eval_suite: Optional[dict]) -> dict:
    """Score trigger accuracy using eval suite.

    Uses TF-IDF-inspired scoring instead of naive word overlap:
    1. Extracts meaningful terms (stopwords removed)
    2. Weights rare/specific terms higher than common ones
    3. Handles negation in description ("do NOT use for X")
    4. Requires higher threshold for positive triggers
    """
    if not eval_suite or "triggers" not in eval_suite:
        return {"score": -1, "issues": ["no_trigger_eval_suite"], "details": {}}

    content = Path(skill_path).read_text(encoding="utf-8")
    description = _extract_description(content)

    if not description:
        return {"score": 0, "issues": ["empty_description"], "details": {}}

    desc_lower = description.lower()

    # Extract negative boundaries from description
    neg_patterns = re.findall(
        r"(?:do not|don't|NOT|never)\s+(?:use\s+)?(?:for|when|if|with)?\s*(.+?)(?:\.|,|$)",
        description, re.IGNORECASE
    )
    negative_terms = set()
    for pat in neg_patterns:
        negative_terms.update(_tokenize_meaningful(pat))

    # Meaningful description terms (excluding negated ones for positive matching)
    desc_terms = _tokenize_meaningful(desc_lower)
    desc_term_set = set(desc_terms)
    positive_desc_terms = desc_term_set - negative_terms

    # Build IDF-like weights: terms that appear in fewer triggers are more discriminative
    all_trigger_terms = []
    for trigger in eval_suite["triggers"]:
        prompt = trigger.get("prompt", "")
        all_trigger_terms.extend(_tokenize_meaningful(prompt))

    term_doc_freq = Counter()
    for trigger in eval_suite["triggers"]:
        prompt_terms = set(_tokenize_meaningful(trigger.get("prompt", "")))
        for t in prompt_terms:
            term_doc_freq[t] += 1

    num_triggers = len(eval_suite["triggers"])

    correct = 0
    total = 0
    details_per_trigger = []

    for trigger in eval_suite["triggers"]:
        prompt = trigger.get("prompt", "")
        expected = trigger.get("should_trigger", True)
        total += 1

        prompt_terms = set(_tokenize_meaningful(prompt))

        # Compute weighted overlap score
        overlap_score = 0.0
        matching_terms = []
        for term in prompt_terms & positive_desc_terms:
            # IDF weight: rarer terms in the eval suite matter more
            idf = math.log(num_triggers / (term_doc_freq.get(term, 1) + 1)) + 1
            overlap_score += idf
            matching_terms.append(term)

        # Check if prompt matches negative boundaries
        neg_overlap = prompt_terms & negative_terms
        if neg_overlap:
            overlap_score *= 0.3  # Heavy penalty for matching negated terms

        # Extra check: "from scratch" / "brand new" patterns indicate creation, not improvement
        creation_patterns = re.findall(
            r"(?i)(from scratch|brand new|new\b.{0,20}\bskill|create\b.{0,20}\bskill|"
            r"build\b.{0,20}\bskill|write\b.{0,20}\bskill|design\b.{0,20}\bskill)",
            prompt
        )
        if creation_patterns:
            overlap_score *= 0.3

        # Apply domain signal multiplier (skill context vs generic code)
        domain_mult = _has_skill_domain_signal(prompt)
        overlap_score *= domain_mult

        # Adaptive threshold based on prompt complexity and domain signal
        prompt_meaningful = len(prompt_terms)
        base_threshold = 3.0 if prompt_meaningful <= 4 else 4.5
        # When prompt is clearly in the skill domain, use a flat lower threshold
        # because even a single matching term is meaningful in the right context
        if domain_mult >= 1.5:
            threshold = 2.5
        else:
            threshold = base_threshold

        would_trigger = overlap_score >= threshold

        if would_trigger == expected:
            correct += 1

        details_per_trigger.append({
            "prompt": prompt[:60],
            "expected": expected,
            "predicted": would_trigger,
            "score": round(overlap_score, 2),
            "match": would_trigger == expected,
        })

    score = int((correct / total) * 100) if total > 0 else 0

    # Identify failure patterns
    issues = []
    false_positives = sum(1 for d in details_per_trigger if d["predicted"] and not d["expected"])
    false_negatives = sum(1 for d in details_per_trigger if not d["predicted"] and d["expected"])
    if false_positives > 0:
        issues.append(f"false_positives:{false_positives}")
    if false_negatives > 0:
        issues.append(f"false_negatives:{false_negatives}")

    return {
        "score": score,
        "issues": issues,
        "details": {
            "correct": correct,
            "total": total,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "per_trigger": details_per_trigger,
        }
    }


def score_efficiency(skill_path: str) -> dict:
    """Score token efficiency — information density.

    Measures how much useful, actionable content the skill delivers
    relative to its total size. Penalizes bloat, rewards conciseness.

    Key insight: A good efficiency metric should NOT reward adding more
    headers or code blocks. It should reward delivering more value in
    fewer words.
    """
    content = Path(skill_path).read_text(encoding="utf-8")
    full_content = content

    # Strip frontmatter for body analysis
    if content.startswith("---"):
        end = content.find("---", 3)
        if end > 0:
            content = content[end + 3:]

    lines = content.strip().split("\n")
    total_lines = len(lines)
    words = content.split()
    total_words = len(words)

    if total_words == 0:
        return {"score": 0, "issues": ["empty_skill_body"], "details": {}}

    # --- Signal indicators (what makes content valuable) ---

    # Actionable instructions (imperative verbs at line start)
    actionable_lines = len(re.findall(
        r"^(?:\d+\.\s*)?(?:Read|Run|Check|Create|Add|Remove|Move|Use|Set|"
        r"Install|Configure|Deploy|Test|Verify|Build|Start|Stop|Open|Save|"
        r"Copy|Delete|Write|Edit|Update|Generate|Execute|Validate|Parse|"
        r"Extract|Transform|Import|Export|Send|Fetch|Call|Return)\b",
        content, re.MULTILINE
    ))

    # Real examples (input/output pairs, not just code blocks)
    real_examples = len(re.findall(
        r"(?i)(example\s*[0-9:#]|input.*output|e\.g\.|for instance|for example)",
        content
    ))

    # WHY-based reasoning (explains rationale)
    why_count = len(re.findall(
        r"\b(because|since|this enables|this prevents|this means|the reason|"
        r"this ensures|this avoids|otherwise|so that|why[:\s])\b",
        content, re.IGNORECASE
    ))

    # Verification commands (executable checks)
    verification_cmds = len(re.findall(r"```\s*(?:bash|sh)\b", content))

    # --- Noise indicators (what wastes tokens) ---

    # Hedging language
    hedge_count = len(re.findall(
        r"you (might|could|should|may) (want to|consider|possibly)",
        content, re.IGNORECASE
    ))

    # Redundant phrases (saying the same thing multiple ways)
    filler_phrases = len(re.findall(
        r"(?i)(it is important to note that|as mentioned (above|earlier|before)|"
        r"in other words|that is to say|keep in mind that|note that|"
        r"it should be noted|please note|remember that|be aware that|"
        r"it's worth mentioning)",
        content
    ))

    # Instructions Claude already knows (generic coding advice)
    obvious_instructions = len(re.findall(
        r"(?i)(make sure to save|don't forget to|always test your|"
        r"be careful when|ensure you have|make sure you|"
        r"remember to commit|use version control)",
        content
    ))

    # Empty/near-empty lines ratio
    empty_lines = sum(1 for line in lines if not line.strip())
    empty_ratio = empty_lines / max(total_lines, 1)

    # --- Compute score ---

    # Base score: information density (signal words / total words)
    signal_count = (
        actionable_lines * 3 +  # High value: direct instructions
        real_examples * 5 +      # High value: concrete examples
        why_count * 2 +           # Medium value: reasoning
        verification_cmds * 2     # Medium value: verifiable steps
    )
    noise_count = (
        hedge_count * 3 +
        filler_phrases * 2 +
        obvious_instructions * 2
    )

    # Density = signal per 100 words, penalized by noise
    density = ((signal_count - noise_count) / max(total_words, 1)) * 100

    # Map density to score
    if density >= 8:
        score = 95
    elif density >= 5:
        score = 85
    elif density >= 3:
        score = 75
    elif density >= 1.5:
        score = 65
    elif density >= 0.5:
        score = 55
    else:
        score = 40

    # Penalty for excessive length without proportional signal
    if total_words > 2000 and density < 3:
        score = max(20, score - 15)

    # Penalty for too much whitespace (padding)
    if empty_ratio > 0.3:
        score = max(20, score - 5)

    # Bonus for explicit scope boundaries (+3)
    if re.search(r"(?i)(do not|don't) use (for|when|if)", full_content):
        score = min(100, score + 3)

    # Bonus for conciseness: under 300 lines with good signal (+5)
    if total_lines <= 300 and density >= 3:
        score = min(100, score + 5)

    issues = []
    if hedge_count > 2:
        issues.append(f"excessive_hedging:{hedge_count}")
    if filler_phrases > 2:
        issues.append(f"filler_phrases:{filler_phrases}")
    if obvious_instructions > 1:
        issues.append(f"obvious_instructions:{obvious_instructions}")
    if total_words > 2000:
        issues.append(f"verbose:{total_words}_words")

    return {
        "score": min(100, max(0, score)),
        "issues": issues,
        "details": {
            "total_words": total_words,
            "total_lines": total_lines,
            "signal_count": signal_count,
            "noise_count": noise_count,
            "density": round(density, 2),
            "actionable_lines": actionable_lines,
            "real_examples": real_examples,
            "why_count": why_count,
            "hedge_count": hedge_count,
            "filler_phrases": filler_phrases,
        }
    }


def score_composability(skill_path: str) -> dict:
    """Score composability — how well this skill plays with others.

    Static analysis checks (no runtime needed):
    - Clear scope boundaries (20 pts)
    - No global state assumptions (20 pts)
    - Input/output contract clarity (20 pts)
    - Explicit handoff points (20 pts)
    - No conflicting tool assumptions (20 pts)
    """
    try:
        content = Path(skill_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"score": 0, "issues": ["file_not_found"], "details": {}}

    score = 0
    issues = []

    # 1. Clear scope boundaries (20 pts)
    has_positive_scope = bool(re.search(
        r"(?i)(use this skill when|use when|trigger when|activate for)",
        content
    ))
    has_negative_scope = bool(re.search(
        r"(?i)(do not use|don't use|NOT for|not use for|out of scope)",
        content
    ))
    if has_positive_scope and has_negative_scope:
        score += 20
    elif has_positive_scope or has_negative_scope:
        score += 10
        issues.append("partial_scope_boundaries")
    else:
        issues.append("no_scope_boundaries")

    # 2. No global state assumptions (20 pts)
    global_state_patterns = re.findall(
        r"(?i)(must be installed globally|global config|~\/\.|modify system|"
        r"system-wide|/etc/|export\s+\w+=)",
        content
    )
    if not global_state_patterns:
        score += 20
    elif len(global_state_patterns) <= 2:
        score += 10
        issues.append(f"some_global_state_assumptions:{len(global_state_patterns)}")
    else:
        issues.append(f"heavy_global_state_assumptions:{len(global_state_patterns)}")

    # 3. Input/output contract clarity (20 pts)
    has_input_spec = bool(re.search(
        r"(?i)(input:|takes.*as input|expects|requires.*file|requires.*path|target.*skill)",
        content
    ))
    has_output_spec = bool(re.search(
        r"(?i)(output:|produces|generates|creates|saves.*to|writes.*to|returns)",
        content
    ))
    if has_input_spec and has_output_spec:
        score += 20
    elif has_input_spec or has_output_spec:
        score += 10
        issues.append("partial_io_contract")
    else:
        issues.append("no_io_contract")

    # 4. Explicit handoff points (20 pts)
    has_handoff = bool(re.search(
        r"(?i)(then use|hand off to|pass to|chain with|followed by|"
        r"complementary|works with|after.*use|before.*use|"
        r"skill-creator|next step)",
        content
    ))
    has_when_not = bool(re.search(
        r"(?i)(if.*instead use|for.*use.*instead|suggest using)",
        content
    ))
    if has_handoff and has_when_not:
        score += 20
    elif has_handoff or has_when_not:
        score += 12
    else:
        issues.append("no_handoff_points")

    # 5. No conflicting tool assumptions (20 pts)
    # Check for hard-coded tool requirements without alternatives
    hard_requirements = re.findall(
        r"(?i)(requires?\s+(?:npm|pip|brew|apt|docker|node|python)\b)",
        content
    )
    has_alternatives = bool(re.search(
        r"(?i)(alternatively|or use|if.*not available|fallback)",
        content
    ))
    if not hard_requirements or has_alternatives:
        score += 20
    elif len(hard_requirements) <= 2:
        score += 10
        issues.append("hard_tool_requirements_without_fallback")
    else:
        issues.append("many_hard_tool_requirements")

    return {
        "score": score,
        "issues": issues,
        "details": {
            "has_positive_scope": has_positive_scope,
            "has_negative_scope": has_negative_scope,
            "has_input_spec": has_input_spec,
            "has_output_spec": has_output_spec,
            "has_handoff": has_handoff,
            "global_state_patterns": len(global_state_patterns) if global_state_patterns else 0,
        }
    }


def score_quality(skill_path: str, eval_suite: Optional[dict]) -> dict:
    """Score eval suite quality — static analysis of test case coverage.

    Checks whether the eval suite has well-structured test cases that
    cover the skill's features with diverse assertion types.

    Scoring (100 pts total):
    - Has 3+ test cases with well-formed assertions: 30 pts
    - Assertions cover multiple types (contains, pattern, excludes, format): 25 pts
    - Test cases cover different skill features (analyze, improve, report): 25 pts
    - All assertions have descriptions: 20 pts
    """
    if not eval_suite or "test_cases" not in eval_suite:
        return {"score": -1, "issues": ["no_eval_suite_test_cases"], "details": {}}

    test_cases = eval_suite["test_cases"]
    if not test_cases:
        return {"score": -1, "issues": ["empty_test_cases"], "details": {}}

    score = 0
    issues = []

    # Count test cases with well-formed assertions (type + value present)
    well_formed = []
    for tc in test_cases:
        assertions = tc.get("assertions", [])
        wf = [a for a in assertions if a.get("type") and a.get("value")]
        if wf:
            well_formed.append(tc)

    # 1. Has 3+ well-formed test cases (30 pts)
    if len(well_formed) >= 3:
        score += 30
    elif len(well_formed) >= 1:
        score += int(30 * len(well_formed) / 3)
    else:
        issues.append("no_well_formed_test_cases")

    # 2. Assertions cover multiple types (25 pts)
    assertion_types = set()
    for tc in test_cases:
        for a in tc.get("assertions", []):
            if a.get("type"):
                assertion_types.add(a["type"])

    known_types = {"contains", "pattern", "excludes", "format"}
    covered_types = assertion_types & known_types
    if len(covered_types) >= 3:
        score += 25
    elif len(covered_types) >= 2:
        score += 15
    elif len(covered_types) >= 1:
        score += 8
    else:
        issues.append("no_known_assertion_types")

    # 3. Test cases cover different skill features (25 pts)
    feature_keywords = {"analyze", "improve", "report"}
    covered_features = set()
    for tc in test_cases:
        prompt = tc.get("prompt", "").lower()
        tc_id = tc.get("id", "").lower()
        combined = prompt + " " + tc_id
        for feat in feature_keywords:
            if feat in combined:
                covered_features.add(feat)

    if len(covered_features) >= 3:
        score += 25
    elif len(covered_features) >= 2:
        score += 15
    elif len(covered_features) >= 1:
        score += 8
    else:
        issues.append("narrow_feature_coverage")

    # 4. All assertions have descriptions (20 pts)
    total_assertions = 0
    described_assertions = 0
    for tc in test_cases:
        for a in tc.get("assertions", []):
            total_assertions += 1
            if a.get("description"):
                described_assertions += 1

    if total_assertions > 0 and described_assertions == total_assertions:
        score += 20
    elif total_assertions > 0:
        score += int(20 * described_assertions / total_assertions)
        issues.append(f"missing_assertion_descriptions:{total_assertions - described_assertions}")
    else:
        issues.append("no_assertions")

    return {
        "score": min(score, 100),
        "issues": issues,
        "details": {
            "test_case_count": len(test_cases),
            "well_formed_count": len(well_formed),
            "assertion_types": sorted(assertion_types),
            "covered_features": sorted(covered_features),
            "total_assertions": total_assertions,
            "described_assertions": described_assertions,
        }
    }


def score_edges(skill_path: str, eval_suite: Optional[dict]) -> dict:
    """Score edge case coverage — static analysis of edge case definitions.

    Checks whether the eval suite has comprehensive edge case coverage
    across multiple failure categories.

    Scoring (100 pts total):
    - Has 5+ edge cases: 30 pts
    - Covers multiple categories: 30 pts
    - All edge cases have expected_behavior: 20 pts
    - All edge cases have assertions: 20 pts
    """
    if not eval_suite or "edge_cases" not in eval_suite:
        return {"score": -1, "issues": ["no_eval_suite_edge_cases"], "details": {}}

    edge_cases = eval_suite["edge_cases"]
    if not edge_cases:
        return {"score": -1, "issues": ["empty_edge_cases"], "details": {}}

    score = 0
    issues = []

    # 1. Has 5+ edge cases (30 pts)
    if len(edge_cases) >= 5:
        score += 30
    elif len(edge_cases) >= 3:
        score += 20
    elif len(edge_cases) >= 1:
        score += 10
    else:
        issues.append("no_edge_cases")

    # 2. Covers multiple categories (30 pts)
    # Use prefix matching to handle category name variations
    # e.g., "malformed_skill" matches "malformed", "unicode_path" matches "unicode"
    category_prefixes = {
        "minimal": "minimal_input",
        "invalid": "invalid_path",
        "scale": "scale_extreme",
        "malformed": "malformed_input",
        "missing": "missing_deps",
        "unicode": "unicode",
        "empty": "minimal_input",
        "huge": "scale_extreme",
        "dangerous": "missing_deps",
    }
    found_categories = set()
    for ec in edge_cases:
        cat = ec.get("category", "")
        if cat:
            found_categories.add(cat)

    # Map found categories to known categories via prefix matching
    covered_known = set()
    for found_cat in found_categories:
        for prefix, known_cat in category_prefixes.items():
            if found_cat.startswith(prefix):
                covered_known.add(known_cat)
                break
    if len(covered_known) >= 4:
        score += 30
    elif len(covered_known) >= 3:
        score += 22
    elif len(covered_known) >= 2:
        score += 15
    elif len(covered_known) >= 1:
        score += 8
    else:
        issues.append("no_known_categories")

    # 3. All edge cases have expected_behavior (20 pts)
    with_behavior = sum(1 for ec in edge_cases if ec.get("expected_behavior"))
    if with_behavior == len(edge_cases):
        score += 20
    elif with_behavior > 0:
        score += int(20 * with_behavior / len(edge_cases))
        issues.append(f"missing_expected_behavior:{len(edge_cases) - with_behavior}")
    else:
        issues.append("no_expected_behaviors")

    # 4. All edge cases have assertions (20 pts)
    with_assertions = sum(
        1 for ec in edge_cases
        if ec.get("assertions") and len(ec["assertions"]) > 0
    )
    if with_assertions == len(edge_cases):
        score += 20
    elif with_assertions > 0:
        score += int(20 * with_assertions / len(edge_cases))
        issues.append(f"missing_edge_assertions:{len(edge_cases) - with_assertions}")
    else:
        issues.append("no_edge_assertions")

    return {
        "score": min(score, 100),
        "issues": issues,
        "details": {
            "edge_case_count": len(edge_cases),
            "categories": sorted(found_categories),
            "known_categories_covered": sorted(covered_known),
            "with_expected_behavior": with_behavior,
            "with_assertions": with_assertions,
        }
    }


def compute_composite(scores: dict) -> dict:
    """Compute weighted composite score with confidence indicator.

    Returns both the score and metadata about how many dimensions
    were actually measured, so users know how trustworthy the number is.
    """
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
    measured = []
    unmeasured = []

    for dim, weight in weights.items():
        s = scores.get(dim, {}).get("score", -1)
        if s >= 0:
            total += s * weight
            weight_sum += weight
            measured.append(dim)
        else:
            unmeasured.append(dim)

    composite = round(total / weight_sum, 1) if weight_sum > 0 else 0.0

    # Confidence: what fraction of total weight is actually measured
    confidence = round(weight_sum, 2)
    measured_count = len(measured)
    total_count = len(weights)

    warnings = []
    if measured_count <= 2:
        warnings.append(
            f"Only {measured_count}/{total_count} dimensions measured "
            f"(weight coverage: {confidence:.0%}). Score is unreliable — "
            f"unmeasured: {', '.join(unmeasured)}"
        )
    elif measured_count <= 4:
        warnings.append(
            f"{measured_count}/{total_count} dimensions measured "
            f"(weight coverage: {confidence:.0%}). "
            f"Unmeasured: {', '.join(unmeasured)}"
        )

    return {
        "score": composite,
        "measured_dimensions": measured_count,
        "total_dimensions": total_count,
        "weight_coverage": confidence,
        "unmeasured": unmeasured,
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser(description="SkillForge Quality Scorer")
    parser.add_argument("skill_path", help="Path to SKILL.md")
    parser.add_argument("--eval-suite", help="Path to eval suite JSON", default=None)
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    eval_suite = None
    if args.eval_suite and Path(args.eval_suite).exists():
        eval_suite = json.loads(Path(args.eval_suite).read_text())
    else:
        # Auto-discover eval-suite.json as sibling of SKILL.md
        skill_dir = Path(args.skill_path).parent
        auto_path = skill_dir / "eval-suite.json"
        if auto_path.exists():
            eval_suite = json.loads(auto_path.read_text())

    scores = {
        "structure": score_structure(args.skill_path),
        "triggers": score_triggers(args.skill_path, eval_suite),
        "quality": score_quality(args.skill_path, eval_suite),
        "edges": score_edges(args.skill_path, eval_suite),
        "efficiency": score_efficiency(args.skill_path),
        "composability": score_composability(args.skill_path),
    }

    composite_result = compute_composite(scores)

    result = {
        "skill_path": args.skill_path,
        "composite_score": composite_result["score"],
        "confidence": {
            "measured": composite_result["measured_dimensions"],
            "total": composite_result["total_dimensions"],
            "weight_coverage": composite_result["weight_coverage"],
            "unmeasured": composite_result["unmeasured"],
        },
        "warnings": composite_result["warnings"],
        "dimensions": {k: v["score"] for k, v in scores.items()},
        "issues": {k: v["issues"] for k, v in scores.items() if v["issues"]},
        "details": {k: v["details"] for k, v in scores.items() if v["details"]},
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"  SkillForge Quality Score: {composite_result['score']}/100")

        # Show confidence warning
        mc = composite_result['measured_dimensions']
        tc = composite_result['total_dimensions']
        wc = composite_result['weight_coverage']
        if mc < tc:
            print(f"  [{mc}/{tc} dimensions measured, {wc:.0%} weight coverage]")

        print(f"{'='*60}")
        for dim, data in scores.items():
            s = data["score"]
            indicator = "\u2713" if s >= 70 else "\u25b3" if s >= 50 else "\u2717" if s >= 0 else "\u2014"
            score_str = f"{s}" if s >= 0 else "n/a"
            print(f"  {indicator} {dim:15s} {score_str:>5s}")
        print(f"{'='*60}")

        # Show warnings
        for warning in composite_result.get("warnings", []):
            print(f"\n  \u26a0  {warning}")

        all_issues = [i for v in scores.values() for i in v["issues"]
                      if i != "requires_runtime_eval"]
        if all_issues:
            print(f"\n  Issues found:")
            for issue in all_issues:
                print(f"    \u2022 {issue}")
        print()


if __name__ == "__main__":
    main()
