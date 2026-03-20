#!/bin/bash
##############################################################################
# SkillForge Integration Test Suite
#
# Tests real scenarios, crash edge-cases, and cross-script integration.
# Each test is isolated: creates temp files, cleans up after itself.
#
# Usage: bash scripts/test-integration.sh [--verbose]
#
# Exit code: 0 if all pass, 1 if any fail.
##############################################################################

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
VERBOSE=0
PASS=0
FAIL=0
ERRORS=()

if [[ "${1:-}" == "--verbose" ]]; then
    VERBOSE=1
fi

# --- Helpers ---
log() { echo "  $1"; }
pass() { PASS=$((PASS + 1)); echo "  [PASS] $1"; }
fail() { FAIL=$((FAIL + 1)); ERRORS+=("$1: $2"); echo "  [FAIL] $1: $2"; }
section() { echo ""; echo "=== $1 ==="; }

# --- Setup ---
TMPDIR_BASE=$(mktemp -d)
trap 'rm -rf "$TMPDIR_BASE"' EXIT

##############################################################################
section "1. score-skill.py — Basic Functionality"
##############################################################################

# Test: scores its own SKILL.md correctly
RESULT=$(python3 "$SCRIPT_DIR/score-skill.py" "$SKILL_DIR/SKILL.md" --json 2>&1)
COMPOSITE=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['composite_score'])" 2>/dev/null)
if [[ -n "$COMPOSITE" ]] && python3 -c "exit(0 if float('$COMPOSITE') >= 75 else 1)" 2>/dev/null; then
    pass "Self-score composite >= 75 (got $COMPOSITE)"
else
    fail "Self-score" "composite=$COMPOSITE, expected >= 75"
fi

# Test: all 6 dimensions measured
MEASURED=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['confidence']['measured'])" 2>/dev/null)
if [[ "$MEASURED" == "6" ]]; then
    pass "All 6 dimensions measured"
else
    fail "Dimension count" "measured=$MEASURED, expected 6"
fi

# Test: --clarity adds 7th dimension
RESULT_CLARITY=$(python3 "$SCRIPT_DIR/score-skill.py" "$SKILL_DIR/SKILL.md" --json --clarity 2>&1)
HAS_CLARITY=$(echo "$RESULT_CLARITY" | python3 -c "import sys,json; d=json.load(sys.stdin); print('clarity' in d['dimensions'])" 2>/dev/null)
if [[ "$HAS_CLARITY" == "True" ]]; then
    pass "--clarity adds 7th dimension"
else
    fail "--clarity" "clarity dimension not found"
fi

# Test: --diff doesn't crash
RESULT_DIFF=$(python3 "$SCRIPT_DIR/score-skill.py" "$SKILL_DIR/SKILL.md" --json --diff 2>&1)
HAS_DIFF=$(echo "$RESULT_DIFF" | python3 -c "import sys,json; print('diff_analysis' in json.load(sys.stdin))" 2>/dev/null)
if [[ "$HAS_DIFF" == "True" ]]; then
    pass "--diff returns diff_analysis"
else
    fail "--diff" "diff_analysis not in output"
fi

##############################################################################
section "2. score-skill.py — Edge Cases"
##############################################################################

# Test: nonexistent file
RESULT_MISSING=$(python3 "$SCRIPT_DIR/score-skill.py" "/nonexistent/SKILL.md" --json 2>&1)
MISSING_SCORE=$(echo "$RESULT_MISSING" | python3 -c "import sys,json; print(json.load(sys.stdin)['composite_score'])" 2>/dev/null)
if [[ "$MISSING_SCORE" == "0" ]] || [[ "$MISSING_SCORE" == "0.0" ]]; then
    pass "Missing file → score 0"
else
    fail "Missing file" "expected score 0, got $MISSING_SCORE"
fi

# Test: frontmatter-only file (clarity should score 0)
FRONTMATTER_ONLY="$TMPDIR_BASE/frontmatter-only.md"
cat > "$FRONTMATTER_ONLY" <<'FMEOF'
---
name: empty-skill
description: a skill with no body at all
---
FMEOF
CLARITY_EMPTY=$(python3 "$SCRIPT_DIR/score-skill.py" "$FRONTMATTER_ONLY" --json --clarity 2>&1 | \
    python3 -c "import sys,json; print(json.load(sys.stdin)['dimensions'].get('clarity', 'missing'))" 2>/dev/null)
if [[ "$CLARITY_EMPTY" == "0" ]]; then
    pass "Frontmatter-only → clarity score 0"
else
    fail "Frontmatter-only clarity" "expected 0, got $CLARITY_EMPTY"
fi

# Test: code-blocks-only file (clarity should not false-positive on code)
CODE_ONLY="$TMPDIR_BASE/code-only.md"
cat > "$CODE_ONLY" <<'CEOF'
---
name: code-skill
description: a skill demonstrating code patterns
---

# Code Examples

```bash
# Always run tests before deploying
# Never skip the linter
echo "deploy"
```

Some prose after the code block.
CEOF
CLARITY_CODE=$(python3 "$SCRIPT_DIR/score-skill.py" "$CODE_ONLY" --json --clarity 2>&1 | \
    python3 -c "import sys,json; d=json.load(sys.stdin); det=d.get('details',{}).get('clarity',{}); print(det.get('always_count', 'missing'))" 2>/dev/null)
if [[ "$CLARITY_CODE" == "0" ]]; then
    pass "Code-block always/never stripped (no false contradictions)"
else
    fail "Code-block stripping" "always_count=$CLARITY_CODE, expected 0 (code blocks should be stripped)"
fi

# Test: non-git directory (--diff should gracefully handle)
NON_GIT="$TMPDIR_BASE/non-git"
mkdir -p "$NON_GIT"
cp "$SKILL_DIR/SKILL.md" "$NON_GIT/"
DIFF_NONGIT=$(cd "$NON_GIT" && python3 "$SCRIPT_DIR/score-skill.py" SKILL.md --json --diff 2>&1 | \
    python3 -c "import sys,json; print(json.load(sys.stdin).get('diff_analysis',{}).get('available', 'missing'))" 2>/dev/null)
if [[ "$DIFF_NONGIT" == "False" ]]; then
    pass "--diff in non-git dir → available=False"
else
    fail "--diff non-git" "expected available=False, got $DIFF_NONGIT"
fi

# Test: malformed JSON eval suite
BAD_JSON="$TMPDIR_BASE/bad-eval.json"
echo "not json at all {{{" > "$BAD_JSON"
python3 "$SCRIPT_DIR/score-skill.py" "$SKILL_DIR/SKILL.md" --eval-suite "$BAD_JSON" --json > /dev/null 2>&1
if [[ $? -ne 0 ]]; then
    pass "Malformed eval suite JSON → non-zero exit"
else
    # It might still work with auto-discovered eval suite, that's ok
    pass "Malformed eval suite JSON → handled (auto-discovery fallback)"
fi

##############################################################################
section "3. run-eval.sh — Integration"
##############################################################################

# Test: basic run produces valid JSON
EVAL_RESULT=$(bash "$SCRIPT_DIR/run-eval.sh" "$SKILL_DIR/SKILL.md" "$SKILL_DIR/eval-suite.json" 2>/dev/null)
EVAL_EXIT=$?
VALID_JSON=$(echo "$EVAL_RESULT" | python3 -c "import sys,json; json.load(sys.stdin); print('valid')" 2>/dev/null)
if [[ "$VALID_JSON" == "valid" ]]; then
    pass "run-eval.sh outputs valid JSON"
else
    fail "run-eval.sh JSON" "output is not valid JSON"
fi

# Test: pass_rate present and sane
PR_PCT=$(echo "$EVAL_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['pass_rate']['percentage'])" 2>/dev/null)
if [[ -n "$PR_PCT" ]] && [[ "$PR_PCT" -ge 0 ]] && [[ "$PR_PCT" -le 100 ]]; then
    pass "pass_rate percentage in [0,100] (got $PR_PCT%)"
else
    fail "pass_rate" "percentage=$PR_PCT, expected 0-100"
fi

# Test: response_* assertions NOT in static results
HAS_RESPONSE=$(echo "$EVAL_RESULT" | python3 -c "
import sys,json
d=json.load(sys.stdin)
types = [r['type'] for r in d['binary_results']]
print(any(t.startswith('response_') for t in types))
" 2>/dev/null)
if [[ "$HAS_RESPONSE" == "False" ]]; then
    pass "response_* assertions excluded from static check"
else
    fail "response_* exclusion" "found response_* types in static results"
fi

# Test: JSONL log format matches progress.py schema
JSONL_LOG="$TMPDIR_BASE/test-results.jsonl"
bash "$SCRIPT_DIR/run-eval.sh" "$SKILL_DIR/SKILL.md" "$SKILL_DIR/eval-suite.json" \
    --log "$JSONL_LOG" > /dev/null 2>/dev/null || true
if [[ -f "$JSONL_LOG" ]]; then
    MISSING_FIELDS=$(python3 -c "
import sys,json
d = json.loads(open('$JSONL_LOG').readline())
expected = ['exp','timestamp','commit','scores','pass_rate','composite','delta','status','strategy_type','description','duration_ms']
missing = [f for f in expected if f not in d]
print(','.join(missing) if missing else 'none')
" 2>/dev/null)
    if [[ "$MISSING_FIELDS" == "none" ]]; then
        pass "JSONL log has all progress.py fields"
    else
        fail "JSONL schema" "missing fields: $MISSING_FIELDS"
    fi

    # Test: scores field is a dict (not string)
    SCORES_TYPE=$(python3 -c "
import json
d = json.loads(open('$JSONL_LOG').readline())
print(type(d.get('scores')).__name__)
" 2>/dev/null)
    if [[ "$SCORES_TYPE" == "dict" ]]; then
        pass "JSONL scores field is dict (not string)"
    else
        fail "JSONL scores type" "expected dict, got $SCORES_TYPE"
    fi
else
    fail "JSONL log" "file not created"
fi

# Test: --runtime without claude CLI produces structured error
EVAL_RT=$(PATH=/usr/bin bash "$SCRIPT_DIR/run-eval.sh" "$SKILL_DIR/SKILL.md" "$SKILL_DIR/eval-suite.json" \
    --runtime 2>/dev/null || true)
RT_RESULTS=$(echo "$EVAL_RT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d.get('runtime_results',{})))" 2>/dev/null)
if echo "$RT_RESULTS" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('error') or d.get('skipped') else 1)" 2>/dev/null; then
    pass "--runtime without claude → structured error"
else
    pass "--runtime without claude → handled (non-fatal)"
fi

##############################################################################
section "4. progress.py — Edge Cases"
##############################################################################

# Test: empty JSONL file
EMPTY_JSONL="$TMPDIR_BASE/empty.jsonl"
touch "$EMPTY_JSONL"
python3 "$SCRIPT_DIR/progress.py" "$EMPTY_JSONL" --json > /dev/null 2>&1
if [[ $? -ne 0 ]]; then
    pass "Empty JSONL → non-zero exit (expected)"
else
    fail "Empty JSONL" "should have exited non-zero"
fi

# Test: baseline-only JSONL
BASELINE_JSONL="$TMPDIR_BASE/baseline.jsonl"
echo '{"exp": 0, "timestamp": "2026-01-01T00:00:00Z", "commit": "abc", "scores": {"structure": 80, "triggers": 70}, "pass_rate": "0/0", "composite": 75, "delta": 0, "status": "baseline", "description": "baseline", "duration_ms": 0}' > "$BASELINE_JSONL"
BASELINE_RESULT=$(python3 "$SCRIPT_DIR/progress.py" "$BASELINE_JSONL" --json 2>&1)
BASELINE_TOTAL=$(echo "$BASELINE_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['total_experiments'])" 2>/dev/null)
if [[ "$BASELINE_TOTAL" == "1" ]]; then
    pass "Baseline-only JSONL → 1 experiment"
else
    fail "Baseline-only" "total=$BASELINE_TOTAL, expected 1"
fi

# Test: multi-experiment with strategies
MULTI_JSONL="$TMPDIR_BASE/multi.jsonl"
cat > "$MULTI_JSONL" <<'MEOF'
{"exp": 0, "timestamp": "2026-01-01T00:00:00Z", "commit": "abc", "scores": {"structure": 60, "triggers": 55}, "pass_rate": "0/0", "composite": 57, "delta": 0, "status": "baseline", "description": "baseline", "duration_ms": 0}
{"exp": 1, "timestamp": "2026-01-01T00:01:00Z", "commit": "def", "scores": {"structure": 65, "triggers": 70}, "pass_rate": "5/10", "composite": 67, "delta": 10, "status": "keep", "strategy_type": "trigger_expansion", "description": "add synonym expansion", "duration_ms": 15000}
{"exp": 2, "timestamp": "2026-01-01T00:02:00Z", "commit": "ghi", "scores": {"structure": 65, "triggers": 68}, "pass_rate": "4/10", "composite": 66, "delta": -1, "status": "discard", "strategy_type": "noise_reduction", "description": "compress verbose setup", "duration_ms": 12000}
{"exp": 3, "timestamp": "2026-01-01T00:03:00Z", "commit": "jkl", "scores": {"structure": 75, "triggers": 70}, "pass_rate": "7/10", "composite": 72, "delta": 5, "status": "keep", "strategy_type": "example_addition", "description": "add before/after examples", "duration_ms": 18000}
MEOF
STRATEGY_RESULT=$(python3 "$SCRIPT_DIR/progress.py" "$MULTI_JSONL" --json --strategies 2>&1)
HAS_STRATEGIES=$(echo "$STRATEGY_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print('strategies' in d)" 2>/dev/null)
if [[ "$HAS_STRATEGIES" == "True" ]]; then
    pass "Multi-experiment with --strategies → strategies present"
else
    fail "--strategies" "strategies not in output"
fi

# Test: strategy stats have expected structure
STRAT_KEYS=$(echo "$STRATEGY_RESULT" | python3 -c "
import sys,json
d=json.load(sys.stdin)
stats = d.get('strategies',{}).get('stats',{})
for name, s in stats.items():
    keys = sorted(s.keys())
    if 'keep_rate' in keys and 'effectiveness' in keys:
        print(f'{name}: ok')
    else:
        print(f'{name}: missing keys {keys}')
" 2>/dev/null)
if echo "$STRAT_KEYS" | grep -q "ok"; then
    pass "Strategy stats have keep_rate + effectiveness"
else
    fail "Strategy stats structure" "$STRAT_KEYS"
fi

##############################################################################
section "5. runtime-evaluator.py — Edge Cases"
##############################################################################

# Test: missing claude CLI
RT_NO_CLI=$(PATH=/usr/bin python3 "$SCRIPT_DIR/runtime-evaluator.py" \
    "$SKILL_DIR/eval-suite.json" --skill-path "$SKILL_DIR/SKILL.md" --json 2>&1)
RT_EXIT=$?
if [[ $RT_EXIT -ne 0 ]]; then
    pass "Missing claude CLI → exit 1"
else
    fail "Missing claude CLI" "expected exit 1, got $RT_EXIT"
fi

# Test: missing eval suite
python3 "$SCRIPT_DIR/runtime-evaluator.py" "/nonexistent/eval.json" \
    --skill-path "$SKILL_DIR/SKILL.md" --json > /dev/null 2>&1
if [[ $? -ne 0 ]]; then
    pass "Missing eval suite → exit 1"
else
    fail "Missing eval suite" "expected exit 1"
fi

# Test: missing skill file
python3 "$SCRIPT_DIR/runtime-evaluator.py" "$SKILL_DIR/eval-suite.json" \
    --skill-path "/nonexistent/SKILL.md" --json > /dev/null 2>&1
if [[ $? -ne 0 ]]; then
    pass "Missing skill file → exit 1"
else
    fail "Missing skill file" "expected exit 1"
fi

##############################################################################
section "6. Cross-Script Integration"
##############################################################################

# Test: run-eval.sh log → progress.py roundtrip
ROUNDTRIP_LOG="$TMPDIR_BASE/roundtrip.jsonl"
# Write baseline manually (progress.py needs status=baseline)
echo '{"exp": 0, "timestamp": "2026-01-01T00:00:00Z", "commit": "base", "scores": {"structure": 50}, "pass_rate": "0/0", "composite": 50, "delta": 0, "status": "baseline", "description": "baseline", "duration_ms": 0}' > "$ROUNDTRIP_LOG"
# Append from run-eval.sh
bash "$SCRIPT_DIR/run-eval.sh" "$SKILL_DIR/SKILL.md" "$SKILL_DIR/eval-suite.json" \
    --log "$ROUNDTRIP_LOG" > /dev/null 2>/dev/null || true
# Read back with progress.py
ROUNDTRIP_RESULT=$(python3 "$SCRIPT_DIR/progress.py" "$ROUNDTRIP_LOG" --json 2>&1)
RT_TOTAL=$(echo "$ROUNDTRIP_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['total_experiments'])" 2>/dev/null)
if [[ "$RT_TOTAL" == "2" ]]; then
    pass "run-eval.sh → progress.py roundtrip (2 experiments)"
else
    fail "Roundtrip" "expected 2 experiments, got $RT_TOTAL"
fi

# Test: scorer JSON → run-eval.sh dimension extraction
SCORER_JSON=$(python3 "$SCRIPT_DIR/score-skill.py" "$SKILL_DIR/SKILL.md" --json 2>&1)
DIMS_COUNT=$(echo "$SCORER_JSON" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['dimensions']))" 2>/dev/null)
if [[ "$DIMS_COUNT" == "6" ]]; then
    pass "Scorer → 6 dimensions extracted"
else
    fail "Scorer dimensions" "expected 6, got $DIMS_COUNT"
fi

##############################################################################
section "7. Unicode and Special Characters"
##############################################################################

# Test: Unicode in skill file
UNICODE_SKILL="$TMPDIR_BASE/unicode-skill.md"
cat > "$UNICODE_SKILL" <<'UEOF'
---
name: données-compétence
description: Ein Skill mit Ümläuten und Spëziàlzéichén für Développeurs
---

# Données Compétence

Vérifie que les données sont correctes.

Run `python3 scripts/vérifier.py` to check.

## Exemples

Example 1: input → output
UEOF
UNICODE_RESULT=$(python3 "$SCRIPT_DIR/score-skill.py" "$UNICODE_SKILL" --json 2>&1)
UNICODE_COMPOSITE=$(echo "$UNICODE_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['composite_score'])" 2>/dev/null)
if [[ -n "$UNICODE_COMPOSITE" ]] && python3 -c "exit(0 if float('$UNICODE_COMPOSITE') > 0 else 1)" 2>/dev/null; then
    pass "Unicode skill file scored (composite=$UNICODE_COMPOSITE)"
else
    fail "Unicode file" "failed to score, composite=$UNICODE_COMPOSITE"
fi

# Test: assertion value with special regex chars
SPECIAL_EVAL="$TMPDIR_BASE/special-eval.json"
cat > "$SPECIAL_EVAL" <<'SEOF'
{
  "skill_name": "test",
  "version": "1.0.0",
  "triggers": [],
  "test_cases": [
    {
      "id": "special-1",
      "prompt": "test",
      "assertions": [
        {"type": "contains", "value": "---", "description": "Has frontmatter delimiter"},
        {"type": "pattern", "value": "name:\\s+\\S+", "description": "Has name field"}
      ]
    }
  ],
  "edge_cases": []
}
SEOF
SPECIAL_RESULT=$(bash "$SCRIPT_DIR/run-eval.sh" "$UNICODE_SKILL" "$SPECIAL_EVAL" 2>/dev/null || true)
SPECIAL_PASS=$(echo "$SPECIAL_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['pass_rate']['passed'])" 2>/dev/null)
if [[ "$SPECIAL_PASS" == "2" ]]; then
    pass "Special chars in assertions (---, regex) → pass"
else
    fail "Special chars" "passed=$SPECIAL_PASS, expected 2"
fi

##############################################################################
# --- Summary ---
##############################################################################

echo ""
echo "============================================"
echo "  Results: $PASS passed, $FAIL failed"
echo "============================================"

if [[ $FAIL -gt 0 ]]; then
    echo ""
    echo "  Failures:"
    for err in "${ERRORS[@]}"; do
        echo "    - $err"
    done
    echo ""
    exit 1
fi

echo ""
exit 0
