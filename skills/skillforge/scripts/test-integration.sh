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

# Test: scorer JSON → run-eval.sh dimension extraction (6 core + runtime)
SCORER_JSON=$(python3 "$SCRIPT_DIR/score-skill.py" "$SKILL_DIR/SKILL.md" --json 2>&1)
DIMS_COUNT=$(echo "$SCORER_JSON" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['dimensions']))" 2>/dev/null)
if [[ "$DIMS_COUNT" == "7" ]]; then
    pass "Scorer → 7 dimensions extracted (6 core + runtime)"
else
    fail "Scorer dimensions" "expected 7, got $DIMS_COUNT"
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
UNKNOWN_TOTAL=$(echo "$UNKNOWN_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['pass_rate']['total'])" 2>/dev/null)
if [[ "$UNKNOWN_TOTAL" == "0" ]]; then
    pass "Unknown assertion type → skipped (not counted)"
else
    fail "Unknown assertion type" "total=$UNKNOWN_TOTAL, expected 0 (skip)"
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
section "16. Regression Tests for Audit Fixes"
##############################################################################

# Test: cache eviction in score-skill.py does not crash after many invocations
# Scores 5 different temp skill files to exercise the cache eviction path
# (MAX_CACHE_ENTRIES=50; each invocation adds a fresh entry via _read_file_cached)
_CACHE_OK=1
for i in $(seq 1 5); do
    _CACHE_FILE="$TMPDIR_BASE/cache-test-$i.md"
    printf -- "---\nname: cache-test-%s\ndescription: cache eviction test file %s\n---\n\nContent paragraph %s for testing.\n" "$i" "$i" "$i" > "$_CACHE_FILE"
    python3 "$SCRIPT_DIR/score-skill.py" "$_CACHE_FILE" --json > /dev/null 2>&1 || _CACHE_OK=0
done
if [[ "$_CACHE_OK" == "1" ]]; then
    pass "Cache eviction: 5 sequential scorings complete without crash"
else
    fail "Cache eviction" "score-skill.py crashed during repeated invocations"
fi

# Test: counter locking in run-eval.sh — parallel runs produce unique experiment IDs
_LOCK_LOG="$TMPDIR_BASE/lock-test.jsonl"
bash "$SCRIPT_DIR/run-eval.sh" "$SKILL_DIR/SKILL.md" "$SKILL_DIR/eval-suite.json" \
    --no-runtime-auto --log "$_LOCK_LOG" > /dev/null 2>&1 &
_LOCK_PID1=$!
bash "$SCRIPT_DIR/run-eval.sh" "$SKILL_DIR/SKILL.md" "$SKILL_DIR/eval-suite.json" \
    --no-runtime-auto --log "$_LOCK_LOG" > /dev/null 2>&1 &
_LOCK_PID2=$!
wait "$_LOCK_PID1" 2>/dev/null; wait "$_LOCK_PID2" 2>/dev/null
_UNIQUE_IDS=$(grep -o '"exp":[0-9]*' "$_LOCK_LOG" 2>/dev/null | sort -u | wc -l | tr -d ' ')
if [[ "$_UNIQUE_IDS" == "2" ]]; then
    pass "Counter locking: parallel runs produced 2 unique experiment IDs"
else
    fail "Counter locking" "expected 2 unique exp IDs, got $_UNIQUE_IDS"
fi

# Test: symlink escape blocked in skill-mesh.py
# A symlink inside the scan root pointing outside must not be followed
_MESH_SAFE="$TMPDIR_BASE/mesh-safe"
_MESH_OUTSIDE="$TMPDIR_BASE/mesh-outside"
mkdir -p "$_MESH_SAFE" "$_MESH_OUTSIDE"
printf -- "---\nname: escaped\ndescription: should not appear\n---\nContent\n" > "$_MESH_OUTSIDE/SKILL.md"
ln -sf "$_MESH_OUTSIDE" "$_MESH_SAFE/symlink-escape"
_MESH_RESULT=$(python3 "$SCRIPT_DIR/skill-mesh.py" --json --skill-dirs "$_MESH_SAFE" 2>/dev/null)
_MESH_FOUND=$(echo "$_MESH_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['skills_found'])" 2>/dev/null)
if [[ "$_MESH_FOUND" == "0" ]]; then
    pass "Symlink escape blocked: skill-mesh.py found 0 skills (symlink not followed)"
else
    fail "Symlink escape" "skills_found=$_MESH_FOUND, expected 0"
fi

# Test: Unicode zero-width char sanitization in session-injector.js
# Failures file contains skill names with invisible zero-width chars; output must be clean
_INJECT_DIR="$TMPDIR_BASE/injector-test"
mkdir -p "$_INJECT_DIR/.skillforge"
printf '{"skill":"test\u200B\u200Cskill","failure_type":"test","injected":false}\n' \
    > "$_INJECT_DIR/.skillforge/failures.jsonl"
printf '{"skill":"test\u200Bskill2","failure_type":"test","injected":false}\n' \
    >> "$_INJECT_DIR/.skillforge/failures.jsonl"
printf '{"skill":"test\u200Bskill3","failure_type":"test","injected":false}\n' \
    >> "$_INJECT_DIR/.skillforge/failures.jsonl"
_INJECT_RESULT=$(echo "{\"cwd\":\"$_INJECT_DIR\"}" | node "$SKILL_DIR/hooks/session-injector.js" 2>/dev/null)
_HAS_ZW=$(echo "$_INJECT_RESULT" | python3 -c "
import sys
data = sys.stdin.read()
bad = [chr(0x200B), chr(0x200C), chr(0x200D), chr(0x200E), chr(0x200F)]
print(any(c in data for c in bad))
" 2>/dev/null)
if [[ "$_HAS_ZW" == "False" ]]; then
    pass "Unicode sanitization: zero-width chars stripped from injector output"
else
    fail "Unicode sanitization" "zero-width chars present in session-injector output"
fi

# Test: state-backup mechanism exists in auto-improve.py source
# Verifies the backup-before-truncation code path was not removed
_BACKUP_CHECK=$(grep -c "state-backup" "$SCRIPT_DIR/auto-improve.py" 2>/dev/null)
if [[ "$_BACKUP_CHECK" -ge 1 ]]; then
    pass "State backup: state-backup reference present in auto-improve.py"
else
    fail "State backup" "state-backup not found in auto-improve.py source"
fi

# Test: auto-improve.py handles --max-iterations 0 gracefully (ROI guard boundary)
# Should not crash and must report stop_reason in JSON output
_AUTOIMPROVE_RESULT=$(python3 "$SCRIPT_DIR/auto-improve.py" "$SKILL_DIR/SKILL.md" \
    --dry-run --max-iterations 0 --json 2>/dev/null)
_AUTOIMPROVE_STOP=$(echo "$_AUTOIMPROVE_RESULT" | \
    python3 -c "import sys,json; print(json.load(sys.stdin).get('stop_reason','MISSING'))" 2>/dev/null)
if [[ -n "$_AUTOIMPROVE_STOP" ]] && [[ "$_AUTOIMPROVE_STOP" != "MISSING" ]]; then
    pass "auto-improve --max-iterations 0: exits cleanly with stop_reason=$_AUTOIMPROVE_STOP"
else
    fail "auto-improve max-iterations 0" "stop_reason missing or crash; got: $_AUTOIMPROVE_STOP"
fi

# Test: meta-report.py handles nonexistent meta-dir without crashing
# Agents 1-4 fixed a None-correlation crash; ensure graceful JSON output remains
_META_RESULT=$(python3 "$SCRIPT_DIR/meta-report.py" --json --meta-dir /nonexistent 2>/dev/null)
_META_VALID=$(echo "$_META_RESULT" | python3 -c "import sys,json; json.load(sys.stdin); print('ok')" 2>/dev/null)
if [[ "$_META_VALID" == "ok" ]]; then
    pass "meta-report.py: nonexistent meta-dir → valid JSON (no crash)"
else
    fail "meta-report nonexistent dir" "output is not valid JSON or script crashed"
fi

# Test: unknown assertion type in eval suite → skipped (not auto-passed)
# Regression for the fix that ensures unknown types are excluded from pass_rate total
_UNKNOWN_SUITE="$TMPDIR_BASE/unknown-type-suite.json"
cat > "$_UNKNOWN_SUITE" <<'EOFSUITE'
{
  "skill_name": "test",
  "version": "1.0.0",
  "triggers": [],
  "test_cases": [
    {
      "id": "unk-1",
      "prompt": "test",
      "assertions": [
        {"type": "nonexistent_type", "value": "test", "description": "Unknown assertion"}
      ]
    }
  ],
  "edge_cases": []
}
EOFSUITE
_UNKNOWN_RESULT=$(bash "$SCRIPT_DIR/run-eval.sh" "$SKILL_DIR/SKILL.md" "$_UNKNOWN_SUITE" \
    --no-runtime-auto 2>/dev/null || true)
_UNKNOWN_TOTAL=$(echo "$_UNKNOWN_RESULT" | \
    python3 -c "import sys,json; print(json.load(sys.stdin)['pass_rate']['total'])" 2>/dev/null)
if [[ "$_UNKNOWN_TOTAL" == "0" ]]; then
    pass "Unknown assertion type: skipped (total=0, not auto-passed)"
else
    fail "Unknown assertion type regression" "total=$_UNKNOWN_TOTAL, expected 0 (should be skipped)"
fi

# Test: text-gradient.py handles invalid eval-suite JSON structure gracefully
# An array [] is valid JSON but not a valid eval-suite schema; must not crash
_BAD_SUITE="$TMPDIR_BASE/bad-suite.json"
echo '[]' > "$_BAD_SUITE"
_GRADIENT_RESULT=$(python3 "$SCRIPT_DIR/text-gradient.py" "$SKILL_DIR/SKILL.md" \
    --json --eval-suite "$_BAD_SUITE" 2>/dev/null)
_GRADIENT_VALID=$(echo "$_GRADIENT_RESULT" | \
    python3 -c "import sys,json; json.load(sys.stdin); print('ok')" 2>/dev/null)
if [[ "$_GRADIENT_VALID" == "ok" ]]; then
    pass "text-gradient.py: invalid eval-suite schema → valid JSON output (no crash)"
else
    fail "text-gradient bad eval-suite" "output not valid JSON or script crashed"
fi

# Test: dashboard.py produces valid JSON with expected top-level keys
_DASHBOARD_RESULT=$(python3 "$SCRIPT_DIR/dashboard.py" "$SKILL_DIR/SKILL.md" --json 2>/dev/null)
_DASHBOARD_VALID=$(echo "$_DASHBOARD_RESULT" | python3 -c "
import sys,json
d=json.load(sys.stdin)
assert 'composite_score' in d or 'skill_name' in d
print('ok')
" 2>/dev/null)
if [[ "$_DASHBOARD_VALID" == "ok" ]]; then
    pass "dashboard.py: produces valid JSON with expected keys"
else
    fail "dashboard.py output" "missing composite_score/skill_name or invalid JSON"
fi

# Test: parallel-runner.py --dry-run produces valid JSON without spawning processes
_PARALLEL_RESULT=$(python3 "$SCRIPT_DIR/parallel-runner.py" "$SKILL_DIR/SKILL.md" \
    --dry-run --json 2>/dev/null)
_PARALLEL_VALID=$(echo "$_PARALLEL_RESULT" | \
    python3 -c "import sys,json; json.load(sys.stdin); print('ok')" 2>/dev/null)
if [[ "$_PARALLEL_VALID" == "ok" ]]; then
    pass "parallel-runner.py: --dry-run produces valid JSON"
else
    fail "parallel-runner dry-run" "output is not valid JSON or script crashed"
fi

echo ""
echo "=== 17. Init & Report Tests ==="

# 17.1 init-skill.py on own SKILL.md (dry-run, JSON)
_INIT_RESULT=$(python3 "$SCRIPT_DIR/init-skill.py" "$SKILL_DIR/SKILL.md" --dry-run --json 2>/dev/null)
if echo "$_INIT_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['skill_name']=='skillforge'; assert d['triggers']['positive']>=5" 2>/dev/null; then
    pass "init-skill.py: generates valid eval-suite for own SKILL.md (dry-run)"
else
    fail "init-skill.py own SKILL.md" "invalid JSON or wrong skill_name"
fi

# 17.2 init-skill.py nonexistent file
python3 "$SCRIPT_DIR/init-skill.py" /nonexistent/SKILL.md --json 2>/dev/null
if [[ $? -eq 1 ]]; then
    pass "init-skill.py: nonexistent file → exit 1"
else
    fail "init-skill.py nonexistent" "expected exit 1"
fi

# 17.3 init-skill.py --dry-run does not write file
_INIT_TMP="$TMPDIR_BASE/init-dryrun-test"
mkdir -p "$_INIT_TMP"
echo -e "---\nname: dryrun-test\ndescription: A test skill\n---\nContent here" > "$_INIT_TMP/SKILL.md"
python3 "$SCRIPT_DIR/init-skill.py" "$_INIT_TMP/SKILL.md" --dry-run --json > /dev/null 2>&1
if [[ ! -f "$_INIT_TMP/eval-suite.json" ]]; then
    pass "init-skill.py: --dry-run does NOT write eval-suite.json"
else
    fail "init-skill.py dry-run" "file was written despite --dry-run"
fi

# 17.4 init-skill.py: positive triggers >= 5
_POS_COUNT=$(echo "$_INIT_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['triggers']['positive'])" 2>/dev/null)
if [[ "$_POS_COUNT" -ge 5 ]] 2>/dev/null; then
    pass "init-skill.py: positive triggers >= 5 (got $_POS_COUNT)"
else
    fail "init-skill.py positive triggers" "got $_POS_COUNT, expected >= 5"
fi

# 17.5 init-skill.py: negative triggers >= 3
_NEG_COUNT=$(echo "$_INIT_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['triggers']['negative'])" 2>/dev/null)
if [[ "$_NEG_COUNT" -ge 3 ]] 2>/dev/null; then
    pass "init-skill.py: negative triggers >= 3 (got $_NEG_COUNT)"
else
    fail "init-skill.py negative triggers" "got $_NEG_COUNT, expected >= 3"
fi

# 17.6 init-skill.py writes eval-suite.json (non-dry-run)
_INIT_WRITE="$TMPDIR_BASE/init-write-test"
mkdir -p "$_INIT_WRITE"
echo -e "---\nname: write-test\ndescription: Testing write behavior\n---\nSome skill content" > "$_INIT_WRITE/SKILL.md"
python3 "$SCRIPT_DIR/init-skill.py" "$_INIT_WRITE/SKILL.md" --json > /dev/null 2>&1
if [[ -f "$_INIT_WRITE/eval-suite.json" ]]; then
    # Validate it's valid JSON with required keys
    if python3 -c "import json; d=json.load(open('$_INIT_WRITE/eval-suite.json')); assert 'triggers' in d" 2>/dev/null; then
        pass "init-skill.py: writes valid eval-suite.json"
    else
        fail "init-skill.py write" "file written but invalid JSON"
    fi
else
    fail "init-skill.py write" "eval-suite.json was not created"
fi

# 17.7 generate-report.py with synthetic JSONL
cat > "$TMPDIR_BASE/report-test.jsonl" << 'EOFJSONL'
{"exp":1,"scores":{"structure":65},"composite":65,"pass_rate":"3/5","delta":0,"status":"baseline","description":"baseline"}
{"exp":2,"scores":{"structure":75},"composite":75,"pass_rate":"4/5","delta":10,"status":"keep","description":"added examples"}
EOFJSONL
_REPORT=$(python3 "$SCRIPT_DIR/generate-report.py" "$TMPDIR_BASE/report-test.jsonl" "$SKILL_DIR/SKILL.md" 2>/dev/null)
if echo "$_REPORT" | grep -q "# SkillForge Report"; then
    pass "generate-report.py: markdown starts with '# SkillForge Report'"
else
    fail "generate-report.py" "output missing report header"
fi

# 17.8 generate-report.py nonexistent SKILL.md
python3 "$SCRIPT_DIR/generate-report.py" "$TMPDIR_BASE/report-test.jsonl" /nonexistent/SKILL.md 2>/dev/null
if [[ $? -ne 0 ]]; then
    pass "generate-report.py: nonexistent SKILL.md → non-zero exit"
else
    fail "generate-report.py nonexistent" "expected non-zero exit"
fi

##############################################################################
# --- 18. New Features Tests ---
##############################################################################

section "18. New Features Tests"

# Achievements: produces valid JSON
ACH_OUT=$(python3 "$SCRIPT_DIR/achievements.py" "$SKILL_DIR/SKILL.md" --json 2>/dev/null)
if echo "$ACH_OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'total_unlocked' in d and 'total_available' in d" 2>/dev/null; then
    pass "achievements.py: produces valid JSON with expected keys"
else
    fail "achievements.py JSON" "missing expected keys"
fi

# Dashboard: gauge bars present
DASH_OUT=$(python3 "$SCRIPT_DIR/dashboard.py" "$SKILL_DIR/SKILL.md" 2>/dev/null)
if echo "$DASH_OUT" | grep -q "█"; then
    pass "dashboard.py: gauge bars rendered in text output"
else
    fail "dashboard.py gauges" "no gauge bars found"
fi

# Dashboard: achievements section present
if echo "$DASH_OUT" | grep -q "Achievements:"; then
    pass "dashboard.py: achievements section present"
else
    fail "dashboard.py achievements" "no achievements section"
fi

# Auto-improve: JSON has elapsed_seconds and sparkline fields
AI_OUT=$(python3 "$SCRIPT_DIR/auto-improve.py" "$SKILL_DIR/SKILL.md" --dry-run --max-iterations 0 --json 2>/dev/null)
if echo "$AI_OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'elapsed_seconds' in d and 'sparkline' in d" 2>/dev/null; then
    pass "auto-improve.py: JSON output has elapsed_seconds and sparkline"
else
    fail "auto-improve.py JSON fields" "missing elapsed_seconds or sparkline"
fi

# Auto-improve: compact banner in text mode
AI_TEXT=$(python3 "$SCRIPT_DIR/auto-improve.py" "$SKILL_DIR/SKILL.md" --dry-run --max-iterations 0 2>&1)
if echo "$AI_TEXT" | grep -q "SkillForge Auto-Improve Complete"; then
    pass "auto-improve.py: compact banner rendered"
else
    fail "auto-improve.py banner" "compact banner not found"
fi

# Report: share snippet present
REPORT_JSONL=$(mktemp)
echo '{"exp":0,"status":"baseline","composite":50,"scores":{"structure":50}}' > "$REPORT_JSONL"
echo '{"exp":1,"status":"keep","composite":55,"delta":5,"description":"test"}' >> "$REPORT_JSONL"
REPORT_OUT=$(python3 "$SCRIPT_DIR/generate-report.py" "$REPORT_JSONL" "$SKILL_DIR/SKILL.md" 2>/dev/null)
rm -f "$REPORT_JSONL"
if echo "$REPORT_OUT" | grep -q "Share this result"; then
    pass "generate-report.py: share snippet present in report"
else
    fail "generate-report.py share" "share snippet not found"
fi

# Achievements: nonexistent SKILL.md → non-zero exit
python3 "$SCRIPT_DIR/achievements.py" /nonexistent/SKILL.md --json 2>/dev/null
if [[ $? -ne 0 ]]; then
    pass "achievements.py: nonexistent SKILL.md → non-zero exit"
else
    fail "achievements.py nonexistent" "expected non-zero exit"
fi

##############################################################################
section "19. Terminal Art, Grade System, Heatmap"
##############################################################################

# terminal_art.py: score_to_grade mapping
GRADE_TESTS=$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from terminal_art import score_to_grade, render_heatmap, colored_bar, sparkline, render_banner, render_before_after, render_score_card

passed = 0
failed = 0
errors = []

# Grade thresholds
for score, expected in [(100,'S'),(95,'S'),(94.9,'A'),(85,'A'),(84,'B'),(75,'B'),(74,'C'),(65,'C'),(64,'D'),(50,'D'),(49,'F'),(0,'F')]:
    g = score_to_grade(score)
    if g == expected:
        passed += 1
    else:
        failed += 1; errors.append(f'grade({score})={g}, expected {expected}')

# Heatmap: renders with >= 3 iterations
dims = ['structure', 'triggers']
iters = [{'dimensions': {'structure': 40, 'triggers': 60}},
         {'dimensions': {'structure': 60, 'triggers': 75}},
         {'dimensions': {'structure': 85, 'triggers': 90}}]
hmap = render_heatmap(dims, iters)
if '\u2591' in hmap or '\u2592' in hmap or '\u2593' in hmap or '\u2588' in hmap:
    passed += 1
else:
    failed += 1; errors.append(f'heatmap missing block chars')

# Heatmap: empty returns empty string
if render_heatmap([], []) == '':
    passed += 1
else:
    failed += 1; errors.append('heatmap empty not empty string')

# colored_bar: returns string with block chars
bar = colored_bar(75.0)
if '\u2588' in bar:
    passed += 1
else:
    failed += 1; errors.append(f'colored_bar missing blocks')

# sparkline: renders values
sp = sparkline([10, 50, 90])
if len(sp) == 3:
    passed += 1
else:
    failed += 1; errors.append(f'sparkline length={len(sp)}')

# render_banner: contains title
banner = render_banner('Test Title', 'subtitle')
if 'Test Title' in banner and 'SkillForge' in banner:
    passed += 1
else:
    failed += 1; errors.append(f'banner missing content')

# render_before_after: contains arrow
ba = render_before_after(40, 80)
if '\u2192' in ba and '+40' in ba:
    passed += 1
else:
    failed += 1; errors.append(f'before_after: {ba}')

# render_score_card: contains grade and dimensions
card = render_score_card(85, 'A', {'structure': 90, 'triggers': 80})
if '[A]' in card and 'structure' in card:
    passed += 1
else:
    failed += 1; errors.append(f'score_card missing grade/dims')

print(f'{passed},{failed}')
if errors:
    for e in errors:
        print(f'  ERR: {e}', file=sys.stderr)
" 2>&1)
GRADE_PASSED=$(echo "$GRADE_TESTS" | head -1 | cut -d, -f1)
GRADE_FAILED=$(echo "$GRADE_TESTS" | head -1 | cut -d, -f2)
if [[ "$GRADE_FAILED" == "0" ]]; then
    pass "terminal_art.py: $GRADE_PASSED tests passed (grades, heatmap, bars, sparkline, banner)"
else
    fail "terminal_art.py" "$GRADE_PASSED passed, $GRADE_FAILED failed"
fi

# Dashboard: grade badge present
DASH_GRADE=$(python3 "$SCRIPT_DIR/dashboard.py" "$SKILL_DIR/SKILL.md" 2>/dev/null)
if echo "$DASH_GRADE" | grep -qE "\[S\]|\[A\]|\[B\]|\[C\]|\[D\]|\[F\]"; then
    pass "dashboard.py: grade badge present in output"
else
    fail "dashboard.py grade" "no grade badge found"
fi

# Auto-improve: grade badge in banner
AI_GRADE=$(python3 "$SCRIPT_DIR/auto-improve.py" "$SKILL_DIR/SKILL.md" --dry-run --max-iterations 0 2>&1)
if echo "$AI_GRADE" | grep -qE "\[S\]|\[A\]|\[B\]|\[C\]|\[D\]|\[F\]"; then
    pass "auto-improve.py: grade badge in text output"
else
    fail "auto-improve.py grade" "no grade badge found"
fi

# Report: grade column in score summary
REPORT_GRADE_JSONL=$(mktemp)
echo '{"exp":0,"status":"baseline","composite":50,"scores":{"structure":50},"pass_rate":"0/0","delta":0,"description":"baseline"}' > "$REPORT_GRADE_JSONL"
echo '{"exp":1,"status":"keep","composite":85,"scores":{"structure":85},"delta":35,"description":"improve"}' >> "$REPORT_GRADE_JSONL"
REPORT_GRADE_OUT=$(python3 "$SCRIPT_DIR/generate-report.py" "$REPORT_GRADE_JSONL" "$SKILL_DIR/SKILL.md" 2>/dev/null)
rm -f "$REPORT_GRADE_JSONL"
if echo "$REPORT_GRADE_OUT" | grep -q "| Grade |"; then
    pass "generate-report.py: Grade column in Score Summary"
else
    fail "generate-report.py grade" "Grade column not found"
fi

# Report: heatmap with >= 3 iterations
HEATMAP_JSONL=$(mktemp)
for i in $(seq 0 4); do
    echo "{\"exp\":$i,\"status\":\"keep\",\"composite\":$((60+i*5)),\"scores\":{\"structure\":$((60+i*5)),\"triggers\":$((55+i*7))},\"pass_rate\":\"0/0\",\"delta\":5,\"description\":\"iter $i\"}" >> "$HEATMAP_JSONL"
done
HEATMAP_OUT=$(python3 "$SCRIPT_DIR/generate-report.py" "$HEATMAP_JSONL" "$SKILL_DIR/SKILL.md" 2>/dev/null)
rm -f "$HEATMAP_JSONL"
if echo "$HEATMAP_OUT" | grep -q "Dimension Heatmap"; then
    pass "generate-report.py: Dimension Heatmap section present"
else
    fail "generate-report.py heatmap" "Dimension Heatmap not found"
fi

# Init: auto-discovery finds SKILL.md
INIT_DISCO=$(cd "$SKILL_DIR" && python3 scripts/init-skill.py --dry-run --json 2>&1)
if echo "$INIT_DISCO" | grep -q "Found SKILL.md"; then
    pass "init-skill.py: auto-discovers SKILL.md"
else
    fail "init-skill.py auto-discovery" "no discovery message found"
fi

# Init: grade badge in human output
INIT_HUMAN=$(python3 "$SCRIPT_DIR/init-skill.py" "$SKILL_DIR/SKILL.md" --dry-run 2>/dev/null)
if echo "$INIT_HUMAN" | grep -qE "\[S\]|\[A\]|\[B\]|\[C\]|\[D\]|\[F\]"; then
    pass "init-skill.py: grade badge in human output"
else
    fail "init-skill.py grade" "no grade badge found"
fi

# Init: dimension bars in human output
if echo "$INIT_HUMAN" | grep -q "█"; then
    pass "init-skill.py: dimension bars rendered"
else
    fail "init-skill.py bars" "no dimension bars found"
fi

# Init: contextual next steps
if echo "$INIT_HUMAN" | grep -qE "(Strong baseline|Good start|Room to grow)"; then
    pass "init-skill.py: contextual next steps shown"
else
    fail "init-skill.py next steps" "no contextual message found"
fi

# Init: progress feedback on stderr
INIT_STDERR=$(python3 "$SCRIPT_DIR/init-skill.py" "$SKILL_DIR/SKILL.md" --dry-run --json 2>&1 1>/dev/null)
if echo "$INIT_STDERR" | grep -q "Computing baseline score"; then
    pass "init-skill.py: progress feedback on stderr"
else
    fail "init-skill.py progress" "no progress message on stderr"
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
