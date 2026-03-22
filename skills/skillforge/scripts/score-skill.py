#!/usr/bin/env python3
"""SkillForge — Skill Structural Scorer

Computes a composite structural score across 6 dimensions.
Used during the autonomous improvement loop to decide keep/discard.

IMPORTANT: This is a STRUCTURAL score — it measures file organization,
keyword coverage, and eval suite completeness. It does NOT measure whether
the skill actually works correctly at runtime. For runtime validation,
use the --runtime flag or run runtime-evaluator.py separately.

Usage:
    python score-skill.py /path/to/SKILL.md [--eval-suite eval.json] [--json]

Outputs composite score and per-dimension breakdown.
"""

import argparse
import json
import math
import re
import subprocess
import sys
from collections import Counter
from typing import Optional
from pathlib import Path

# Ensure scripts directory is on path for shared module imports
sys.path.insert(0, str(Path(__file__).parent))
from shared import regex_search_safe as _regex_search_safe, read_skill_safe, extract_description, VALID_DIMENSIONS, MAX_SKILL_SIZE, invalidate_cache as _shared_invalidate_cache
from nlp import STOPWORDS, stem as _stem, tokenize_meaningful as _tokenize_meaningful, SYNONYM_TABLE, _SYNONYM_GROUPS, RE_WORD_TOKEN as _RE_WORD_TOKEN

# --- Pre-compiled regex patterns (Change 3) ---
# Used in score_structure()
_RE_FRONTMATTER_NAME = re.compile(r"^name:\s*\S+", re.MULTILINE)
_RE_FRONTMATTER_DESC = re.compile(r"^description:", re.MULTILINE)
_RE_REAL_EXAMPLES = re.compile(
    r"(?i)(example\s*[0-9:#]|input.*output|e\.g\.|for instance|for example)"
)
_RE_CODE_BLOCKS = re.compile(r"```")
_RE_HEADERS = re.compile(r"^##\s", re.MULTILINE)
_RE_HEDGING = re.compile(
    r"you (might|could|should|may) (want to|consider|possibly)", re.IGNORECASE
)
_RE_REFS = re.compile(r"(references|scripts|templates)/[\w./-]+")
_RE_TODO = re.compile(r"(?i)(TODO|FIXME|HACK|XXX|placeholder)")
_RE_SECTION_HEADER = re.compile(r"^##\s")

# Used in score_efficiency()
_RE_ACTIONABLE_LINES = re.compile(
    r"^(?:\d+\.\s*)?(?:Read|Run|Check|Create|Add|Remove|Move|Use|Set|"
    r"Install|Configure|Deploy|Test|Verify|Build|Start|Stop|Open|Save|"
    r"Copy|Delete|Write|Edit|Update|Generate|Execute|Validate|Parse|"
    r"Extract|Transform|Import|Export|Send|Fetch|Call|Return)\b",
    re.MULTILINE,
)
_RE_WHY_COUNT = re.compile(
    r"\b(because|since|this enables|this prevents|this means|the reason|"
    r"this ensures|this avoids|otherwise|so that|why[:\s])\b",
    re.IGNORECASE,
)
_RE_VERIFICATION_CMDS = re.compile(r"```\s*(?:bash|sh)\b")
_RE_FILLER_PHRASES = re.compile(
    r"(?i)(it is important to note that|as mentioned (above|earlier|before)|"
    r"in other words|that is to say|keep in mind that|note that|"
    r"it should be noted|please note|remember that|be aware that|"
    r"it's worth mentioning)"
)
_RE_OBVIOUS_INSTRUCTIONS = re.compile(
    r"(?i)(make sure to save|don't forget to|always test your|"
    r"be careful when|ensure you have|make sure you|"
    r"remember to commit|use version control)"
)
_RE_SCOPE_BOUNDARY = re.compile(r"(?i)(do not|don't) use (for|when|if)")

# Used in score_composability()
_RE_POSITIVE_SCOPE = re.compile(
    r"(?i)(use this skill when|use when|trigger when|activate for)"
)
_RE_NEGATIVE_SCOPE = re.compile(
    r"(?i)(do not use|don't use|NOT for|not use for|out of scope)"
)
_RE_GLOBAL_STATE = re.compile(
    r"(?i)(must be installed globally|global config|~\/\.|modify system|"
    r"system-wide|/etc/|export\s+\w+=)"
)
_RE_INPUT_SPEC = re.compile(
    r"(?i)(input:|takes.*as input|expects|requires.*file|requires.*path|target.*skill)"
)
_RE_OUTPUT_SPEC = re.compile(
    r"(?i)(output:|produces|generates|creates|saves.*to|writes.*to|returns)"
)
_RE_HANDOFF = re.compile(
    r"(?i)(then use|hand off to|pass to|chain with|followed by|"
    r"complementary|works with|after.*use|before.*use|"
    r"skill-creator|next step)"
)
_RE_WHEN_NOT = re.compile(
    r"(?i)(if.*instead use|for.*use.*instead|suggest using)"
)
_RE_HARD_REQUIREMENTS = re.compile(
    r"(?i)(requires?\s+(?:npm|pip|brew|apt|docker|node|python)\b)"
)
_RE_ALTERNATIVES = re.compile(
    r"(?i)(alternatively|or use|if.*not available|fallback)"
)

# Used in score_clarity()
_RE_ALWAYS_PATTERNS = re.compile(r"(?i)\b(always|must)\s+(\w+(?:\s+\w+)?)")
_RE_NEVER_PATTERNS = re.compile(r"(?i)\b(never|must not|do not|don't)\s+(\w+(?:\s+\w+)?)")
_RE_VAGUE_REF = re.compile(
    r"\b(the\s+(?:file|script|output|result|command|path|tool|config))\b", re.IGNORECASE
)
_RE_BACKTICK_REF = re.compile(r"`[^`]+`")
_RE_SPECIFIC_REF = re.compile(r"(`[^`]+`|[\w/]+\.\w+|/[\w/]+)")
_RE_AMBIGUOUS_PRONOUN = re.compile(
    r"^\s*(It|This|That)\s+(is|does|will|can|should|has|was|means)\b"
)
_RE_RUN_PATTERN = re.compile(
    r"^\s*(?:\d+\.\s*)?(?:Run|Execute|Install|Configure)\s+(.+)", re.IGNORECASE
)
_RE_CONCEPTUAL = re.compile(
    r"(?i)(baseline|all\s+\d+|VERIFY|evolution|the\s+\w+\s+(?:on|for|to|with|against))"
)
_RE_CONCRETE_CMD = re.compile(r"(`[^`]+`|[\w/.-]+\.\w+|/[\w/]+)")
_RE_CODE_BLOCK_START = re.compile(r"^```")

# Used in score_triggers() / _has_skill_domain_signal()
_RE_CREATION_PATTERNS = re.compile(
    r"(?i)(from scratch|brand new|new\b.{0,20}\bskill|create\b.{0,20}\bskill|"
    r"build\b.{0,20}\bskill|write\b.{0,20}\bskill|design\b.{0,20}\bskill)"
)
_RE_NEGATION_BOUNDARIES = re.compile(
    r"(?:do not|don't|NOT|never)\s+(?:use\s+)?(?:for|when|if|with)?\s*(.+?)(?:\.|,|$)",
    re.IGNORECASE,
)
# _RE_WORD_TOKEN now imported from nlp.py
# _RE_DESC_BLOCK, _RE_DESC_INLINE, _extract_description now in shared.py

# Used in score_diff()
_RE_DIFF_SIGNAL = re.compile(
    r"^(?:\d+\.\s*)?(?:Read|Run|Check|Create|Add|Remove|Move|Use|Set|"
    r"Install|Configure|Deploy|Test|Verify|Build|Start|Stop|Open|Save|"
    r"Copy|Delete|Write|Edit|Update|Generate|Execute|Validate|Parse|"
    r"Extract|Transform|Import|Export|Send|Fetch|Call|Return)\b",
    re.IGNORECASE,
)
_RE_DIFF_EXAMPLE = re.compile(
    r"(?i)(example\s*[0-9:#]|input.*output|e\.g\.|for instance|for example)"
)
_RE_DIFF_NOISE = re.compile(
    r"(?i)(you (might|could|should|may) (want to|consider|possibly)|"
    r"it is important to note that|as mentioned (above|earlier|before)|"
    r"in other words|keep in mind that|note that|please note|"
    r"make sure to save|don't forget to|always test your)"
)

# Used in score_coherence() (Change 2)
_RE_IMPERATIVE_INSTRUCTION = re.compile(
    r"^\s*(?:\d+\.\s*)?(?:Run|Create|Add|Check|Remove|Move|Use|Set|Install|"
    r"Configure|Deploy|Test|Verify|Build|Start|Stop|Open|Save|Copy|Delete|"
    r"Write|Edit|Update|Generate|Execute|Validate|Parse|Extract|Transform|"
    r"Import|Export|Send|Fetch|Call|Return)\b(.+)",
    re.IGNORECASE,
)
_RE_CODE_BLOCK_REGION = re.compile(r"```[\s\S]*?```")

# MAX_SKILL_SIZE, read_skill_safe, invalidate_cache now imported from shared.py
# Keep local aliases for backward compatibility with external callers
_read_skill_safe = read_skill_safe


def invalidate_cache(skill_path: str) -> None:
    """Invalidate the file cache for a given skill path.

    Public API — delegates to shared.invalidate_cache (single cache).
    """
    _shared_invalidate_cache(skill_path)


# NLP utilities and shared constants now imported at top of file


def score_structure(skill_path: str) -> dict:
    """Score structural quality of a skill file.

    Uses inline Python analysis directly — no external bash dependency.
    """
    return _score_structure_inline(skill_path)


def _score_structure_inline(skill_path: str) -> dict:
    """Fallback structural scoring without the bash script."""
    score = 0
    issues = []

    try:
        content = _read_skill_safe(skill_path)
    except (FileNotFoundError, ValueError):
        return {"score": 0, "issues": ["file_not_found"], "details": {}}

    lines = content.split("\n")

    # Frontmatter
    if lines and lines[0].strip() == "---":
        score += 10
        if _RE_FRONTMATTER_NAME.search(content):
            score += 10
        else:
            issues.append("missing_name")
        if _RE_FRONTMATTER_DESC.search(content):
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
    real_examples = len(_RE_REAL_EXAMPLES.findall(content))
    code_block_pairs = len(_RE_CODE_BLOCKS.findall(content)) // 2
    if real_examples >= 2:
        score += 10
    elif real_examples >= 1 or (real_examples + code_block_pairs // 3) >= 2:
        score += 5
    else:
        issues.append("no_real_examples")

    # Headers
    header_count = len(_RE_HEADERS.findall(content))
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
    hedge_count = len(_RE_HEDGING.findall(content))
    if hedge_count == 0:
        score += 5
    elif hedge_count <= 2:
        score += 3

    # Referenced files exist
    refs = set(_RE_REFS.findall(content))
    missing = [r for r in refs if not (skill_dir / r).exists()]
    if not missing:
        score += 10
    else:
        score += 5
        issues.append(f"missing_refs: {missing}")

    # No dead content (TODO/FIXME/placeholder, empty sections)
    todo_count = len(_RE_TODO.findall(content))
    # Check for headers followed by only blank lines or next header
    empty_sections = 0
    for i, line in enumerate(lines):
        if _RE_SECTION_HEADER.match(line):
            # Look at next 5 non-empty lines
            next_content = 0
            for j in range(i + 1, min(i + 6, len(lines))):
                if lines[j].strip() and not lines[j].startswith("#"):
                    next_content += 1
            if next_content == 0:
                empty_sections += 1
    if todo_count == 0 and empty_sections == 0:
        score += 10
    elif todo_count == 0:
        score += 7
        issues.append(f"has_empty_sections:{empty_sections}")
    else:
        issues.append(f"has_todo_or_placeholder_text:{todo_count}")
        if empty_sections > 0:
            issues.append(f"has_empty_sections:{empty_sections}")

    return {"score": max(0, min(100, score)), "issues": issues, "details": {"line_count": len(lines)}}


# _extract_description = extract_description (imported from shared.py at top)
_extract_description = extract_description


# _stem, _tokenize_meaningful, SYNONYM_TABLE, _SYNONYM_GROUPS now imported from nlp.py


# Pre-compiled domain signal patterns (avoids ~300 re.search compilations per scoring run)
_RE_STRONG_DOMAIN_SIGNAL = re.compile(
    r"skill\.md|skill\s*forge|my\s+skill|this\s+skill|the\s+skill|"
    r"skill\s+(?:trigger|description|improvement|quality|needs|work)|"
    r"improve\s+(?:my|this|the)\s+skill|"
    r"(?:trigger|eval)\s+(?:accuracy|suite|test)|"
    r"skill\s+(?:and|but|needs|is|has)",
    re.IGNORECASE,
)
_RE_ANTI_DOMAIN_SIGNAL = re.compile(
    r"python\s+function|rest\s+api|docker|"
    r"security\s+vulnerab|\.py\b|\.ts\b|\.js\b|"
    r"open\s+source\s+project|readme|prompt\s+template",
    re.IGNORECASE,
)


def _has_skill_domain_signal(prompt: str) -> float:
    """Check if prompt is about skills (not generic code/config).

    Returns a multiplier: 1.8 for strong signal, 1.0 for neutral, 0.4 for anti-signal.
    """
    prompt_lower = prompt.lower()

    if _RE_STRONG_DOMAIN_SIGNAL.search(prompt_lower):
        return 1.8

    if "skill" in prompt_lower:
        return 1.2

    if _RE_ANTI_DOMAIN_SIGNAL.search(prompt_lower):
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

    try:
        content = _read_skill_safe(skill_path)
    except (FileNotFoundError, ValueError):
        return {"score": 0, "issues": ["file_not_found"], "details": {}}
    description = _extract_description(content)

    if not description:
        return {"score": 0, "issues": ["empty_description"], "details": {}}

    desc_lower = description.lower()

    # Extract negative boundaries from description
    neg_patterns = _RE_NEGATION_BOUNDARIES.findall(description)
    negative_terms = set()
    for pat in neg_patterns:
        negative_terms.update(_tokenize_meaningful(pat))

    # Meaningful description terms (excluding negated ones for positive matching)
    desc_terms = _tokenize_meaningful(desc_lower, expand_reverse=True)
    desc_term_set = set(desc_terms)
    positive_desc_terms = desc_term_set - negative_terms

    # Build IDF-like weights: terms that appear in fewer triggers are more discriminative
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
        creation_patterns = _RE_CREATION_PATTERNS.findall(prompt)
        if creation_patterns:
            overlap_score *= 0.1  # Strong penalty: creation is anti-signal for improvement

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
    try:
        content = _read_skill_safe(skill_path)
    except (FileNotFoundError, ValueError):
        return {"score": 0, "issues": ["file_not_found"], "details": {}}

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
    actionable_lines = len(_RE_ACTIONABLE_LINES.findall(content))

    # Real examples (input/output pairs, not just code blocks)
    real_examples = len(_RE_REAL_EXAMPLES.findall(content))

    # WHY-based reasoning (explains rationale)
    why_count = len(_RE_WHY_COUNT.findall(content))

    # Verification commands (executable checks)
    verification_cmds = len(_RE_VERIFICATION_CMDS.findall(content))

    # --- Noise indicators (what wastes tokens) ---

    # Hedging language
    hedge_count = len(_RE_HEDGING.findall(content))

    # Redundant phrases (saying the same thing multiple ways)
    filler_phrases = len(_RE_FILLER_PHRASES.findall(content))

    # Instructions Claude already knows (generic coding advice)
    obvious_instructions = len(_RE_OBVIOUS_INSTRUCTIONS.findall(content))

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
    if _RE_SCOPE_BOUNDARY.search(full_content):
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
        content = _read_skill_safe(skill_path)
    except (FileNotFoundError, ValueError):
        return {"score": 0, "issues": ["file_not_found"], "details": {}}

    score = 0
    issues = []

    # 1. Clear scope boundaries (20 pts)
    has_positive_scope = bool(_RE_POSITIVE_SCOPE.search(content))
    has_negative_scope = bool(_RE_NEGATIVE_SCOPE.search(content))
    if has_positive_scope and has_negative_scope:
        score += 20
    elif has_positive_scope or has_negative_scope:
        score += 10
        issues.append("partial_scope_boundaries")
    else:
        issues.append("no_scope_boundaries")

    # 2. No global state assumptions (20 pts)
    global_state_patterns = _RE_GLOBAL_STATE.findall(content)
    if not global_state_patterns:
        score += 20
    elif len(global_state_patterns) <= 2:
        score += 10
        issues.append(f"some_global_state_assumptions:{len(global_state_patterns)}")
    else:
        issues.append(f"heavy_global_state_assumptions:{len(global_state_patterns)}")

    # 3. Input/output contract clarity (20 pts)
    has_input_spec = bool(_RE_INPUT_SPEC.search(content))
    has_output_spec = bool(_RE_OUTPUT_SPEC.search(content))
    if has_input_spec and has_output_spec:
        score += 20
    elif has_input_spec or has_output_spec:
        score += 10
        issues.append("partial_io_contract")
    else:
        issues.append("no_io_contract")

    # 4. Explicit handoff points (20 pts)
    has_handoff = bool(_RE_HANDOFF.search(content))
    has_when_not = bool(_RE_WHEN_NOT.search(content))
    if has_handoff and has_when_not:
        score += 20
    elif has_handoff or has_when_not:
        score += 12
    else:
        issues.append("no_handoff_points")

    # 5. No conflicting tool assumptions (20 pts)
    # Check for hard-coded tool requirements without alternatives
    hard_requirements = _RE_HARD_REQUIREMENTS.findall(content)
    has_alternatives = bool(_RE_ALTERNATIVES.search(content))
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


def score_coherence(skill_path: str, eval_suite: Optional[dict]) -> dict:
    """Check instruction-assertion alignment as a static correctness proxy.

    Cross-references imperative instructions in the skill body against
    assertion values in the eval suite's test_cases. Returns a bonus score
    (0-10) based on how many instruction topics are covered by assertions.
    """
    if not eval_suite or "test_cases" not in eval_suite:
        return {"bonus": 0, "details": {"reason": "no_eval_suite"}}

    try:
        content = _read_skill_safe(skill_path)
    except (FileNotFoundError, ValueError):
        return {"bonus": 0, "details": {"reason": "file_not_found"}}

    # Strip frontmatter
    body = content
    if content.startswith("---"):
        end = content.find("---", 3)
        if end > 0:
            body = content[end + 3:]

    # 1. Extract imperative instruction topics from skill body
    instruction_topics = set()
    for line in body.split("\n"):
        m = _RE_IMPERATIVE_INSTRUCTION.match(line)
        if m:
            rest = m.group(1).strip()
            # Extract meaningful words from the instruction
            words = _RE_WORD_TOKEN.findall(rest.lower())
            for w in words:
                if w not in STOPWORDS and len(w) >= 4:
                    instruction_topics.add(_stem(w))

    if not instruction_topics:
        return {"bonus": 0, "details": {"reason": "no_instructions_found"}}

    # 2. Extract assertion values from test_cases
    assertion_topics = set()
    for tc in eval_suite["test_cases"]:
        for assertion in tc.get("assertions", []):
            value = assertion.get("value", "")
            if value:
                words = _RE_WORD_TOKEN.findall(value.lower())
                for w in words:
                    if w not in STOPWORDS and len(w) >= 4:
                        assertion_topics.add(_stem(w))

    if not assertion_topics:
        return {"bonus": 0, "details": {"reason": "no_assertion_values"}}

    # 3. Check overlap: how many instruction topics appear in assertions
    covered = instruction_topics & assertion_topics
    coverage_ratio = len(covered) / len(instruction_topics) if instruction_topics else 0

    # Score: 10 pts for full coverage, proportional otherwise
    bonus = min(10, round(coverage_ratio * 10))

    return {
        "bonus": bonus,
        "details": {
            "instruction_topics": len(instruction_topics),
            "assertion_topics": len(assertion_topics),
            "covered_topics": len(covered),
            "coverage_ratio": round(coverage_ratio, 2),
        },
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

    # 5. Instruction-assertion coherence bonus (up to +10 pts)
    coherence = score_coherence(skill_path, eval_suite)
    coherence_bonus = coherence["bonus"]
    score += coherence_bonus

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
            "coherence_bonus": coherence_bonus,
            "coherence_details": coherence["details"],
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


def score_runtime(skill_path: str, eval_suite: Optional[dict] = None,
                   enabled: bool = False) -> dict:
    """Score runtime effectiveness by invoking Claude with test prompts.

    Opt-in dimension — returns -1 (skip) unless explicitly enabled.
    Requires `claude` CLI to be available. Returns score -1 if unavailable
    (graceful degradation — dimension is skipped in composite).

    Runs up to 3 test cases from eval suite, checks response_* assertions.

    Args:
        enabled: Must be True to actually run (default: False → returns -1)
    """
    if not enabled:
        return {"score": -1, "issues": ["runtime_not_enabled"], "details": {}}

    # Check claude CLI availability
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True, text=True, timeout=5, errors="replace"
        )
        if result.returncode != 0:
            return {"score": -1, "issues": ["claude_cli_unavailable"], "details": {}}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"score": -1, "issues": ["claude_cli_unavailable"], "details": {}}

    if not eval_suite or "test_cases" not in eval_suite:
        return {"score": -1, "issues": ["no_eval_suite_for_runtime"], "details": {}}

    # Find test cases with response_* assertions
    runtime_cases = []
    for tc in eval_suite["test_cases"]:
        assertions = tc.get("assertions", [])
        runtime_asserts = [a for a in assertions if a.get("type", "").startswith("response_")]
        if runtime_asserts:
            runtime_cases.append({"tc": tc, "assertions": runtime_asserts})

    if not runtime_cases:
        return {"score": -1, "issues": ["no_runtime_assertions"], "details": {}}

    # Run up to 3 cases to limit cost
    runtime_cases = runtime_cases[:3]

    try:
        content = _read_skill_safe(skill_path)
    except (FileNotFoundError, ValueError):
        return {"score": 0, "issues": ["file_not_found"], "details": {}}

    passed = 0
    total = 0
    per_case = []

    for rc in runtime_cases:
        tc = rc["tc"]
        prompt = tc.get("prompt", "")
        if not prompt:
            continue

        # Invoke claude with the skill content prepended to the prompt
        try:
            full_prompt = f"[SKILL CONTEXT]\n{content}\n\n[USER REQUEST]\n{prompt}"
            result = subprocess.run(
                ["claude", "-p", full_prompt, "--no-input"],
                capture_output=True, text=True, timeout=60, errors="replace",
            )
            response = result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            per_case.append({"id": tc.get("id", "?"), "status": "timeout"})
            total += len(rc["assertions"])
            continue

        # Check assertions
        for assertion in rc["assertions"]:
            total += 1
            atype = assertion.get("type", "")
            value = assertion.get("value", "")
            case_passed = False

            if atype == "response_contains":
                case_passed = value.lower() in response.lower()
            elif atype == "response_matches":
                try:
                    case_passed = _regex_search_safe(value, response)
                except re.error:
                    case_passed = False
            elif atype == "response_excludes":
                case_passed = value.lower() not in response.lower()

            if case_passed:
                passed += 1

        per_case.append({
            "id": tc.get("id", "?"),
            "status": "ok",
            "response_length": len(response),
        })

    score = int((passed / total) * 100) if total > 0 else 0
    return {
        "score": score,
        "issues": [] if score >= 70 else [f"runtime_pass_rate_low:{passed}/{total}"],
        "details": {
            "passed": passed,
            "total": total,
            "cases_run": len(per_case),
            "per_case": per_case,
        }
    }


_calibrated_weights_cache: Optional[dict] = None
_calibrated_weights_mtime: float = 0.0
_calibrated_weights_path: str = ""


def _load_calibrated_weights() -> Optional[dict]:
    """Load auto-calibrated weights from ~/.skillforge/meta/calibrated-weights.json.

    Uses module-level cache with mtime invalidation to avoid repeated disk reads.
    """
    global _calibrated_weights_cache, _calibrated_weights_mtime, _calibrated_weights_path
    path = Path.home() / ".skillforge" / "meta" / "calibrated-weights.json"
    path_str = str(path)

    if not path.exists():
        _calibrated_weights_cache = None
        return None

    current_mtime = path.stat().st_mtime
    if (_calibrated_weights_cache is not None
            and path_str == _calibrated_weights_path
            and current_mtime == _calibrated_weights_mtime):
        return _calibrated_weights_cache

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and all(isinstance(v, (int, float)) for v in data.values()):
            _calibrated_weights_cache = data
            _calibrated_weights_mtime = current_mtime
            _calibrated_weights_path = path_str
            return data
    except (json.JSONDecodeError, OSError):
        pass
    _calibrated_weights_cache = None
    return None


def compute_composite(scores: dict, custom_weights: Optional[dict] = None) -> dict:
    """Compute weighted composite score with confidence indicator.

    Returns both the score and metadata about how many dimensions
    were actually measured, so users know how trustworthy the number is.

    Args:
        scores: Per-dimension score dicts from the individual scorers.
        custom_weights: Optional dict of dimension_name -> float weight.
            Values are normalized to sum to 1.0. Example:
            {"structure": 0.3, "triggers": 0.4, "efficiency": 0.3}
    """
    weights = {
        "structure": 0.15,
        "triggers": 0.20,
        "quality": 0.20,
        "edges": 0.15,
        "efficiency": 0.10,
        "composability": 0.05,
        "runtime": 0.15,
    }

    # Apply custom weights if provided (highest priority)
    if custom_weights:
        # Normalize custom weights to sum to 1.0
        total_w = sum(custom_weights.values())
        if total_w > 0:
            weights = {k: v / total_w for k, v in custom_weights.items()}
    else:
        # Try auto-calibrated weights (second priority)
        calibrated = _load_calibrated_weights()
        if calibrated:
            total_w = sum(calibrated.values())
            if total_w > 0:
                weights = {k: v / total_w for k, v in calibrated.items()}

    # If clarity is present, add it with weight 0.05 redistributed proportionally
    if "clarity" in scores:
        clarity_weight = 0.05
        scale = (1.0 - clarity_weight) / sum(weights.values())
        weights = {k: v * scale for k, v in weights.items()}
        weights["clarity"] = clarity_weight

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

    # Confidence notes: explain what each dimension can and cannot tell you
    confidence_notes = {
        "structure": "Measures file organization (frontmatter, headers, length, references). "
                     "Cannot assess whether instructions are correct or effective.",
        "triggers": "Measures keyword overlap between description and eval prompts using TF-IDF heuristic. "
                     "Cannot predict actual Claude triggering behavior — that requires runtime evaluation.",
        "quality": "Measures eval suite coverage (assertion types, feature breadth). "
                    "Cannot assess whether following the skill produces correct output.",
        "edges": "Measures edge case definitions in the eval suite. "
                  "Cannot verify the skill handles edge cases correctly at runtime.",
        "efficiency": "Measures information density (signal-to-noise ratio in text). "
                      "Cannot assess whether the content is actually useful to Claude.",
        "composability": "Measures scope boundaries and handoff declarations. "
                         "Cannot verify the skill works correctly alongside other skills.",
    }
    if "clarity" in scores:
        confidence_notes["clarity"] = (
            "Measures contradiction, vague reference, and ambiguity patterns. "
            "Cannot assess whether instructions are clear to Claude in practice."
        )

    # Determine score type based on what was measured
    has_runtime = "runtime" in measured
    score_type = "structural+runtime" if has_runtime else "structural"

    return {
        "score": composite,
        "score_type": score_type,
        "measured_dimensions": measured_count,
        "total_dimensions": total_count,
        "weight_coverage": confidence,
        "unmeasured": unmeasured,
        "warnings": warnings,
        "confidence_notes": {k: v for k, v in confidence_notes.items() if k in measured},
    }


def score_clarity(skill_path: str) -> dict:
    """Score instruction clarity — detect contradictions, ambiguity, vague references.

    Optional 7th dimension with zero default weight. Activated via --clarity.

    Sub-checks (100 pts total):
    - Contradiction detection (30 pts): "always X" vs "never X" on same topic
    - Vague reference detection (25 pts): "the file" without antecedent
    - Ambiguous pronoun detection (20 pts): sentences starting with It/This/That
    - Instruction completeness (25 pts): every "Run X" has a concrete command
    """
    try:
        content = _read_skill_safe(skill_path)
    except (FileNotFoundError, ValueError):
        return {"score": 0, "issues": ["file_not_found"], "details": {}}

    # Strip frontmatter
    body = content
    if content.startswith("---"):
        end = content.find("---", 3)
        if end > 0:
            body = content[end + 3:]

    # Strip code blocks before clarity analysis (avoid false positives
    # from "always"/"never" inside code examples)
    prose_body = _RE_CODE_BLOCK_REGION.sub("", body)

    lines = prose_body.strip().split("\n")

    # Empty body check
    if not prose_body.strip():
        return {"score": 0, "issues": ["empty_skill_body"], "details": {}}

    score = 100
    issues = []
    details: dict = {}

    # 1. Contradiction detection (30 pts)
    # Find "always/never/must/must not" pairs on overlapping topics
    # Compare first verb only to catch "always run X" vs "never run Y"
    always_patterns = _RE_ALWAYS_PATTERNS.findall(prose_body)
    never_patterns = _RE_NEVER_PATTERNS.findall(prose_body)

    always_topics = {topic.lower().strip() for _, topic in always_patterns}
    never_topics = {topic.lower().strip() for _, topic in never_patterns}
    contradictions = always_topics & never_topics

    if contradictions:
        penalty = min(30, len(contradictions) * 10)
        score -= penalty
        issues.append(f"contradictions:{len(contradictions)}")
        details["contradictions"] = sorted(contradictions)
    details["always_count"] = len(always_patterns)
    details["never_count"] = len(never_patterns)

    # 2. Vague reference detection (25 pts)
    # "the file", "the script", "the output" without clear antecedent in preceding 3 lines
    vague_refs = []
    for i, line in enumerate(lines):
        matches = _RE_VAGUE_REF.findall(line)
        for match in matches:
            # Skip if backtick-quoted reference is on the same line (e.g., "the file `output.json`")
            if _RE_BACKTICK_REF.search(line):
                continue
            # Check preceding 3 lines for a specific file/path reference
            context = "\n".join(lines[max(0, i - 3):i])
            # If no specific path, filename, or backtick-quoted reference nearby, it's vague
            if not _RE_SPECIFIC_REF.search(context):
                vague_refs.append(f"line {i + 1}: {match}")

    if vague_refs:
        penalty = min(25, len(vague_refs) * 5)
        score -= penalty
        issues.append(f"vague_references:{len(vague_refs)}")
    details["vague_references"] = len(vague_refs)

    # 3. Ambiguous pronoun detection (20 pts)
    # Sentences starting with "It ", "This ", "That " without clear referent
    ambiguous_pronouns = []
    for i, line in enumerate(lines):
        if _RE_AMBIGUOUS_PRONOUN.match(line):
            # Check if preceding line provides a clear subject
            if i > 0:
                prev = lines[i - 1].strip()
                # If previous line is empty or a header, the pronoun is ambiguous
                if not prev or prev.startswith("#"):
                    ambiguous_pronouns.append(f"line {i + 1}")

    if ambiguous_pronouns:
        penalty = min(20, len(ambiguous_pronouns) * 5)
        score -= penalty
        issues.append(f"ambiguous_pronouns:{len(ambiguous_pronouns)}")
    details["ambiguous_pronouns"] = len(ambiguous_pronouns)

    # 4. Instruction completeness (25 pts)
    # Every "Run X" / "Execute X" should have a concrete command or path
    # Skip conceptual uses like "Run eval evolution BETWEEN sessions"
    incomplete_instructions = []
    for i, line in enumerate(lines):
        m = _RE_RUN_PATTERN.match(line)
        if m:
            rest = m.group(1).strip()
            # Skip conceptual instructions (not meant as shell commands)
            if _RE_CONCEPTUAL.search(rest):
                continue
            # Check if there's a backtick command, a path, or a code block nearby
            has_concrete = bool(_RE_CONCRETE_CMD.search(rest))
            # Also check next line for a code block
            if not has_concrete and i + 1 < len(lines):
                has_concrete = lines[i + 1].strip().startswith("```")
            if not has_concrete:
                incomplete_instructions.append(f"line {i + 1}: {line.strip()[:60]}")

    if incomplete_instructions:
        penalty = min(25, len(incomplete_instructions) * 8)
        score -= penalty
        issues.append(f"incomplete_instructions:{len(incomplete_instructions)}")
    details["incomplete_instructions"] = len(incomplete_instructions)

    return {
        "score": max(0, score),
        "issues": issues,
        "details": details,
    }


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


def main():
    parser = argparse.ArgumentParser(description="SkillForge Structural Scorer")
    parser.add_argument("skill_path", help="Path to SKILL.md")
    parser.add_argument("--eval-suite", help="Path to eval suite JSON", default=None)
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--diff", action="store_true", help="Include diff analysis")
    parser.add_argument("--diff-ref", default="HEAD~1", help="Git ref to diff against (default: HEAD~1)")
    parser.add_argument("--clarity", action="store_true", help="Include clarity dimension (zero weight by default)")
    parser.add_argument("--runtime", action="store_true",
                        help="Enable runtime scoring dimension (invokes claude CLI)")
    parser.add_argument("--weights", default=None,
                        help="Custom dimension weights as key=value pairs, e.g. "
                             "'structure=0.3,triggers=0.4,efficiency=0.3'. "
                             "Values are normalized to sum to 1.0.")
    args = parser.parse_args()

    eval_suite = None
    if args.eval_suite and Path(args.eval_suite).exists():
        try:
            eval_suite = json.loads(Path(args.eval_suite).read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"Error: malformed eval-suite JSON '{args.eval_suite}': {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Auto-discover eval-suite.json as sibling of SKILL.md
        skill_dir = Path(args.skill_path).parent
        auto_path = skill_dir / "eval-suite.json"
        if auto_path.exists():
            try:
                eval_suite = json.loads(auto_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                print(f"Warning: malformed eval-suite.json: {e}", file=sys.stderr)

    scores = {
        "structure": score_structure(args.skill_path),
        "triggers": score_triggers(args.skill_path, eval_suite),
        "quality": score_quality(args.skill_path, eval_suite),
        "edges": score_edges(args.skill_path, eval_suite),
        "efficiency": score_efficiency(args.skill_path),
        "composability": score_composability(args.skill_path),
        "runtime": score_runtime(args.skill_path, eval_suite, enabled=args.runtime),
    }

    # Clarity dimension (opt-in, zero default weight)
    if args.clarity:
        scores["clarity"] = score_clarity(args.skill_path)

    # Parse custom weights if provided
    custom_weights = None
    if args.weights:
        custom_weights = {}
        for pair in args.weights.split(","):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                dim_name = k.strip()
                if dim_name not in VALID_DIMENSIONS:
                    print(f"Error: unknown dimension '{dim_name}' — valid: {', '.join(sorted(VALID_DIMENSIONS))}", file=sys.stderr)
                    sys.exit(1)
                try:
                    custom_weights[dim_name] = float(v.strip())
                except ValueError:
                    print(f"Error: invalid weight value for '{dim_name}': '{v.strip()}' — expected a number", file=sys.stderr)
                    sys.exit(1)

    composite_result = compute_composite(scores, custom_weights)

    result = {
        "skill_path": args.skill_path,
        "composite_score": composite_result["score"],
        "score_type": composite_result["score_type"],
        "confidence": {
            "measured": composite_result["measured_dimensions"],
            "total": composite_result["total_dimensions"],
            "weight_coverage": composite_result["weight_coverage"],
            "unmeasured": composite_result["unmeasured"],
        },
        "warnings": composite_result["warnings"],
        "confidence_notes": composite_result.get("confidence_notes", {}),
        "dimensions": {k: v["score"] for k, v in scores.items()},
        "issues": {k: v["issues"] for k, v in scores.items() if v["issues"]},
        "details": {k: v["details"] for k, v in scores.items() if v["details"]},
    }

    # Diff analysis (opt-in)
    if args.diff:
        diff_analysis = score_diff(args.skill_path, args.diff_ref)
        result["diff_analysis"] = diff_analysis
        # Wire explain_score_change into diff output
        # Use current scores as "new" and zeros as "old" placeholder
        # (real old scores would come from previous run's JSON)
        current_scores = {k: v["score"] for k, v in scores.items() if v["score"] >= 0}
        explanations = explain_score_change({}, current_scores, diff_analysis)
        if explanations:
            result["score_explanations"] = explanations

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n{'='*60}")
        score_type = "Structural+Runtime" if args.runtime else "Structural"
        print(f"  SkillForge {score_type} Score: {composite_result['score']}/100")

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

        all_issues = [i for v in scores.values() for i in v["issues"]]
        if all_issues:
            print(f"\n  Issues found:")
            for issue in all_issues:
                print(f"    \u2022 {issue}")
        print()


if __name__ == "__main__":
    main()
