"""Check instruction-assertion alignment as a static correctness proxy.

Cross-references imperative instructions in the skill body against
assertion values in the eval suite's test_cases. Returns a bonus score
(0-10) based on how many instruction topics are covered by assertions.
"""
import sys
from typing import Optional
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import read_skill_safe
from nlp import STOPWORDS, stem as _stem, RE_WORD_TOKEN as _RE_WORD_TOKEN
from scoring.patterns import _RE_IMPERATIVE_INSTRUCTION


def score_coherence(skill_path: str, eval_suite: Optional[dict]) -> dict:
    """Check instruction-assertion alignment as a static correctness proxy.

    Cross-references imperative instructions in the skill body against
    assertion values in the eval suite's test_cases. Returns a bonus score
    (0-10) based on how many instruction topics are covered by assertions.
    """
    if not eval_suite or "test_cases" not in eval_suite:
        return {"bonus": 0, "details": {"reason": "no_eval_suite"}}

    try:
        content = read_skill_safe(skill_path)
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
