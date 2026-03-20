#!/bin/bash
##############################################################################
# SkillForge Self-Test — Verifies SkillForge Can Score Itself
#
# The ultimate dogfooding test: SkillForge runs its own eval pipeline
# against its own SKILL.md and verifies the results make sense.
#
# Usage: bash scripts/test-self.sh
#
# This script proves that:
# 1. The scorer correctly evaluates SkillForge's own SKILL.md
# 2. The eval suite passes against SkillForge's own content
# 3. The JSONL log integrates with progress.py
# 4. All dimensions are measurable and above threshold
# 5. The full pipeline works end-to-end
##############################################################################

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
PASS=0
FAIL=0
ERRORS=()

pass() { PASS=$((PASS + 1)); echo "  [PASS] $1"; }
fail() { FAIL=$((FAIL + 1)); ERRORS+=("$1"); echo "  [FAIL] $1"; }
section() { echo ""; echo "=== $1 ==="; }

TMPDIR_BASE=$(mktemp -d)
trap 'rm -rf "$TMPDIR_BASE"' EXIT

##############################################################################
section "Self-Score: SkillForge evaluates its own SKILL.md"
##############################################################################

SELF_SCORE=$(python3 "$SCRIPT_DIR/score-skill.py" "$SKILL_DIR/SKILL.md" --json 2>&1)

# All 6 base dimensions should be measurable
MEASURED=$(echo "$SELF_SCORE" | python3 -c "import sys,json; print(json.load(sys.stdin)['confidence']['measured'])" 2>/dev/null)
[[ "$MEASURED" == "6" ]] && pass "All 6 dimensions measured" || fail "Expected 6 dimensions, got $MEASURED"

# Composite should be >= 90 (SkillForge should practice what it preaches)
COMPOSITE=$(echo "$SELF_SCORE" | python3 -c "import sys,json; print(json.load(sys.stdin)['composite_score'])" 2>/dev/null)
python3 -c "exit(0 if float('$COMPOSITE') >= 90 else 1)" 2>/dev/null && \
    pass "Composite >= 90 (got $COMPOSITE)" || fail "Composite $COMPOSITE < 90"

# Each dimension should be >= 70
echo "$SELF_SCORE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for dim, score in d['dimensions'].items():
    if score < 70:
        print(f'LOW:{dim}={score}')
    else:
        print(f'OK:{dim}={score}')
" 2>/dev/null | while read -r line; do
    if [[ "$line" == LOW:* ]]; then
        fail "Dimension ${line#LOW:} below 70"
    else
        pass "Dimension ${line#OK:} >= 70"
    fi
done

# No warnings should be present
WARNINGS=$(echo "$SELF_SCORE" | python3 -c "import sys,json; w=json.load(sys.stdin)['warnings']; print(len(w))" 2>/dev/null)
[[ "$WARNINGS" == "0" ]] && pass "No scoring warnings" || fail "$WARNINGS warnings present"

##############################################################################
section "Self-Eval: Run eval suite against own SKILL.md"
##############################################################################

EVAL_RESULT=$(bash "$SCRIPT_DIR/run-eval.sh" "$SKILL_DIR/SKILL.md" "$SKILL_DIR/eval-suite.json" 2>/dev/null || true)

# Should produce valid JSON
echo "$EVAL_RESULT" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null && \
    pass "Eval produces valid JSON" || fail "Eval output is not valid JSON"

# Pass rate should be 100%
PASS_PCT=$(echo "$EVAL_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['pass_rate']['percentage'])" 2>/dev/null)
[[ "$PASS_PCT" == "100" ]] && pass "100% static assertion pass rate" || fail "Pass rate $PASS_PCT% (expected 100%)"

# Composite from eval should match standalone scorer
EVAL_COMP=$(echo "$EVAL_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['composite_score'])" 2>/dev/null)
python3 -c "exit(0 if abs(float('$EVAL_COMP') - float('$COMPOSITE')) < 1 else 1)" 2>/dev/null && \
    pass "Eval composite matches scorer ($EVAL_COMP ≈ $COMPOSITE)" || \
    fail "Eval composite $EVAL_COMP != scorer $COMPOSITE"

##############################################################################
section "Pipeline: run-eval.sh → JSONL → progress.py"
##############################################################################

PIPELINE_LOG="$TMPDIR_BASE/pipeline.jsonl"

# Simulate a 3-experiment session
echo '{"exp":0,"timestamp":"2026-01-01T00:00:00Z","commit":"base","scores":{"structure":80,"triggers":75,"quality":70,"edges":65,"efficiency":80,"composability":70},"pass_rate":"0/0","composite":73.5,"delta":0,"status":"baseline","strategy_type":null,"description":"baseline","duration_ms":0}' > "$PIPELINE_LOG"

# Run actual eval and log it
bash "$SCRIPT_DIR/run-eval.sh" "$SKILL_DIR/SKILL.md" "$SKILL_DIR/eval-suite.json" \
    --log "$PIPELINE_LOG" > /dev/null 2>/dev/null || true

# Progress.py should read both entries
PROG_RESULT=$(python3 "$SCRIPT_DIR/progress.py" "$PIPELINE_LOG" --json 2>&1)
TOTAL_EXPS=$(echo "$PROG_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['total_experiments'])" 2>/dev/null)
[[ "$TOTAL_EXPS" == "2" ]] && pass "Pipeline produces 2 experiments" || fail "Expected 2 experiments, got $TOTAL_EXPS"

# Baseline should be detected
HAS_BASELINE=$(echo "$PROG_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['baseline'] is not None)" 2>/dev/null)
[[ "$HAS_BASELINE" == "True" ]] && pass "Baseline detected from JSONL" || fail "Baseline not detected"

##############################################################################
section "Clarity: Self-measure instruction quality"
##############################################################################

CLARITY_RESULT=$(python3 "$SCRIPT_DIR/score-skill.py" "$SKILL_DIR/SKILL.md" --json --clarity 2>&1)
CLARITY_SCORE=$(echo "$CLARITY_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['dimensions']['clarity'])" 2>/dev/null)
python3 -c "exit(0 if int('$CLARITY_SCORE') >= 80 else 1)" 2>/dev/null && \
    pass "Clarity >= 80 (got $CLARITY_SCORE)" || fail "Clarity $CLARITY_SCORE < 80"

# No contradictions in own SKILL.md
CONTRADICTIONS=$(echo "$CLARITY_RESULT" | python3 -c "
import sys,json
d=json.load(sys.stdin)
c = d.get('details',{}).get('clarity',{}).get('contradictions',[])
print(len(c) if isinstance(c, list) else 0)
" 2>/dev/null)
[[ "$CONTRADICTIONS" == "0" ]] && pass "No contradictions in SKILL.md" || fail "$CONTRADICTIONS contradictions found"

##############################################################################
section "Regression Guard: SKILL.md line count"
##############################################################################

LINE_COUNT=$(wc -l < "$SKILL_DIR/SKILL.md" | tr -d ' ')
python3 -c "exit(0 if int('$LINE_COUNT') <= 280 else 1)" 2>/dev/null && \
    pass "SKILL.md <= 280 lines ($LINE_COUNT)" || fail "SKILL.md has $LINE_COUNT lines (max 280)"

python3 -c "exit(0 if int('$LINE_COUNT') >= 100 else 1)" 2>/dev/null && \
    pass "SKILL.md >= 100 lines ($LINE_COUNT)" || fail "SKILL.md suspiciously short ($LINE_COUNT lines)"

##############################################################################
# --- Summary ---
##############################################################################

echo ""
echo "============================================"
echo "  Self-Test: $PASS passed, $FAIL failed"
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

echo "  SkillForge practices what it preaches."
echo ""
exit 0
