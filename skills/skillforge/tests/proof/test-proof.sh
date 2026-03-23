#!/bin/bash
##############################################################################
# SkillForge — Real-World Proof Test
#
# Proves the scorer detects real problems (not just validates itself):
# 1. Score a deliberately bad skill → expect low score
# 2. Apply 3 known improvements → expect score increase
# 3. This validates the scorer measures structural defects, not just itself
#
# Usage: bash tests/proof/test-proof.sh
##############################################################################

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
SCORER="$SKILL_DIR/scripts/score-skill.py"
BAD_SKILL="$SCRIPT_DIR/bad-skill.md"
BAD_EVAL="$SCRIPT_DIR/bad-eval-suite.json"

PASS=0
FAIL=0
ERRORS=()

pass() { PASS=$((PASS + 1)); echo "  [PASS] $1"; }
fail() { FAIL=$((FAIL + 1)); ERRORS+=("$1: $2"); echo "  [FAIL] $1: $2"; }

# Create a temp copy we can modify
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT
cp "$BAD_SKILL" "$TMPDIR/SKILL.md"
cp "$BAD_EVAL" "$TMPDIR/eval-suite.json"

echo ""
echo "=== SkillForge Real-World Proof Test ==="
echo ""

# --- Step 1: Score the bad skill → expect low composite ---
echo "--- Step 1: Score deliberately bad skill ---"
RESULT1=$(python3 "$SCORER" "$TMPDIR/SKILL.md" --eval-suite "$TMPDIR/eval-suite.json" --json 2>&1)
SCORE1=$(echo "$RESULT1" | python3 -c "import sys,json; print(json.load(sys.stdin)['composite_score'])" 2>/dev/null)

if [[ -n "$SCORE1" ]] && python3 -c "import sys; exit(0 if float(sys.argv[1]) < 50 else 1)" "$SCORE1" 2>/dev/null; then
    pass "Bad skill scores low (composite=$SCORE1 < 50)"
else
    fail "Bad skill score" "expected < 50, got $SCORE1"
fi

# Check specific defects detected
ISSUES=$(echo "$RESULT1" | python3 -c "
import sys, json
d = json.load(sys.stdin)
all_issues = []
for dim, issues in d.get('issues', {}).items():
    all_issues.extend(issues)
print(len(all_issues))
" 2>/dev/null)
if [[ "$ISSUES" -ge 3 ]]; then
    pass "Multiple issues detected ($ISSUES issues)"
else
    fail "Issue detection" "expected >= 3 issues, got $ISSUES"
fi

# --- Step 2: Apply improvement 1 — add frontmatter ---
echo ""
echo "--- Step 2: Add frontmatter ---"
cat > "$TMPDIR/SKILL.md" <<'IMPROVED1'
---
name: bad-skill
description: >
  A skill about doing things. Helps with stuff. Do NOT use for brand-new
  skills from scratch.
---

This is a skill about doing things.

It helps with stuff. You might want to consider using it when you need help.

You should possibly try it out. It could maybe be useful for some tasks.

Remember to always test your code. Don't forget to save your files.

TODO: add more content here
FIXME: this section needs work
IMPROVED1

RESULT2=$(python3 "$SCORER" "$TMPDIR/SKILL.md" --eval-suite "$TMPDIR/eval-suite.json" --json 2>&1)
SCORE2=$(echo "$RESULT2" | python3 -c "import sys,json; print(json.load(sys.stdin)['composite_score'])" 2>/dev/null)

if python3 -c "import sys; exit(0 if float(sys.argv[1]) > float(sys.argv[2]) else 1)" "$SCORE2" "$SCORE1" 2>/dev/null; then
    pass "Frontmatter improves score ($SCORE1 → $SCORE2)"
else
    fail "Frontmatter improvement" "expected > $SCORE1, got $SCORE2"
fi

# --- Step 3: Apply improvement 2 — add headers + examples ---
echo ""
echo "--- Step 3: Add headers and examples ---"
cat > "$TMPDIR/SKILL.md" <<'IMPROVED2'
---
name: bad-skill
description: >
  A skill about doing things. Helps with stuff. Do NOT use for brand-new
  skills from scratch.
---

# Bad Skill

## When to Use

Use this skill when you need help doing things.

## Examples

Example 1: input → output

```bash
echo "hello world"
```

Example 2: another case

```bash
echo "goodbye world"
```

## Instructions

Run `python3 check.py` to validate.
IMPROVED2

RESULT3=$(python3 "$SCORER" "$TMPDIR/SKILL.md" --eval-suite "$TMPDIR/eval-suite.json" --json 2>&1)
SCORE3=$(echo "$RESULT3" | python3 -c "import sys,json; print(json.load(sys.stdin)['composite_score'])" 2>/dev/null)

if python3 -c "import sys; exit(0 if float(sys.argv[1]) > float(sys.argv[2]) else 1)" "$SCORE3" "$SCORE2" 2>/dev/null; then
    pass "Headers + examples improve score ($SCORE2 → $SCORE3)"
else
    fail "Headers + examples" "expected > $SCORE2, got $SCORE3"
fi

# --- Step 4: Apply improvement 3 — remove dead content, add scope ---
echo ""
echo "--- Step 4: Remove dead content, add scope ---"
cat > "$TMPDIR/SKILL.md" <<'IMPROVED3'
---
name: bad-skill
description: >
  A skill for improving task execution quality. Use when you need structured
  iteration on task output. Do NOT use for brand-new skills from scratch —
  use skill-creator first.
---

# Bad Skill — Task Execution Quality

## When to Use

Use this skill when task output needs systematic improvement.
Do not use for creating new skills from scratch.

## Examples

Example 1: input → output

```bash
echo "hello world"
```

Example 2: another case

```bash
echo "goodbye world"
```

## Instructions

Run `python3 check.py` to validate results.

Check `output.json` for execution metrics.

## Handoff

After improvement, hand off to `skill-creator` for new skill creation.
If task is crashing, suggest using `systematic-debugging` first.
IMPROVED3

RESULT4=$(python3 "$SCORER" "$TMPDIR/SKILL.md" --eval-suite "$TMPDIR/eval-suite.json" --json 2>&1)
SCORE4=$(echo "$RESULT4" | python3 -c "import sys,json; print(json.load(sys.stdin)['composite_score'])" 2>/dev/null)

if python3 -c "import sys; exit(0 if float(sys.argv[1]) > float(sys.argv[2]) else 1)" "$SCORE4" "$SCORE3" 2>/dev/null; then
    pass "Scope + cleanup improves score ($SCORE3 → $SCORE4)"
else
    fail "Scope + cleanup" "expected > $SCORE3, got $SCORE4"
fi

# --- Step 5: Verify total improvement is substantial ---
echo ""
echo "--- Step 5: Verify total improvement ---"
TOTAL_DELTA=$(python3 -c "import sys; print(round(float(sys.argv[1]) - float(sys.argv[2]), 1))" "$SCORE4" "$SCORE1" 2>/dev/null)
if python3 -c "import sys; exit(0 if float(sys.argv[1]) >= 15 else 1)" "$TOTAL_DELTA" 2>/dev/null; then
    pass "Total improvement >= 15 points ($SCORE1 → $SCORE4, delta=$TOTAL_DELTA)"
else
    fail "Total improvement" "expected >= 15 points, got delta=$TOTAL_DELTA ($SCORE1 → $SCORE4)"
fi

# --- Summary ---
echo ""
echo "============================================"
echo "  Proof Test: $PASS passed, $FAIL failed"
echo "  Score progression: $SCORE1 → $SCORE2 → $SCORE3 → $SCORE4"
echo "============================================"

if [[ $FAIL -gt 0 ]]; then
    echo ""
    echo "  Failures:"
    for err in "${ERRORS[@]}"; do
        echo "    - $err"
    done
    exit 1
fi

echo ""
exit 0
