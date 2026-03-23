#!/bin/bash
##############################################################################
# SkillForge Binary Eval System
#
# Combines 6-dimension scoring (structure, triggers, efficiency, composability)
# with binary assertions (do the outputs pass validation?).
#
# Usage:
#   run-eval.sh <SKILL.md> <eval-suite.json> [--timeout SECONDS] [--runtime]
#
# Outputs JSON with composite results and appends to results log.
# Exit code: 0 if pass_rate improved, 1 if not.
##############################################################################

set -euo pipefail

# --- Cost tracking: capture start time ---
START_SECONDS=$SECONDS

# --- Temp directory for all mktemp files (cleaned up in trap) ---
TMPDIR_BASE=$(mktemp -d)

# --- Default config ---
TIMEOUT=300
RESULTS_LOG=""
RUNTIME_EVAL=0
RUNTIME_IF_AVAILABLE=1  # default ON: auto-enable runtime if claude CLI exists
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_MD=""
EVAL_SUITE=""

# --- Check required tools ---
for tool in jq python3; do
    if ! command -v "$tool" &>/dev/null; then
        echo "Error: required tool '$tool' not found in PATH" >&2
        exit 1
    fi
done

# --- Trap signal handlers ---
cleanup() {
    local exit_code=$?
    # Release counter lock if held
    rmdir "${LOCK_DIR:-/nonexistent}" 2>/dev/null || true
    if [[ -n "${SCORER_PID:-}" ]] && kill -0 "$SCORER_PID" 2>/dev/null; then
        kill -9 "$SCORER_PID" 2>/dev/null || true
    fi
    if [[ -n "${TEST_PID:-}" ]] && kill -0 "$TEST_PID" 2>/dev/null; then
        kill -9 "$TEST_PID" 2>/dev/null || true
    fi
    # Remove all temp files created during this run
    rm -rf "${TMPDIR_BASE:-/nonexistent}" 2>/dev/null || true
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
        --runtime)
            RUNTIME_EVAL=1
            shift
            ;;
        --no-runtime-auto)
            RUNTIME_IF_AVAILABLE=0
            shift
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
Usage: run-eval.sh <SKILL.md> <eval-suite.json> [--timeout SECONDS] [--log RESULTS_LOG] [--runtime] [--no-runtime-auto]

Arguments:
  SKILL_MD              Path to the skill SKILL.md to evaluate
  EVAL_SUITE            Path to eval-suite-*.json containing triggers and test cases
  --timeout SECONDS     Timeout for scoring and assertions (default: 300)
  --log LOGFILE         JSONL file to append results to (optional)
  --runtime             Force runtime evaluator (invoke claude -p for each test case)
  --no-runtime-auto     Disable auto-detection of claude CLI for runtime eval
USAGE
    exit 1
fi

# --- Validate inputs ---
if [[ ! -f "$SKILL_MD" ]]; then
    jq -n --arg path "$(basename "$SKILL_MD")" '{"error": "SKILL.md not found", "path": $path}'
    exit 1
fi

if [[ ! -f "$EVAL_SUITE" ]]; then
    jq -n --arg path "$(basename "$EVAL_SUITE")" '{"error": "eval-suite not found", "path": $path}'
    exit 1
fi

# Resolve to absolute paths to ensure consistent SKILL_DIR/FAILURES_DIR
SKILL_MD=$(cd "$(dirname "$SKILL_MD")" && echo "$(pwd)/$(basename "$SKILL_MD")")

# --- Extract skill name from SKILL.md ---
SKILL_NAME=$(grep "^name:" "$SKILL_MD" | head -1 | sed 's/^name:[[:space:]]*//' | sed 's/[[:space:]]*$//' || echo "unknown")
SKILL_DIR=$(dirname "$SKILL_MD")

# --- Generate experiment ID (sequential counter, atomic lock) ---
EXPERIMENT_DIR="${SKILL_DIR}/.skillforge-eval"
mkdir -p "$EXPERIMENT_DIR"
COUNTER_FILE="$EXPERIMENT_DIR/counter"
LOCK_DIR="$EXPERIMENT_DIR/.counter.lock"

# Acquire lock using mkdir (atomic on all POSIX systems including macOS)
_counter_retries=0
_total_retries=0
while ! mkdir "$LOCK_DIR" 2>/dev/null; do
    _counter_retries=$((_counter_retries + 1))
    _total_retries=$((_total_retries + 1))
    if [[ $_total_retries -gt 300 ]]; then
        echo "Error: could not acquire counter lock after 30s, proceeding without lock" >&2
        break
    fi
    if [[ $_counter_retries -gt 50 ]]; then
        echo "Warning: counter lock acquisition timed out, removing stale lock" >&2
        rmdir "$LOCK_DIR" 2>/dev/null || rm -rf "$LOCK_DIR"
        _counter_retries=0
    fi
    sleep 0.1
done

if [[ -f "$COUNTER_FILE" ]]; then
    RAW_COUNTER=$(cat "$COUNTER_FILE" 2>/dev/null || echo "0")
    if [[ "$RAW_COUNTER" =~ ^[0-9]+$ ]]; then
        EXPERIMENT_ID=$((RAW_COUNTER + 1))
    else
        echo "Warning: counter file contained non-numeric value, resetting to 1" >&2
        EXPERIMENT_ID=1
    fi
else
    EXPERIMENT_ID=1
fi
echo "$EXPERIMENT_ID" > "$COUNTER_FILE"

# Release lock immediately after write
rmdir "$LOCK_DIR" 2>/dev/null || true

# --- Run Python scorer (6 dimensions) ---
DIMENSION_SCORES="{}"
COMPOSITE_SCORE=0
SCORER_FAILED=0

echo "  Running Python scorer..." >&2
SCORE_OUTPUT=$(mktemp "$TMPDIR_BASE/score.XXXXXX")
# Use timeout if available (Linux), fall back to direct invocation (macOS)
TIMEOUT_CMD=""
if command -v timeout &>/dev/null; then
    TIMEOUT_CMD="timeout $TIMEOUT"
fi
$TIMEOUT_CMD python3 "$SCRIPT_DIR/score-skill.py" "$SKILL_MD" \
    --eval-suite "$EVAL_SUITE" --json > "$SCORE_OUTPUT" 2>&1 || {
    SCORER_FAILED=1
}

if [[ $SCORER_FAILED -eq 0 ]]; then
    DIMENSION_SCORES=$(jq -c '.dimensions' "$SCORE_OUTPUT")
    COMPOSITE_SCORE=$(jq -r '.composite_score' "$SCORE_OUTPUT")
fi
rm -f "$SCORE_OUTPUT"

# --- Assertion types that are runtime-only (skip in static check) ---
# These types are handled by runtime-evaluator.py, not the static bash loop.
RUNTIME_ONLY_TYPES="response_contains|response_matches|response_excludes"

# --- Run binary assertions (static checks against SKILL.md content) ---
BINARY_RESULTS="[]"
ASSERTIONS_PASSED=0
ASSERTIONS_TOTAL=0

if jq -e '.test_cases' "$EVAL_SUITE" > /dev/null 2>&1; then
    echo "  Running binary assertions..." >&2

    # Read skill content once (not per-assertion)
    SKILL_CONTENT=$(cat "$SKILL_MD" 2>/dev/null || echo "")

    BINARY_OUTPUT=$(mktemp "$TMPDIR_BASE/binary.XXXXXX")
    {
        ASSERTIONS_PASSED=0
        ASSERTIONS_TOTAL=0

        # Extract all assertions in one jq call as NUL-separated blocks
        # Each block: tc_id\ntype\nvalue\ndescription\n\0
        ASSERTIONS_FILE=$(mktemp "$TMPDIR_BASE/assertions.XXXXXX")
        jq -rj '.test_cases[]? | .id as $tc_id | (.assertions // [])[] |
            "\($tc_id)\n\(.type)\n\(.value)\n\(.description)\n\u0000"' "$EVAL_SUITE" > "$ASSERTIONS_FILE"

        # Collect results as JSONL lines (one per assertion), build array at end
        RESULTS_LINES=$(mktemp "$TMPDIR_BASE/results.XXXXXX")

        # Pre-resolve timeout command (once, not per-assertion)
        _GREP_TIMEOUT=""
        if command -v gtimeout &>/dev/null; then
            _GREP_TIMEOUT="gtimeout 2"
        elif command -v timeout &>/dev/null; then
            _GREP_TIMEOUT="timeout 2"
        fi

        while IFS= read -r -d '' assertion_block; do
            tc_id=$(printf '%s' "$assertion_block" | sed -n '1p')
            assertion_type=$(printf '%s' "$assertion_block" | sed -n '2p')
            assertion_value=$(printf '%s' "$assertion_block" | sed -n '3p')
            assertion_desc=$(printf '%s' "$assertion_block" | sed -n '4p')
            # Skip runtime-only assertion types in static check
            if echo "$assertion_type" | grep -qE "^($RUNTIME_ONLY_TYPES)$"; then
                continue
            fi

            ASSERTIONS_TOTAL=$((ASSERTIONS_TOTAL + 1))

            # Evaluate assertion against skill content (static check)
            assertion_passed="false"

            case "$assertion_type" in
                contains)
                    if echo "$SKILL_CONTENT" | grep -qiF -- "$assertion_value" 2>/dev/null; then
                        assertion_passed="true"
                    fi
                    ;;
                excludes)
                    if ! echo "$SKILL_CONTENT" | grep -qiF -- "$assertion_value" 2>/dev/null; then
                        assertion_passed="true"
                    fi
                    ;;
                pattern)
                    # Validate regex complexity before execution (ReDoS prevention)
                    if ! PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}" python3 -c "
from shared import validate_regex_complexity
import sys
ok, reason = validate_regex_complexity(sys.argv[1])
if not ok: sys.exit(1)
" "$assertion_value" 2>/dev/null; then
                        echo "  Warning: skipping unsafe regex in $tc_id" >&2
                        assertion_passed="false"
                    else
                        # Regex passed complexity check — execute with timeout guard
                        if echo "$SKILL_CONTENT" | $_GREP_TIMEOUT grep -qiE -- "$assertion_value" 2>/dev/null; then
                            assertion_passed="true"
                        fi
                    fi
                    ;;
                *)
                    # Unknown assertion type — warn and skip
                    echo "  Warning: unknown assertion type '$assertion_type' in test case '$tc_id', skipping" >&2
                    continue
                    ;;
            esac

            if [[ "$assertion_passed" == "true" ]]; then
                ASSERTIONS_PASSED=$((ASSERTIONS_PASSED + 1))
            fi

            # Append result as JSONL line (using jq for correct JSON escaping)
            jq -n -c --arg tc "$tc_id" --arg type "$assertion_type" \
                --arg desc "$assertion_desc" --argjson passed "$assertion_passed" \
                '{"test_case":$tc,"type":$type,"description":$desc,"passed":$passed}' >> "$RESULTS_LINES"
        done < "$ASSERTIONS_FILE"

        # Build the JSON array from collected JSONL results
        if [[ -s "$RESULTS_LINES" ]]; then
            jq -s '.' "$RESULTS_LINES"
        else
            echo "[]"
        fi

        rm -f "$ASSERTIONS_FILE" "$RESULTS_LINES"
    } > "$BINARY_OUTPUT"

    BINARY_RESULTS=$(cat "$BINARY_OUTPUT")
    ASSERTIONS_PASSED=$(echo "$BINARY_RESULTS" | jq '[.[] | select(.passed == true)] | length')
    ASSERTIONS_TOTAL=$(echo "$BINARY_RESULTS" | jq 'length')

    rm -f "$BINARY_OUTPUT"
fi

# --- Auto-enable runtime eval if claude CLI is available ---
if [[ $RUNTIME_EVAL -eq 0 ]] && [[ $RUNTIME_IF_AVAILABLE -eq 1 ]]; then
    if command -v claude &>/dev/null; then
        echo "  Runtime eval auto-enabled (claude CLI found). Use --no-runtime-auto to disable." >&2
        RUNTIME_EVAL=1
    fi
fi

# --- Run runtime evaluator ---
RUNTIME_RESULTS="{}"
if [[ $RUNTIME_EVAL -eq 1 ]]; then
    echo "  Running runtime evaluator..." >&2
    RUNTIME_OUTPUT=$(mktemp "$TMPDIR_BASE/runtime.XXXXXX")
    if python3 "$SCRIPT_DIR/runtime-evaluator.py" "$EVAL_SUITE" \
        --skill-path "$SKILL_MD" --timeout "$TIMEOUT" --json > "$RUNTIME_OUTPUT" 2>/dev/null; then
        RUNTIME_RESULTS=$(cat "$RUNTIME_OUTPUT")
        # Merge runtime assertions into totals
        RT_PASSED=$(echo "$RUNTIME_RESULTS" | jq -r '.assertions_passed // 0')
        RT_TOTAL=$(echo "$RUNTIME_RESULTS" | jq -r '.assertions_total // 0')
        ASSERTIONS_PASSED=$((ASSERTIONS_PASSED + RT_PASSED))
        ASSERTIONS_TOTAL=$((ASSERTIONS_TOTAL + RT_TOTAL))
    else
        RUNTIME_RESULTS='{"error": "runtime evaluator failed", "skipped": true}'
        echo "  Runtime evaluator failed (non-fatal)" >&2
    fi
    rm -f "$RUNTIME_OUTPUT"
fi

# --- Calculate pass rate ---
PASS_RATE=0
if [[ $ASSERTIONS_TOTAL -gt 0 ]]; then
    PASS_RATE=$((ASSERTIONS_PASSED * 100 / ASSERTIONS_TOTAL))
fi

# --- Check previous pass rate (for exit code determination) ---
PREVIOUS_PASS_RATE=0
if [[ -n "$RESULTS_LOG" ]] && [[ -f "$RESULTS_LOG" ]]; then
    # pass_rate stored as "N/M" (v5) or integer (v4 legacy) — handle both
    _prev_pr_raw=$(tail -1 "$RESULTS_LOG" | jq -r '.pass_rate // "0/1"' 2>/dev/null || echo "0/1")
    if [[ "$_prev_pr_raw" == */* ]]; then
        _prev_passed="${_prev_pr_raw%%/*}"
        _prev_total="${_prev_pr_raw##*/}"
        if [[ "$_prev_total" =~ ^[0-9]+$ ]] && [[ "$_prev_total" -gt 0 ]] && [[ "$_prev_passed" =~ ^[0-9]+$ ]]; then
            PREVIOUS_PASS_RATE=$((_prev_passed * 100 / _prev_total))
        else
            PREVIOUS_PASS_RATE=0
        fi
    elif [[ "$_prev_pr_raw" =~ ^[0-9]+$ ]]; then
        # Legacy integer percentage from v4
        PREVIOUS_PASS_RATE="$_prev_pr_raw"
    else
        PREVIOUS_PASS_RATE=0
    fi
fi

# --- Build JSON output ---
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
SKILL_BASENAME=$(basename "$SKILL_MD")
RESULT_JSON=$(jq -n \
    --arg skill_name "$SKILL_NAME" \
    --arg skill_path "$SKILL_BASENAME" \
    --argjson experiment_id "$EXPERIMENT_ID" \
    --arg timestamp "$TIMESTAMP" \
    --argjson pass_rate "$PASS_RATE" \
    --argjson assertions_passed "$ASSERTIONS_PASSED" \
    --argjson assertions_total "$ASSERTIONS_TOTAL" \
    --argjson composite_score "$COMPOSITE_SCORE" \
    --argjson dimension_scores "$DIMENSION_SCORES" \
    --argjson binary_results "$BINARY_RESULTS" \
    --argjson runtime_results "$RUNTIME_RESULTS" \
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
        "binary_results": $binary_results,
        "runtime_results": $runtime_results
    }')

# --- Emit calibration data to meta-learning store ---
META_DIR="${HOME}/.skillforge/meta"
mkdir -p "$META_DIR"

# Cap calibration log at 10MB
_CAL_LOG="${META_DIR}/calibration-log.jsonl"
if [ -f "$_CAL_LOG" ] && [ "$(wc -c < "$_CAL_LOG" 2>/dev/null || echo 0)" -gt 10485760 ]; then
    tail -n 500 "$_CAL_LOG" > "${_CAL_LOG}.tmp" && mv "${_CAL_LOG}.tmp" "$_CAL_LOG"
fi

# Calibration log: static scores + runtime pass rate (when runtime was used)
if [[ $RUNTIME_EVAL -eq 1 ]] && [[ "$RUNTIME_RESULTS" != "{}" ]]; then
    RT_PASSED_META=$(echo "$RUNTIME_RESULTS" | jq -r '.assertions_passed // 0')
    RT_TOTAL_META=$(echo "$RUNTIME_RESULTS" | jq -r '.assertions_total // 0')
    RT_PASS_RATE_META=0
    if [[ $RT_TOTAL_META -gt 0 ]]; then
        RT_PASS_RATE_META=$((RT_PASSED_META * 100 / RT_TOTAL_META))
    fi
    jq -n -c \
        --arg skill "$SKILL_NAME" \
        --arg timestamp "$TIMESTAMP" \
        --argjson static_scores "$DIMENSION_SCORES" \
        --argjson runtime_pass_rate "$RT_PASS_RATE_META" \
        --arg weights_used "${WEIGHTS_USED:-default}" \
        '{
            "skill": $skill,
            "timestamp": $timestamp,
            "static_scores": $static_scores,
            "runtime_pass_rate": $runtime_pass_rate,
            "weights_used": $weights_used
        }' >> "$META_DIR/calibration-log.jsonl"
fi

# --- Log assertion failures to .skillforge/failures.jsonl ---
FAILURES_DIR="${SKILL_DIR}/.skillforge"
FAILURES_FILE="$FAILURES_DIR/failures.jsonl"
if [[ "$BINARY_RESULTS" != "[]" ]]; then
    FAILED_ASSERTIONS=$(echo "$BINARY_RESULTS" | jq -c '[.[] | select(.passed == false)]')
    FAILED_COUNT=$(echo "$FAILED_ASSERTIONS" | jq 'length')
    if [[ $FAILED_COUNT -gt 0 ]]; then
        mkdir -p "$FAILURES_DIR"
        echo "$FAILED_ASSERTIONS" | jq -c \
            --arg ts "$TIMESTAMP" \
            --arg skill "$SKILL_NAME" \
            '.[] | {
                timestamp: $ts,
                skill: $skill,
                failure_type: "assertion_failed",
                assertion_id: (.test_case + ":" + .type + ":" + (.description // "")),
                confidence: 0.9
            }' >> "$FAILURES_FILE"

        # Rotate if > 1MB
        if [[ -f "$FAILURES_FILE" ]] && [[ $(wc -c < "$FAILURES_FILE" | tr -d ' ') -gt 1000000 ]]; then
            mv "$FAILURES_FILE" "${FAILURES_FILE}.archive.$(date +%s)"
        fi
    fi
fi

# --- Append to results log if specified ---
# Schema aligned with progress.py expectations
if [[ -n "$RESULTS_LOG" ]]; then
    mkdir -p "$(dirname "$RESULTS_LOG")"

    # Cost tracking: compute real duration, tokens, delta, status
    COMMIT_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    DURATION_MS=$(( (SECONDS - START_SECONDS) * 1000 ))
    WORD_COUNT=$(wc -w < "$SKILL_MD" | tr -d ' ')
    TOKENS_EST=$((WORD_COUNT * 13 / 10))

    # Compute delta and status from previous entry
    LOG_STATUS="baseline"
    LOG_DELTA=0
    if [[ -f "$RESULTS_LOG" ]] && [[ -s "$RESULTS_LOG" ]]; then
        PREV_COMPOSITE=$(tail -1 "$RESULTS_LOG" | jq -r '.composite // 0' 2>/dev/null || echo "0")
        _ARITH_RESULT=$(python3 -c "
import sys
a, b = float(sys.argv[1]), float(sys.argv[2])
delta = round(a - b, 1)
verdict = 'keep' if a > b else 'discard'
print(f'{delta}:{verdict}')
" "$COMPOSITE_SCORE" "$PREV_COMPOSITE" 2>/dev/null || echo "0.0:discard")
        LOG_DELTA="${_ARITH_RESULT%%:*}"
        _VERDICT="${_ARITH_RESULT##*:}"
        if [[ "$_VERDICT" == "keep" ]]; then
            LOG_STATUS="keep"
        else
            LOG_STATUS="discard"
        fi
    fi

    # JSONL format compatible with progress.py ProgressAnalyzer
    jq -n -c \
        --argjson exp "$EXPERIMENT_ID" \
        --arg timestamp "$TIMESTAMP" \
        --arg commit "$COMMIT_HASH" \
        --argjson scores "$DIMENSION_SCORES" \
        --arg pass_rate "${ASSERTIONS_PASSED}/${ASSERTIONS_TOTAL}" \
        --argjson composite "$COMPOSITE_SCORE" \
        --argjson delta "$LOG_DELTA" \
        --arg status "$LOG_STATUS" \
        --arg description "" \
        --argjson duration_ms "$DURATION_MS" \
        --argjson tokens_estimated "$TOKENS_EST" \
        '{
            "exp": $exp,
            "timestamp": $timestamp,
            "commit": $commit,
            "scores": $scores,
            "pass_rate": $pass_rate,
            "composite": $composite,
            "delta": $delta,
            "status": $status,
            "strategy_type": null,
            "description": $description,
            "duration_ms": $duration_ms,
            "tokens_estimated": $tokens_estimated
        }' >> "$RESULTS_LOG"
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
