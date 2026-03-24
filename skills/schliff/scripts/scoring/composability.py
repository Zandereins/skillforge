"""Score composability — how well this skill plays with others.

Static analysis checks (no runtime needed), 10 checks × 10 pts each:
- Clear scope boundaries (10 pts)
- No global state assumptions (10 pts)
- Input/output contract clarity (10 pts)
- Explicit handoff points (10 pts)
- No conflicting tool assumptions (10 pts)
- Error/failure behavior described (10 pts)
- Idempotency/safety statement (10 pts)
- Dependency declarations (10 pts)
- Namespace/prefix isolation (10 pts)
- Version/compat notes (10 pts)
"""
from shared import read_skill_safe
from scoring.patterns import (
    _RE_POSITIVE_SCOPE, _RE_NEGATIVE_SCOPE, _RE_GLOBAL_STATE,
    _RE_INPUT_SPEC, _RE_OUTPUT_SPEC, _RE_HANDOFF, _RE_WHEN_NOT,
    _RE_HARD_REQUIREMENTS, _RE_ALTERNATIVES,
    _RE_ERROR_BEHAVIOR, _RE_IDEMPOTENCY, _RE_DEPENDENCY_DECL,
    _RE_NAMESPACE_ISOLATION, _RE_VERSION_COMPAT,
)


def score_composability(skill_path: str) -> dict:
    """Score composability — how well this skill plays with others.

    10 checks × 10 pts each = 100 pts max. Partial credit where appropriate.
    """
    try:
        content = read_skill_safe(skill_path)
    except (FileNotFoundError, ValueError):
        return {"score": 0, "issues": ["file_not_found"], "details": {}}

    score = 0
    issues = []

    # 1. Clear scope boundaries (10 pts)
    has_positive_scope = bool(_RE_POSITIVE_SCOPE.search(content))
    has_negative_scope = bool(_RE_NEGATIVE_SCOPE.search(content))
    if has_positive_scope and has_negative_scope:
        score += 10
    elif has_positive_scope or has_negative_scope:
        score += 5
        issues.append("partial_scope_boundaries")
    else:
        issues.append("no_scope_boundaries")

    # 2. No global state assumptions (10 pts)
    global_state_patterns = _RE_GLOBAL_STATE.findall(content)
    if not global_state_patterns:
        score += 10
    elif len(global_state_patterns) <= 2:
        score += 5
        issues.append(f"some_global_state_assumptions:{len(global_state_patterns)}")
    else:
        issues.append(f"heavy_global_state_assumptions:{len(global_state_patterns)}")

    # 3. Input/output contract clarity (10 pts)
    has_input_spec = bool(_RE_INPUT_SPEC.search(content))
    has_output_spec = bool(_RE_OUTPUT_SPEC.search(content))
    if has_input_spec and has_output_spec:
        score += 10
    elif has_input_spec or has_output_spec:
        score += 5
        issues.append("partial_io_contract")
    else:
        issues.append("no_io_contract")

    # 4. Explicit handoff points (10 pts)
    has_handoff = bool(_RE_HANDOFF.search(content))
    has_when_not = bool(_RE_WHEN_NOT.search(content))
    if has_handoff and has_when_not:
        score += 10
    elif has_handoff or has_when_not:
        score += 6
    else:
        issues.append("no_handoff_points")

    # 5. No conflicting tool assumptions (10 pts)
    hard_requirements = _RE_HARD_REQUIREMENTS.findall(content)
    has_alternatives = bool(_RE_ALTERNATIVES.search(content))
    if not hard_requirements or has_alternatives:
        score += 10
    elif len(hard_requirements) <= 2:
        score += 5
        issues.append("hard_tool_requirements_without_fallback")
    else:
        issues.append("many_hard_tool_requirements")

    # 6. Error/failure behavior described (10 pts)
    has_error_behavior = bool(_RE_ERROR_BEHAVIOR.search(content))
    if has_error_behavior:
        score += 10
    else:
        issues.append("no_error_behavior")

    # 7. Idempotency/safety statement (10 pts)
    has_idempotency = bool(_RE_IDEMPOTENCY.search(content))
    if has_idempotency:
        score += 10
    else:
        issues.append("no_idempotency_statement")

    # 8. Dependency declarations (10 pts)
    has_dependency_decl = bool(_RE_DEPENDENCY_DECL.search(content))
    if has_dependency_decl:
        score += 10
    else:
        issues.append("no_dependency_declarations")

    # 9. Namespace/prefix isolation (10 pts)
    has_namespace = bool(_RE_NAMESPACE_ISOLATION.search(content))
    if has_namespace:
        score += 10
    else:
        issues.append("no_namespace_isolation")

    # 10. Version/compat notes (10 pts)
    has_version_compat = bool(_RE_VERSION_COMPAT.search(content))
    if has_version_compat:
        score += 10
    else:
        issues.append("no_version_compat")

    return {
        "score": score,
        "issues": issues,
        "details": {
            "has_positive_scope": has_positive_scope,
            "has_negative_scope": has_negative_scope,
            "has_input_spec": has_input_spec,
            "has_output_spec": has_output_spec,
            "has_handoff": has_handoff,
            "has_error_behavior": has_error_behavior,
            "has_idempotency": has_idempotency,
            "has_dependency_decl": has_dependency_decl,
            "has_namespace": has_namespace,
            "has_version_compat": has_version_compat,
            "global_state_patterns": len(global_state_patterns) if global_state_patterns else 0,
        }
    }
