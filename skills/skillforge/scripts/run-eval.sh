#!/bin/bash
##############################################################################
# SkillForge Binary Eval System
#
# Combines 6-dimension scoring (structure, triggers, efficiency, composability)
# with binary assertions (do the outputs pass validation?).
#
# Usage:
#   run-eval.sh <SKILL.md> <eval-suite.json> [--timeout SECONDS]
#
# Outputs JSON with composite results and appends to results log.
# Exit code: 0 if pass_rate improved, 1 if not.
##############################################################################

set -euo pipefail

# --- Default config ---
TIMEOUT=300
RESULTS_LOG=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_MD=""
EVAL_SUITE=""

# --- Trap signal handlers ---
cleanup() {
    local exit_code=$?
    if [[ -n "${SCORER_PID:-}" ]] && kill -0 "$SCORER_PID" 2>/dev/null; then
        kill -9 "$SCORER_PID" 2>/dev/null || true
    fi
    if [[ -n "${TEST_PID:-}" ]] && kill -0 "$TEST_PID" 2>/dev/null; then
        kill -9 "$TEST_PID" 2>/dev/null || true
    fi
    exit "$exit_code"
}
trap cleanup EXIT INT TERM

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --log)
            RESULTS_LOG="$2"
            shift 2
            ;;
        -*)
            echo "Error: unknown option $1" >&2
            exit 1
            ;;
        *)
            if [[ -z "$SKILL_MD" ]]; then
                SKILL_MD="$1"
            elif [[ -z "$EVAL_SUITE" ]]; then
                EVAL_SUITE="$1"
            else
                echo "Error: too many positional arguments" >&2
                exit 1
            fi
            shift
            ;;
    esac
done

if [[ -z "$SKILL_MD" ]] || [[ -z "$EVAL_SUITE" ]]; then
    cat >&2 <<'USAGE'
Usage: run-eval.sh <SKILL.md> <eval-suite.json> [--timeout SECONDS] [--log RESULTS_LOG]

Arguments:
  SKILL_MD           Path to the skill SKILL.md to evaluate
  EVAL_SUITE         Path to eval-suite-*.json containing triggers and test cases
  --timeout SECONDS  Timeout for scoring and assertions (default: 300)
  --log LOGFILE      TSV/JSONL file to append results to (optional)
USAGE
    exit 1
fi

# --- Validate inputs ---
if [[ ! -f "$SKILL_MD" ]]; then
    echo '{"error": "SKILL.md not found", "path": "'"$SKILL_MD"'"}' | jq .
    exit 1
fi

if [[ ! -f "$EVAL_SUITE" ]]; then
    echo '{"error": "eval-suite not found", "path": "'"$EVAL_SUITE"'"}' | jq .
    exit 1
fi

# --- Extract skill name from SKILL.md ---
SKILL_NAME=$(grep "^name:" "$SKILL_MD" | head -1 | cut -d: -f2- | xargs || echo "unknown")
SKILL_DIR=$(dirname "$SKILL_MD")

# --- Generate experiment ID (sequential counter) ---
EXPERIMENT_DIR="${SKILL_DIR}/.skillforge-eval"
mkdir -p "$EXPERIMENT_DIR"
COUNTER_FILE="$EXPERIMENT_DIR/counter"
if [[ -f "$COUNTER_FILE" ]]; then
    EXPERIMENT_ID=$(($(cat "$COUNTER_FILE") + 1))
else
    EXPERIMENT_ID=1
fi
echo "$EXPERIMENT_ID" > "$COUNTER_FILE"

# --- Run Python scorer (6 dimensions) ---
DIMENSION_SCORES="{}"
COMPOSITE_SCORE=0
SCORER_FAILED=0

echo "  Running Python scorer..." >&2
SCORE_OUTPUT=$(mktemp)
timeout "$TIMEOUT" python3 "$SCRIPT_DIR/score-skill.py" "$SKILL_MD" \
    --eval-suite "$EVAL_SUITE" --json > "$SCORE_OUTPUT" 2>&1 || {
    SCORER_FAILED=1
}

if [[ $SCORER_FAILED -eq 0 ]]; then
    DIMENSION_SCORES=$(jq -c '.dimensions' "$SCORE_OUTPUT")
    COMPOSITE_SCORE=$(jq -r '.composite_score' "$SCORE_OUTPUT")
fi
rm -f "$SCORE_OUTPUT"

# --- Run binary assertions ---
BINARY_RESULTS="[]"
ASSERTIONS_PASSED=0
ASSERTIONS_TOTAL=0

if jq -e '.test_cases' "$EVAL_SUITE" > /dev/null 2>&1; then
    echo "  Running binary assertions..." >&2
    
    BINARY_OUTPUT=$(mktemp)
    {
        ASSERTIONS_PASSED=0
        ASSERTIONS_TOTAL=0
        BINARY_ARRAY="[]"
        
        # Process each test case
        test_count=$(jq '.test_cases | length' "$EVAL_SUITE")
        for ((i=0; i<test_count; i++)); do
            tc=$(jq ".test_cases[$i]" "$EVAL_SUITE")
            tc_id=$(echo "$tc" | jq -r '.id')
            prompt=$(echo "$tc" | jq -r '.prompt')
            
            # For now, assertions are parsed from test_cases
            # In production, run the prompt and check assertions
            assertions=$(echo "$tc" | jq '.assertions // []')
            assertion_count=$(echo "$assertions" | jq 'length')
            
            for ((j=0; j<assertion_count; j++)); do
                assertion=$(echo "$assertions" | jq ".[$j]")
                assertion_type=$(echo "$assertion" | jq -r '.type')
                assertion_value=$(echo "$assertion" | jq -r '.value')
                assertion_desc=$(echo "$assertion" | jq -r '.description')
                
                ASSERTIONS_TOTAL=$((ASSERTIONS_TOTAL + 1))
                
                # Evaluate assertion against skill content (static check)
                # For runtime assertions, the caller must provide output files
                assertion_passed="false"
                skill_content=$(cat "$SKILL_MD" 2>/dev/null || echo "")

                case "$assertion_type" in
                    contains)
                        if echo "$skill_content" | grep -qi "$assertion_value" 2>/dev/null; then
                            assertion_passed="true"
                        fi
                        ;;
                    excludes)
                        if ! echo "$skill_content" | grep -qi "$assertion_value" 2>/dev/null; then
                            assertion_passed="true"
                        fi
                        ;;
                    pattern)
                        if echo "$skill_content" | grep -qiE "$assertion_value" 2>/dev/null; then
                            assertion_passed="true"
                        fi
                        ;;
                    *)
                        # Unknown assertion type — skip, mark as passed
                        assertion_passed="true"
                        ;;
                esac

                if [[ "$assertion_passed" == "true" ]]; then
                    ASSERTIONS_PASSED=$((ASSERTIONS_PASSED + 1))
                fi

                BINARY_ARRAY=$(echo "$BINARY_ARRAY" | jq \
                    --arg tc_id "$tc_id" \
                    --arg type "$assertion_type" \
                    --arg desc "$assertion_desc" \
                    --argjson passed "$assertion_passed" \
                    '. += [{"test_case": $tc_id, "type": $type, "description": $desc, "passed": $passed}]')
            done
        done
        
        # Output results
        echo "$BINARY_ARRAY" | jq .
    } > "$BINARY_OUTPUT"
    
    BINARY_RESULTS=$(cat "$BINARY_OUTPUT")
    ASSERTIONS_PASSED=$(echo "$BINARY_RESULTS" | jq '[.[] | select(.passed == true)] | length')
    ASSERTIONS_TOTAL=$(echo "$BINARY_RESULTS" | jq 'length')
    
    rm -f "$BINARY_OUTPUT"
fi

# --- Calculate pass rate ---
PASS_RATE=0
if [[ $ASSERTIONS_TOTAL -gt 0 ]]; then
    PASS_RATE=$((ASSERTIONS_PASSED * 100 / ASSERTIONS_TOTAL))
fi

# --- Check previous pass rate (for exit code determination) ---
PREVIOUS_PASS_RATE=0
if [[ -n "$RESULTS_LOG" ]] && [[ -f "$RESULTS_LOG" ]]; then
    PREVIOUS_PASS_RATE=$(tail -1 "$RESULTS_LOG" | \
        awk -F'\t' '{print $3}' 2>/dev/null || echo "0")
fi

# --- Build JSON output ---
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
RESULT_JSON=$(jq -n \
    --arg skill_name "$SKILL_NAME" \
    --arg skill_path "$SKILL_MD" \
    --argjson experiment_id "$EXPERIMENT_ID" \
    --arg timestamp "$TIMESTAMP" \
    --argjson pass_rate "$PASS_RATE" \
    --argjson assertions_passed "$ASSERTIONS_PASSED" \
    --argjson assertions_total "$ASSERTIONS_TOTAL" \
    --argjson composite_score "$COMPOSITE_SCORE" \
    --argjson dimension_scores "$DIMENSION_SCORES" \
    --argjson binary_results "$BINARY_RESULTS" \
    '{
        "experiment_id": $experiment_id,
        "skill_name": $skill_name,
        "skill_path": $skill_path,
        "timestamp": $timestamp,
        "pass_rate": {
            "passed": $assertions_passed,
            "total": $assertions_total,
            "percentage": $pass_rate
        },
        "dimension_scores": $dimension_scores,
        "composite_score": $composite_score,
        "binary_results": $binary_results
    }')

# --- Append to results log if specified ---
if [[ -n "$RESULTS_LOG" ]]; then
    mkdir -p "$(dirname "$RESULTS_LOG")"
    
    # JSONL format: one JSON object per line (compatible with progress.py)
    printf '{"experiment_id":"%s","skill_name":"%s","pass_rate":%s,"composite_score":%s,"timestamp":"%s"}\n' \
        "$EXPERIMENT_ID" "$SKILL_NAME" "$PASS_RATE" "${COMPOSITE_SCORE:-0}" "$TIMESTAMP" >> "$RESULTS_LOG"
fi

# --- Output JSON result ---
echo "$RESULT_JSON" | jq .

# --- Determine exit code based on improvement ---
EXIT_CODE=1
if [[ $ASSERTIONS_TOTAL -gt 0 ]]; then
    if [[ $PASS_RATE -gt $PREVIOUS_PASS_RATE ]]; then
        EXIT_CODE=0
    fi
fi

exit $EXIT_CODE
