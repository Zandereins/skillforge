"""Score eval suite quality — static analysis of test case coverage.

Checks whether the eval suite has well-structured test cases that
cover the skill's features with diverse assertion types.

Scoring (100 pts total):
- Has 3+ test cases with well-formed assertions: 30 pts
- Assertions cover multiple types (contains, pattern, excludes, format): 25 pts
- Test cases cover different skill features (analyze, improve, report): 25 pts
- All assertions have descriptions: 20 pts
"""
from typing import Optional

from scoring.coherence import score_coherence


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
    feature_keywords = {
        "analyze", "improve", "report", "validate", "generate",
        "format", "compare", "summarize", "create", "check",
        "review", "test", "build", "deploy", "fix", "debug",
        "search", "parse", "transform", "optimize",
    }
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
