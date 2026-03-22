#!/usr/bin/env python3
"""SkillForge — Runtime Evaluator

Actually invoke Claude with test prompts and evaluate the response.
This is the missing piece: scoring measures file patterns, not runtime behavior.
The runtime evaluator bridges that gap.

Usage:
    python runtime-evaluator.py <eval-suite.json> --skill-path SKILL.md [--timeout 30] [--json]

Requires `claude` CLI to be available. Exits with code 1 and a clear message
if not found.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from shared import regex_search_safe


def check_claude_cli() -> bool:
    """Check if claude CLI is available."""
    return shutil.which("claude") is not None


def invoke_claude(prompt: str, skill_context: str, timeout: int = 30) -> dict:
    """Invoke claude -p with a prompt and skill context.

    Returns dict with 'response' (str) and 'error' (str or None).
    """
    full_prompt = (
        f"You are operating with the following skill context:\n\n"
        f"{skill_context}\n\n"
        f"---\n\n"
        f"User request: {prompt}"
    )

    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "json", full_prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            return {"response": "", "error": f"claude exited with code {result.returncode}: {result.stderr.strip()}"}

        # Parse JSON output from claude
        try:
            output = json.loads(result.stdout)
            # claude --output-format json returns {"result": "..."} or similar
            response_text = output.get("result", output.get("text", result.stdout))
            if isinstance(response_text, dict):
                response_text = json.dumps(response_text)
            return {"response": str(response_text), "error": None}
        except json.JSONDecodeError:
            # Fallback: treat stdout as plain text
            return {"response": result.stdout.strip(), "error": None}

    except subprocess.TimeoutExpired:
        return {"response": "", "error": f"claude timed out after {timeout}s"}
    except FileNotFoundError:
        return {"response": "", "error": "claude CLI not found"}


def check_assertion(response: str, assertion: dict) -> dict:
    """Check a single assertion against a claude response.

    Supports assertion types:
    - response_contains: response includes the value (case-insensitive)
    - response_matches: response matches regex pattern
    - response_excludes: response does NOT include the value
    - contains: alias for response_contains (backward compat with static assertions)
    - pattern: alias for response_matches
    - excludes: alias for response_excludes
    """
    a_type = assertion.get("type", "")
    a_value = assertion.get("value", "")
    description = assertion.get("description", "")
    response_lower = response.lower()

    passed = False

    if a_type in ("response_contains", "contains"):
        passed = a_value.lower() in response_lower

    elif a_type in ("response_matches", "pattern"):
        try:
            passed = regex_search_safe(a_value, response)
        except (re.error, TimeoutError) as e:
            return {
                "type": a_type,
                "value": a_value,
                "description": description,
                "passed": False,
                "error": f"regex error: {e}",
            }

    elif a_type in ("response_excludes", "excludes"):
        passed = a_value.lower() not in response_lower

    else:
        # Unknown assertion type — fail-safe, do not auto-pass
        print(f"Warning: unknown assertion type '{a_type}', marking as skipped (not passed)", file=sys.stderr)
        return {
            "type": a_type,
            "value": a_value,
            "description": description,
            "passed": False,
            "skipped": True,
            "reason": f"unknown assertion type: {a_type}",
        }

    return {
        "type": a_type,
        "value": a_value,
        "description": description,
        "passed": passed,
    }


def run_runtime_assertions(
    test_suite: dict,
    skill_path: str,
    timeout: int = 30,
) -> dict:
    """Run runtime assertions: invoke claude for each test case, check responses.

    Returns a result dict compatible with run-eval.sh JSON schema.
    """
    skill_content = Path(skill_path).read_text(encoding="utf-8", errors="replace")
    test_cases = test_suite.get("test_cases", [])

    results = []
    total_assertions = 0
    passed_assertions = 0

    for tc in test_cases:
        tc_id = tc.get("id", "unknown")
        prompt = tc.get("prompt", "")
        assertions = tc.get("assertions", [])

        # Filter to runtime-compatible assertions
        runtime_types = {
            "response_contains", "response_matches", "response_excludes",
            "contains", "pattern", "excludes",
        }
        applicable = [a for a in assertions if a.get("type") in runtime_types]

        if not applicable:
            continue

        # Invoke claude
        invoke_result = invoke_claude(prompt, skill_content, timeout=timeout)

        tc_result: dict[str, Any] = {
            "test_case": tc_id,
            "prompt": prompt[:80],
            "assertions": [],
        }

        if invoke_result["error"]:
            tc_result["error"] = invoke_result["error"]
            # Mark all assertions as failed due to invocation error
            for a in applicable:
                total_assertions += 1
                tc_result["assertions"].append({
                    "type": a.get("type"),
                    "description": a.get("description", ""),
                    "passed": False,
                    "error": invoke_result["error"],
                })
        else:
            response = invoke_result["response"]
            tc_result["response_length"] = len(response)

            for a in applicable:
                total_assertions += 1
                a_result = check_assertion(response, a)
                if a_result["passed"]:
                    passed_assertions += 1
                tc_result["assertions"].append(a_result)

        results.append(tc_result)

    pass_rate = int((passed_assertions / total_assertions) * 100) if total_assertions > 0 else 0

    return {
        "runtime_eval": True,
        "test_cases_run": len(results),
        "assertions_passed": passed_assertions,
        "assertions_total": total_assertions,
        "pass_rate": pass_rate,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="SkillForge Runtime Evaluator")
    parser.add_argument("eval_suite", help="Path to eval-suite.json")
    parser.add_argument("--skill-path", required=True, help="Path to SKILL.md")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout per invocation (seconds)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    # Check claude CLI availability
    if not check_claude_cli():
        print(json.dumps({"error": "claude CLI not found. Install it: https://docs.anthropic.com/en/docs/claude-code"}), file=sys.stderr)
        sys.exit(1)

    # Load test suite
    suite_path = Path(args.eval_suite)
    if not suite_path.exists():
        print(json.dumps({"error": f"eval suite not found: {args.eval_suite}"}), file=sys.stderr)
        sys.exit(1)

    test_suite = json.loads(suite_path.read_text())

    # Validate skill path
    if not Path(args.skill_path).exists():
        print(json.dumps({"error": f"skill file not found: {args.skill_path}"}), file=sys.stderr)
        sys.exit(1)

    # Run runtime assertions
    result = run_runtime_assertions(test_suite, args.skill_path, timeout=args.timeout)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\nRuntime Eval: {result['pass_rate']}% ({result['assertions_passed']}/{result['assertions_total']})")
        for tc in result["results"]:
            status = "PASS" if all(a["passed"] for a in tc["assertions"]) else "FAIL"
            print(f"  [{status}] {tc['test_case']}: {tc.get('prompt', '')[:60]}")
            if tc.get("error"):
                print(f"         Error: {tc['error']}")


if __name__ == "__main__":
    main()
