"""Score edge case coverage — static analysis of edge case definitions.

Checks whether the eval suite has comprehensive edge case coverage
across multiple failure categories.

Scoring (100 pts total):
- Has 5+ edge cases: 30 pts
- Covers multiple categories: 30 pts
- All edge cases have expected_behavior: 20 pts
- All edge cases have assertions: 20 pts
"""
import sys
from typing import Optional
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


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
