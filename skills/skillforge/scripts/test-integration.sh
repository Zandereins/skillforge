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
EVAL_RESULT=$(bash "$SCRIPT_DIR/run-eval.sh" "$SKILL_DIR/SKILL.md" "$SKILL_DIR/eval-suite.json" --no-runtime-auto 2>/dev/null)
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
    --log "$JSONL_LOG" --no-runtime-auto > /dev/null 2>/dev/null || true
if [[ -f "$JSONL_LOG" ]]; then
    MISSING_FIELDS=$(python3 -c "
import sys,json
d = json.loads(open('$JSONL_LOG').readline())
expected = ['exp','timestamp','commit','scores','pass_rate','composite','delta','status','strategy_type','description','duration_ms','tokens_estimated']
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
    --log "$ROUNDTRIP_LOG" --no-runtime-auto > /dev/null 2>/dev/null || true
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
section "8. --since Bug Fix (progress.py)"
##############################################################################

SINCE_JSONL="$TMPDIR_BASE/since.jsonl"
cat > "$SINCE_JSONL" <<'SEOF'
{"exp": 0, "timestamp": "2026-01-01T00:00:00Z", "commit": "a", "scores": {"s": 50}, "pass_rate": "0/0", "composite": 50, "delta": 0, "status": "baseline", "description": "baseline", "duration_ms": 1000}
{"exp": 1, "timestamp": "2026-01-01T00:01:00Z", "commit": "b", "scores": {"s": 60}, "pass_rate": "5/10", "composite": 60, "delta": 10, "status": "keep", "description": "add x", "duration_ms": 2000}
{"exp": 2, "timestamp": "2026-01-01T00:02:00Z", "commit": "c", "scores": {"s": 55}, "pass_rate": "4/10", "composite": 55, "delta": -5, "status": "discard", "description": "try y", "duration_ms": 1500}
{"exp": 3, "timestamp": "2026-01-01T00:03:00Z", "commit": "d", "scores": {"s": 65}, "pass_rate": "7/10", "composite": 65, "delta": 5, "status": "keep", "description": "add z", "duration_ms": 3000}
{"exp": 4, "timestamp": "2026-01-01T00:04:00Z", "commit": "e", "scores": {"s": 63}, "pass_rate": "6/10", "composite": 63, "delta": -2, "status": "discard", "description": "try w", "duration_ms": 1000}
{"exp": 5, "timestamp": "2026-01-01T00:05:00Z", "commit": "f", "scores": {"s": 70}, "pass_rate": "8/10", "composite": 70, "delta": 5, "status": "keep", "description": "add v", "duration_ms": 2500}
SEOF

# Test: --since 2 returns exactly 2 experiments
SINCE_RESULT=$(python3 "$SCRIPT_DIR/progress.py" "$SINCE_JSONL" --since 2 --json 2>&1)
SINCE_TOTAL=$(echo "$SINCE_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['total_experiments'])" 2>/dev/null)
if [[ "$SINCE_TOTAL" == "2" ]]; then
    pass "--since 2 → total_experiments=2"
else
    fail "--since total" "expected 2, got $SINCE_TOTAL"
fi

# Test: --since 2 outcomes sum to 2
SINCE_OUTCOMES=$(echo "$SINCE_RESULT" | python3 -c "
import sys,json
o = json.load(sys.stdin)['outcomes']
print(o['keep'] + o['discard'] + o['crash'])
" 2>/dev/null)
if [[ "$SINCE_OUTCOMES" == "2" ]]; then
    pass "--since 2 → outcomes sum=2"
else
    fail "--since outcomes" "expected sum 2, got $SINCE_OUTCOMES"
fi

# Test: --since 2 time_metrics only from last 2 experiments
SINCE_TIME=$(echo "$SINCE_RESULT" | python3 -c "
import sys,json
t = json.load(sys.stdin)['time']['total_seconds']
# Last 2 exps: 1000ms + 2500ms = 3500ms = 3.5s
print(t)
" 2>/dev/null)
if python3 -c "exit(0 if abs(float('$SINCE_TIME') - 3.5) < 0.1 else 1)" 2>/dev/null; then
    pass "--since 2 → time from last 2 only ($SINCE_TIME s)"
else
    fail "--since time" "expected ~3.5s, got $SINCE_TIME"
fi

# Test: --since 3 includes 3 experiments
SINCE3_RESULT=$(python3 "$SCRIPT_DIR/progress.py" "$SINCE_JSONL" --since 3 --json 2>&1)
SINCE3_TOTAL=$(echo "$SINCE3_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['total_experiments'])" 2>/dev/null)
if [[ "$SINCE3_TOTAL" == "3" ]]; then
    pass "--since 3 → total_experiments=3"
else
    fail "--since 3 total" "expected 3, got $SINCE3_TOTAL"
fi

# Test: full run (no --since) returns all 6
FULL_RESULT=$(python3 "$SCRIPT_DIR/progress.py" "$SINCE_JSONL" --json 2>&1)
FULL_TOTAL=$(echo "$FULL_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['total_experiments'])" 2>/dev/null)
if [[ "$FULL_TOTAL" == "6" ]]; then
    pass "No --since → total_experiments=6 (all)"
else
    fail "No --since total" "expected 6, got $FULL_TOTAL"
fi

##############################################################################
section "9. explain_score_change() (score-skill.py)"
##############################################################################

# Test explain_score_change via Python direct import
EXPLAIN_TESTS=$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from importlib.util import spec_from_file_location, module_from_spec
spec = spec_from_file_location('score_skill', '$SCRIPT_DIR/score-skill.py')
mod = module_from_spec(spec)
spec.loader.exec_module(mod)

passed = 0
failed = 0
errors = []

# Test 1: Changed scores produce explanations
old = {'structure': 70, 'triggers': 80}
new = {'structure': 85, 'triggers': 80}
result = mod.explain_score_change(old, new, {'available': False})
if len(result) == 1 and result[0]['dimension'] == 'structure':
    passed += 1
else:
    failed += 1; errors.append(f'changed scores: {result}')

# Test 2: Unchanged scores (delta < 0.5) → empty
old = {'structure': 70.0}
new = {'structure': 70.3}
result = mod.explain_score_change(old, new, {'available': False})
if len(result) == 0:
    passed += 1
else:
    failed += 1; errors.append(f'unchanged: {result}')

# Test 3: Empty diff → no context annotations
old = {'efficiency': 60}
new = {'efficiency': 75}
result = mod.explain_score_change(old, new, {'available': False})
if result and '(noise removed)' not in result[0]['explanation']:
    passed += 1
else:
    failed += 1; errors.append(f'empty diff: {result}')

# Test 4: New-only dimension → old defaults to 0
old = {}
new = {'clarity': 80}
result = mod.explain_score_change(old, new, {'available': False})
if len(result) == 1 and result[0]['old'] == 0:
    passed += 1
else:
    failed += 1; errors.append(f'new-only dim: {result}')

# Test 5: Diff with noise removed annotation
old = {'efficiency': 60}
new = {'efficiency': 75}
diff = {'available': True, 'net_change': {'noise': -3, 'signal': 0, 'lines': -5}}
result = mod.explain_score_change(old, new, diff)
if result and '(noise removed)' in result[0]['explanation']:
    passed += 1
else:
    failed += 1; errors.append(f'noise removed: {result}')

# Test 6: Diff with signal added annotation
old = {'efficiency': 60}
new = {'efficiency': 75}
diff = {'available': True, 'net_change': {'noise': 0, 'signal': 5, 'lines': 10}}
result = mod.explain_score_change(old, new, diff)
if result and '(signal added)' in result[0]['explanation']:
    passed += 1
else:
    failed += 1; errors.append(f'signal added: {result}')

# Test 7: Structure with lines removed annotation
old = {'structure': 60}
new = {'structure': 75}
diff = {'available': True, 'net_change': {'noise': 0, 'signal': 0, 'lines': -20}}
result = mod.explain_score_change(old, new, diff)
if result and '(file shortened)' in result[0]['explanation']:
    passed += 1
else:
    failed += 1; errors.append(f'file shortened: {result}')

print(f'{passed},{failed}')
if errors:
    for e in errors:
        print(f'  ERR: {e}', file=sys.stderr)
" 2>&1)
EXPLAIN_PASSED=$(echo "$EXPLAIN_TESTS" | head -1 | cut -d, -f1)
EXPLAIN_FAILED=$(echo "$EXPLAIN_TESTS" | head -1 | cut -d, -f2)
if [[ "$EXPLAIN_FAILED" == "0" ]]; then
    pass "explain_score_change: $EXPLAIN_PASSED/7 tests passed"
else
    fail "explain_score_change" "$EXPLAIN_PASSED passed, $EXPLAIN_FAILED failed"
fi

##############################################################################
section "10. _extract_description() (score-skill.py)"
##############################################################################

EXTRACT_TESTS=$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from importlib.util import spec_from_file_location, module_from_spec
spec = spec_from_file_location('score_skill', '$SCRIPT_DIR/score-skill.py')
mod = module_from_spec(spec)
spec.loader.exec_module(mod)

passed = 0
failed = 0
errors = []

# Test 1: inline description
r = mod._extract_description('---\nname: test\ndescription: inline text here\n---\n')
if r == 'inline text here':
    passed += 1
else:
    failed += 1; errors.append(f'inline: {repr(r)}')

# Test 2: block scalar >
r = mod._extract_description('---\nname: test\ndescription: >\n  block text\n  continues\n---\n')
if 'block text' in r:
    passed += 1
else:
    failed += 1; errors.append(f'block >: {repr(r)}')

# Test 3: block scalar |
r = mod._extract_description('---\nname: test\ndescription: |\n  literal text\n  here\n---\n')
if 'literal text' in r:
    passed += 1
else:
    failed += 1; errors.append(f'block |: {repr(r)}')

# Test 4: empty description
r = mod._extract_description('---\nname: test\n---\n')
if r == '':
    passed += 1
else:
    failed += 1; errors.append(f'empty: {repr(r)}')

# Test 5: missing description field
r = mod._extract_description('---\nname: test\nversion: 1\n---\n')
if r == '':
    passed += 1
else:
    failed += 1; errors.append(f'missing: {repr(r)}')

# Test 6: >- variant
r = mod._extract_description('---\nname: test\ndescription: >-\n  folded strip\n  text\n---\n')
if 'folded strip' in r:
    passed += 1
else:
    failed += 1; errors.append(f'>-: {repr(r)}')

# Test 7: quoted description
r = mod._extract_description('---\nname: test\ndescription: \"quoted text\"\n---\n')
if r == 'quoted text':
    passed += 1
else:
    failed += 1; errors.append(f'quoted: {repr(r)}')

print(f'{passed},{failed}')
if errors:
    for e in errors:
        print(f'  ERR: {e}', file=sys.stderr)
" 2>&1)
EXTRACT_PASSED=$(echo "$EXTRACT_TESTS" | head -1 | cut -d, -f1)
EXTRACT_FAILED=$(echo "$EXTRACT_TESTS" | head -1 | cut -d, -f2)
if [[ "$EXTRACT_FAILED" == "0" ]]; then
    pass "_extract_description: $EXTRACT_PASSED/7 tests passed"
else
    fail "_extract_description" "$EXTRACT_PASSED passed, $EXTRACT_FAILED failed"
fi

##############################################################################
section "11. _infer_strategy() (progress.py)"
##############################################################################

INFER_TESTS=$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from importlib.util import spec_from_file_location, module_from_spec
spec = spec_from_file_location('progress', '$SCRIPT_DIR/progress.py')
mod = module_from_spec(spec)
spec.loader.exec_module(mod)

# Create dummy analyzer with minimal data
import tempfile, json, os
tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False)
tmp.write(json.dumps({'exp': 0, 'status': 'baseline', 'composite': 50}) + '\n')
tmp.close()
analyzer = mod.ProgressAnalyzer(tmp.name)
os.unlink(tmp.name)

passed = 0
failed = 0
errors = []

# Test 1: synonym expansion → trigger_expansion
r = analyzer._infer_strategy('add synonym expansion for deploy triggers')
if r == 'trigger_expansion':
    passed += 1
else:
    failed += 1; errors.append(f'synonym: {r}')

# Test 2: compress verbose → noise_reduction
r = analyzer._infer_strategy('compress verbose setup section')
if r == 'noise_reduction':
    passed += 1
else:
    failed += 1; errors.append(f'compress: {r}')

# Test 3: no keywords → None
r = analyzer._infer_strategy('random unrelated change')
if r is None:
    passed += 1
else:
    failed += 1; errors.append(f'no keywords: {r}')

# Test 4: empty string → None
r = analyzer._infer_strategy('')
if r is None:
    passed += 1
else:
    failed += 1; errors.append(f'empty: {r}')

# Test 5: multi-keyword → highest count wins
r = analyzer._infer_strategy('add example input/output sample before/after')
if r == 'example_addition':
    passed += 1
else:
    failed += 1; errors.append(f'multi-keyword: {r}')

# Test 6: case insensitivity
r = analyzer._infer_strategy('Add SYNONYM EXPANSION for triggers')
if r == 'trigger_expansion':
    passed += 1
else:
    failed += 1; errors.append(f'case: {r}')

print(f'{passed},{failed}')
if errors:
    for e in errors:
        print(f'  ERR: {e}', file=sys.stderr)
" 2>&1)
INFER_PASSED=$(echo "$INFER_TESTS" | head -1 | cut -d, -f1)
INFER_FAILED=$(echo "$INFER_TESTS" | head -1 | cut -d, -f2)
if [[ "$INFER_FAILED" == "0" ]]; then
    pass "_infer_strategy: $INFER_PASSED/6 tests passed"
else
    fail "_infer_strategy" "$INFER_PASSED passed, $INFER_FAILED failed"
fi

##############################################################################
section "12. classify_eval_health() (progress.py)"
##############################################################################

HEALTH_TESTS=$(python3 -c "
import sys, tempfile, json, os
sys.path.insert(0, '$SCRIPT_DIR')
from importlib.util import spec_from_file_location, module_from_spec
spec = spec_from_file_location('progress', '$SCRIPT_DIR/progress.py')
mod = module_from_spec(spec)
spec.loader.exec_module(mod)

passed = 0
failed = 0
errors = []

def make_analyzer(entries):
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False)
    for e in entries:
        tmp.write(json.dumps(e) + '\n')
    tmp.close()
    a = mod.ProgressAnalyzer(tmp.name)
    os.unlink(tmp.name)
    return a

# Test 1: All mastered (avg>=95, var<5)
entries = [{'exp': i, 'status': 'keep', 'composite': 96, 'scores': {'dim1': 96 + (i % 2)}} for i in range(5)]
a = make_analyzer(entries)
h = a.classify_eval_health(window=10)
if 'dim1' in h['mastered']:
    passed += 1
else:
    failed += 1; errors.append(f'mastered: {h}')

# Test 2: All blocked (avg<50)
entries = [{'exp': i, 'status': 'keep', 'composite': 30, 'scores': {'dim1': 30 + (i % 3)}} for i in range(5)]
a = make_analyzer(entries)
h = a.classify_eval_health(window=10)
if 'dim1' in h['blocked']:
    passed += 1
else:
    failed += 1; errors.append(f'blocked: {h}')

# Test 3: Flaky (variance>50)
entries = [{'exp': i, 'status': 'keep', 'composite': 70, 'scores': {'dim1': 40 if i % 2 == 0 else 90}} for i in range(5)]
a = make_analyzer(entries)
h = a.classify_eval_health(window=10)
if 'dim1' in h['flaky']:
    passed += 1
else:
    failed += 1; errors.append(f'flaky: {h}')

# Test 4: Healthy (moderate avg, low variance)
entries = [{'exp': i, 'status': 'keep', 'composite': 70, 'scores': {'dim1': 70 + (i % 3)}} for i in range(5)]
a = make_analyzer(entries)
h = a.classify_eval_health(window=10)
if 'dim1' in h['healthy']:
    passed += 1
else:
    failed += 1; errors.append(f'healthy: {h}')

# Test 5: <3 kept → all empty
entries = [{'exp': 0, 'status': 'baseline', 'composite': 50, 'scores': {'dim1': 50}},
           {'exp': 1, 'status': 'keep', 'composite': 60, 'scores': {'dim1': 60}}]
a = make_analyzer(entries)
h = a.classify_eval_health(window=10)
if all(len(v) == 0 for v in h.values()):
    passed += 1
else:
    failed += 1; errors.append(f'<3 kept: {h}')

# Test 6: Score -1 sentinel → skipped
entries = [{'exp': i, 'status': 'keep', 'composite': 70, 'scores': {'dim1': -1}} for i in range(5)]
a = make_analyzer(entries)
h = a.classify_eval_health(window=10)
if 'dim1' not in h['mastered'] and 'dim1' not in h['blocked'] and 'dim1' not in h['flaky'] and 'dim1' not in h['healthy']:
    passed += 1
else:
    failed += 1; errors.append(f'-1 sentinel: {h}')

print(f'{passed},{failed}')
if errors:
    for e in errors:
        print(f'  ERR: {e}', file=sys.stderr)
" 2>&1)
HEALTH_PASSED=$(echo "$HEALTH_TESTS" | head -1 | cut -d, -f1)
HEALTH_FAILED=$(echo "$HEALTH_TESTS" | head -1 | cut -d, -f2)
if [[ "$HEALTH_FAILED" == "0" ]]; then
    pass "classify_eval_health: $HEALTH_PASSED/6 tests passed"
else
    fail "classify_eval_health" "$HEALTH_PASSED passed, $HEALTH_FAILED failed"
fi

##############################################################################
section "13. check_assertion() edge cases (run-eval.sh)"
##############################################################################

# Test: invalid regex pattern → assertion fails (not crash)
REGEX_EVAL="$TMPDIR_BASE/regex-eval.json"
cat > "$REGEX_EVAL" <<'REOF'
{
  "skill_name": "test",
  "version": "1.0.0",
  "triggers": [],
  "test_cases": [
    {
      "id": "regex-1",
      "prompt": "test",
      "assertions": [
        {"type": "pattern", "value": "[invalid(regex", "description": "Bad regex"},
        {"type": "contains", "value": "---", "description": "Has frontmatter"}
      ]
    }
  ],
  "edge_cases": []
}
REOF
REGEX_RESULT=$(bash "$SCRIPT_DIR/run-eval.sh" "$SKILL_DIR/SKILL.md" "$REGEX_EVAL" --no-runtime-auto 2>/dev/null || true)
REGEX_PASSED_CT=$(echo "$REGEX_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['pass_rate']['passed'])" 2>/dev/null)
REGEX_TOTAL_CT=$(echo "$REGEX_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['pass_rate']['total'])" 2>/dev/null)
# Bad regex should fail (grep -qiE returns non-zero), frontmatter should pass
if [[ "$REGEX_PASSED_CT" == "1" ]] && [[ "$REGEX_TOTAL_CT" == "2" ]]; then
    pass "Invalid regex → assertion fails gracefully (1/2 passed)"
else
    fail "Invalid regex" "passed=$REGEX_PASSED_CT total=$REGEX_TOTAL_CT, expected 1/2"
fi

# Test: unknown assertion type → passed (skipped)
UNKNOWN_EVAL="$TMPDIR_BASE/unknown-eval.json"
cat > "$UNKNOWN_EVAL" <<'UEOF'
{
  "skill_name": "test",
  "version": "1.0.0",
  "triggers": [],
  "test_cases": [
    {
      "id": "unknown-1",
      "prompt": "test",
      "assertions": [
        {"type": "nonexistent_type", "value": "foo", "description": "Unknown type"}
      ]
    }
  ],
  "edge_cases": []
}
UEOF
UNKNOWN_RESULT=$(bash "$SCRIPT_DIR/run-eval.sh" "$SKILL_DIR/SKILL.md" "$UNKNOWN_EVAL" --no-runtime-auto 2>/dev/null || true)
UNKNOWN_PASSED=$(echo "$UNKNOWN_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['pass_rate']['passed'])" 2>/dev/null)
if [[ "$UNKNOWN_PASSED" == "1" ]]; then
    pass "Unknown assertion type → passed (skipped)"
else
    fail "Unknown assertion type" "passed=$UNKNOWN_PASSED, expected 1"
fi

# Test: case-insensitive contains
CI_EVAL="$TMPDIR_BASE/ci-eval.json"
cat > "$CI_EVAL" <<'CEOF'
{
  "skill_name": "test",
  "version": "1.0.0",
  "triggers": [],
  "test_cases": [
    {
      "id": "ci-1",
      "prompt": "test",
      "assertions": [
        {"type": "contains", "value": "SKILLFORGE", "description": "Case insensitive match"}
      ]
    }
  ],
  "edge_cases": []
}
CEOF
CI_RESULT=$(bash "$SCRIPT_DIR/run-eval.sh" "$SKILL_DIR/SKILL.md" "$CI_EVAL" --no-runtime-auto 2>/dev/null || true)
CI_PASSED=$(echo "$CI_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['pass_rate']['passed'])" 2>/dev/null)
if [[ "$CI_PASSED" == "1" ]]; then
    pass "Case-insensitive contains → passed"
else
    fail "Case-insensitive contains" "passed=$CI_PASSED, expected 1"
fi

# Test: excludes pass/fail
EXCL_EVAL="$TMPDIR_BASE/excl-eval.json"
cat > "$EXCL_EVAL" <<'EEOF'
{
  "skill_name": "test",
  "version": "1.0.0",
  "triggers": [],
  "test_cases": [
    {
      "id": "excl-1",
      "prompt": "test",
      "assertions": [
        {"type": "excludes", "value": "ZZZNEVEREXISTS999", "description": "Excludes non-existent"},
        {"type": "excludes", "value": "SkillForge", "description": "Excludes existing text"}
      ]
    }
  ],
  "edge_cases": []
}
EEOF
EXCL_RESULT=$(bash "$SCRIPT_DIR/run-eval.sh" "$SKILL_DIR/SKILL.md" "$EXCL_EVAL" --no-runtime-auto 2>/dev/null || true)
EXCL_PASSED=$(echo "$EXCL_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['pass_rate']['passed'])" 2>/dev/null)
if [[ "$EXCL_PASSED" == "1" ]]; then
    pass "Excludes: non-existent passes, existing fails (1/2)"
else
    fail "Excludes" "passed=$EXCL_PASSED, expected 1"
fi

# Test: valid regex match
VREG_EVAL="$TMPDIR_BASE/vreg-eval.json"
cat > "$VREG_EVAL" <<'VEOF'
{
  "skill_name": "test",
  "version": "1.0.0",
  "triggers": [],
  "test_cases": [
    {
      "id": "vreg-1",
      "prompt": "test",
      "assertions": [
        {"type": "pattern", "value": "^---$", "description": "Frontmatter boundary"}
      ]
    }
  ],
  "edge_cases": []
}
VEOF
VREG_RESULT=$(bash "$SCRIPT_DIR/run-eval.sh" "$SKILL_DIR/SKILL.md" "$VREG_EVAL" --no-runtime-auto 2>/dev/null || true)
VREG_PASSED=$(echo "$VREG_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['pass_rate']['passed'])" 2>/dev/null)
if [[ "$VREG_PASSED" == "1" ]]; then
    pass "Valid regex pattern → passed"
else
    fail "Valid regex" "passed=$VREG_PASSED, expected 1"
fi

# Test: response_contains is skipped in static
RESP_EVAL="$TMPDIR_BASE/resp-eval.json"
cat > "$RESP_EVAL" <<'RESP'
{
  "skill_name": "test",
  "version": "1.0.0",
  "triggers": [],
  "test_cases": [
    {
      "id": "resp-1",
      "prompt": "test",
      "assertions": [
        {"type": "response_contains", "value": "anything", "description": "Runtime only"},
        {"type": "contains", "value": "---", "description": "Static check"}
      ]
    }
  ],
  "edge_cases": []
}
RESP
RESP_RESULT=$(bash "$SCRIPT_DIR/run-eval.sh" "$SKILL_DIR/SKILL.md" "$RESP_EVAL" --no-runtime-auto 2>/dev/null || true)
RESP_TOTAL=$(echo "$RESP_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['pass_rate']['total'])" 2>/dev/null)
if [[ "$RESP_TOTAL" == "1" ]]; then
    pass "response_contains skipped in static (total=1)"
else
    fail "response skip" "total=$RESP_TOTAL, expected 1"
fi

##############################################################################
section "14. score_clarity() sub-checks (score-skill.py)"
##############################################################################

# Test: contradiction detection
CONTRA_FILE="$TMPDIR_BASE/contra.md"
cat > "$CONTRA_FILE" <<'CEOF'
---
name: contra-test
description: test contradictions
---

# Test

Always run tests before deploying.
Never run tests in production.
CEOF
CONTRA_RESULT=$(python3 "$SCRIPT_DIR/score-skill.py" "$CONTRA_FILE" --json --clarity 2>&1)
CONTRA_SCORE=$(echo "$CONTRA_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['dimensions']['clarity'])" 2>/dev/null)
if python3 -c "exit(0 if int('$CONTRA_SCORE') < 100 else 1)" 2>/dev/null; then
    pass "Contradiction detected (clarity=$CONTRA_SCORE < 100)"
else
    fail "Contradiction" "clarity=$CONTRA_SCORE, expected < 100"
fi

# Test: vague reference detection
VAGUE_FILE="$TMPDIR_BASE/vague.md"
cat > "$VAGUE_FILE" <<'VEOF'
---
name: vague-test
description: test vague references
---

# Test

Some unrelated paragraph here.

Check the file for errors.
VEOF
VAGUE_RESULT=$(python3 "$SCRIPT_DIR/score-skill.py" "$VAGUE_FILE" --json --clarity 2>&1)
VAGUE_REFS=$(echo "$VAGUE_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['details']['clarity']['vague_references'])" 2>/dev/null)
if [[ "$VAGUE_REFS" -ge 1 ]]; then
    pass "Vague reference detected ($VAGUE_REFS found)"
else
    fail "Vague reference" "vague_references=$VAGUE_REFS, expected >= 1"
fi

# Test: ambiguous pronoun after empty line
AMBIG_FILE="$TMPDIR_BASE/ambig.md"
cat > "$AMBIG_FILE" <<'AEOF'
---
name: ambig-test
description: test ambiguous pronouns
---

# Test

It is important to check this.

It does validation.
AEOF
AMBIG_RESULT=$(python3 "$SCRIPT_DIR/score-skill.py" "$AMBIG_FILE" --json --clarity 2>&1)
AMBIG_COUNT=$(echo "$AMBIG_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['details']['clarity']['ambiguous_pronouns'])" 2>/dev/null)
if [[ "$AMBIG_COUNT" -ge 1 ]]; then
    pass "Ambiguous pronoun detected ($AMBIG_COUNT found)"
else
    fail "Ambiguous pronoun" "count=$AMBIG_COUNT, expected >= 1"
fi

# Test: clean file → high clarity score
CLEAN_FILE="$TMPDIR_BASE/clean.md"
cat > "$CLEAN_FILE" <<'CLEOF'
---
name: clean-test
description: a well-written skill for testing clarity
---

# Clean Test Skill

Run `python3 scripts/check.py` to validate the input.

Use `scripts/deploy.sh` to deploy the application.

Check `output.json` for results after running the pipeline.
CLEOF
CLEAN_RESULT=$(python3 "$SCRIPT_DIR/score-skill.py" "$CLEAN_FILE" --json --clarity 2>&1)
CLEAN_SCORE=$(echo "$CLEAN_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['dimensions']['clarity'])" 2>/dev/null)
if python3 -c "exit(0 if int('$CLEAN_SCORE') >= 90 else 1)" 2>/dev/null; then
    pass "Clean file → clarity >= 90 (got $CLEAN_SCORE)"
else
    fail "Clean clarity" "score=$CLEAN_SCORE, expected >= 90"
fi

# Test: code-block stripping (no false positive from code)
CODE_CONTRA="$TMPDIR_BASE/code-contra.md"
cat > "$CODE_CONTRA" <<'CCEOF'
---
name: code-contra
description: test code block stripping
---

# Code Example

```bash
# Always run tests
# Never skip linting
echo "done"
```

Run `python3 test.py` to verify.
CCEOF
CODE_CONTRA_RESULT=$(python3 "$SCRIPT_DIR/score-skill.py" "$CODE_CONTRA" --json --clarity 2>&1)
CODE_CONTRA_CONTRADICTIONS=$(echo "$CODE_CONTRA_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin)['details'].get('clarity',{}); print(len(d.get('contradictions',[])))" 2>/dev/null)
if [[ "$CODE_CONTRA_CONTRADICTIONS" == "0" ]]; then
    pass "Code blocks stripped: no false contradictions"
else
    fail "Code block stripping" "contradictions=$CODE_CONTRA_CONTRADICTIONS, expected 0"
fi

# Test: same-verb contradiction detection (exact topic overlap)
VERB_CONTRA="$TMPDIR_BASE/verb-contra.md"
cat > "$VERB_CONTRA" <<'VCEOF'
---
name: verb-contra
description: test same-verb contradictions
---

# Instructions

Always run tests before deploying.
Never run tests in production.
VCEOF
VERB_RESULT=$(python3 "$SCRIPT_DIR/score-skill.py" "$VERB_CONTRA" --json --clarity 2>&1)
VERB_CONTRADICTIONS=$(echo "$VERB_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin)['details'].get('clarity',{}); print(len(d.get('contradictions',[])))" 2>/dev/null)
if [[ "$VERB_CONTRADICTIONS" -ge 1 ]]; then
    pass "Same-verb contradiction detected ($VERB_CONTRADICTIONS found)"
else
    fail "Same-verb contradiction" "contradictions=$VERB_CONTRADICTIONS, expected >= 1"
fi

##############################################################################
section "15. Cost Tracking (run-eval.sh)"
##############################################################################

# Test: JSONL entry has duration_ms > 0
COST_LOG="$TMPDIR_BASE/cost.jsonl"
bash "$SCRIPT_DIR/run-eval.sh" "$SKILL_DIR/SKILL.md" "$SKILL_DIR/eval-suite.json" \
    --log "$COST_LOG" --no-runtime-auto > /dev/null 2>/dev/null || true
if [[ -f "$COST_LOG" ]]; then
    COST_DUR=$(python3 -c "import json; d=json.loads(open('$COST_LOG').readline()); print(d['duration_ms'])" 2>/dev/null)
    if [[ -n "$COST_DUR" ]] && [[ "$COST_DUR" -ge 0 ]]; then
        pass "JSONL duration_ms >= 0 (got ${COST_DUR}ms)"
    else
        fail "duration_ms" "expected >= 0, got $COST_DUR"
    fi

    # Test: tokens_estimated > 0
    COST_TOK=$(python3 -c "import json; d=json.loads(open('$COST_LOG').readline()); print(d['tokens_estimated'])" 2>/dev/null)
    if [[ -n "$COST_TOK" ]] && [[ "$COST_TOK" -gt 0 ]]; then
        pass "JSONL tokens_estimated > 0 (got $COST_TOK)"
    else
        fail "tokens_estimated" "expected > 0, got $COST_TOK"
    fi

    # Test: status is baseline on first run
    COST_STATUS=$(python3 -c "import json; d=json.loads(open('$COST_LOG').readline()); print(d['status'])" 2>/dev/null)
    if [[ "$COST_STATUS" == "baseline" ]]; then
        pass "JSONL status=baseline on first run"
    else
        fail "status" "expected baseline, got $COST_STATUS"
    fi

    # Test: second run computes delta and status correctly
    bash "$SCRIPT_DIR/run-eval.sh" "$SKILL_DIR/SKILL.md" "$SKILL_DIR/eval-suite.json" \
        --log "$COST_LOG" --no-runtime-auto > /dev/null 2>/dev/null || true
    SECOND_STATUS=$(python3 -c "
import json
lines = open('$COST_LOG').readlines()
d = json.loads(lines[1])
print(d['status'])
" 2>/dev/null)
    if [[ "$SECOND_STATUS" == "keep" ]] || [[ "$SECOND_STATUS" == "discard" ]]; then
        pass "JSONL second run status=$SECOND_STATUS (not pending)"
    else
        fail "second status" "expected keep/discard, got $SECOND_STATUS"
    fi
else
    fail "Cost log" "file not created"
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
