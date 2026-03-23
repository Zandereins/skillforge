"""Score composability — how well this skill plays with others.

Static analysis checks (no runtime needed):
- Clear scope boundaries (20 pts)
- No global state assumptions (20 pts)
- Input/output contract clarity (20 pts)
- Explicit handoff points (20 pts)
- No conflicting tool assumptions (20 pts)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import read_skill_safe
from scoring.patterns import (
    _RE_POSITIVE_SCOPE, _RE_NEGATIVE_SCOPE, _RE_GLOBAL_STATE,
    _RE_INPUT_SPEC, _RE_OUTPUT_SPEC, _RE_HANDOFF, _RE_WHEN_NOT,
    _RE_HARD_REQUIREMENTS, _RE_ALTERNATIVES,
)


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
        content = read_skill_safe(skill_path)
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
