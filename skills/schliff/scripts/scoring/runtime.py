"""Score runtime effectiveness by invoking Claude with test prompts.

Opt-in dimension — returns -1 (skip) unless explicitly enabled.
Requires `claude` CLI to be available. Returns score -1 if unavailable
(graceful degradation — dimension is skipped in composite).

Runs up to 3 test cases from eval suite, checks response_* assertions.
"""
import re
import subprocess
from typing import Optional

from shared import regex_search_safe as _regex_search_safe, read_skill_safe


def score_runtime(skill_path: str, eval_suite: Optional[dict] = None,
                   enabled: bool = False) -> dict:
    """Score runtime effectiveness by invoking Claude with test prompts.

    Opt-in dimension — returns -1 (skip) unless explicitly enabled.
    Requires `claude` CLI to be available. Returns score -1 if unavailable
    (graceful degradation — dimension is skipped in composite).

    Runs up to 3 test cases from eval suite, checks response_* assertions.

    Args:
        enabled: Must be True to actually run (default: False -> returns -1)
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
        content = read_skill_safe(skill_path)
    except (FileNotFoundError, ValueError):
        return {"score": -1, "issues": ["file_not_found"], "details": {}}

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
