"""Score trigger accuracy using eval suite.

Uses TF-IDF-inspired scoring instead of naive word overlap:
1. Extracts meaningful terms (stopwords removed)
2. Weights rare/specific terms higher than common ones
3. Handles negation in description ("do NOT use for X")
4. Requires higher threshold for positive triggers
"""
import math
from collections import Counter
from typing import Optional

from shared import read_skill_safe, extract_description
from nlp import tokenize_meaningful as _tokenize_meaningful
from scoring.patterns import (
    _RE_NEGATION_BOUNDARIES, _RE_CREATION_PATTERNS, _has_skill_domain_signal,
)


def score_triggers(skill_path: str, eval_suite: Optional[dict]) -> dict:
    """Score trigger accuracy using eval suite.

    Uses TF-IDF-inspired scoring instead of naive word overlap:
    1. Extracts meaningful terms (stopwords removed)
    2. Weights rare/specific terms higher than common ones
    3. Handles negation in description ("do NOT use for X")
    4. Requires higher threshold for positive triggers
    """
    if not eval_suite or "triggers" not in eval_suite or not eval_suite["triggers"]:
        return {"score": -1, "issues": ["no_trigger_eval_suite"], "details": {}}

    try:
        content = read_skill_safe(skill_path)
    except (FileNotFoundError, ValueError):
        return {"score": 0, "issues": ["file_not_found"], "details": {}}
    description = extract_description(content)

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
            idf = max(1.0, math.log(num_triggers / (term_doc_freq.get(term, 1) + 1)) + 1)
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

        # Scale threshold down for small eval suites so skills with few
        # triggers can still accumulate enough overlap score.
        # Floor at 1.5 to prevent single-term matches from passing.
        if num_triggers < 5:
            threshold = max(1.5, threshold * (num_triggers / 5))

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

    # Cap score for small eval suites — low sample size = low confidence
    if total < 8:
        score = min(score, 60)

    # Identify failure patterns
    issues = []
    if total < 8:
        issues.append(f"low_confidence_triggers:{total}_of_8_minimum")
    false_positives = sum(1 for d in details_per_trigger if d["predicted"] and not d["expected"])
    false_negatives = sum(1 for d in details_per_trigger if not d["predicted"] and d["expected"])
    if false_positives > 0:
        issues.append(f"false_positives:{false_positives}")
    if false_negatives > 0:
        issues.append(f"false_negatives:{false_negatives}")

    # Compute precision and recall (Issue #13)
    true_positives = sum(1 for d in details_per_trigger if d["predicted"] and d["expected"])
    precision = round(true_positives / (true_positives + false_positives) * 100, 1) if (true_positives + false_positives) > 0 else 0.0
    recall = round(true_positives / (true_positives + false_negatives) * 100, 1) if (true_positives + false_negatives) > 0 else 0.0

    return {
        "score": score,
        "precision": precision,
        "recall": recall,
        "issues": issues,
        "details": {
            "correct": correct,
            "total": total,
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "per_trigger": details_per_trigger,
        }
    }
