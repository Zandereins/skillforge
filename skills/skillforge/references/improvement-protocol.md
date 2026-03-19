# Improvement Protocol — 8-Phase Loop Detail

This document describes each phase of the SkillForge autonomous improvement loop.
The loop runs indefinitely (or for N iterations) and makes ONE atomic change per cycle.

## Phase 1: REVIEW

Read the current state of the target skill:

- Re-read SKILL.md (it may have changed from previous iteration)
- Review git log for recent kept/discarded changes
- Read `skillforge-results.tsv` for score trends
- Identify which dimension has the most room for improvement

**Decision framework for what to improve next:**

```
IF structure_score < 70 → fix structural issues first
ELIF trigger_score < 70 → improve trigger description
ELIF quality_score < 70 → add/improve examples and instructions
ELIF edge_score < 60 → add edge-case handling
ELIF efficiency_score < 75 → compress and optimize
ELSE → focus on lowest-scoring dimension
```

After 3+ consecutive discards on the same dimension, switch to a different dimension.

## Phase 2: IDEATE

Choose ONE specific change. The change must be:

- **Atomic**: Expressible in a single sentence
- **Testable**: Will move at least one eval metric
- **Reversible**: Can be cleanly reverted via `git revert`

Good changes:
- "Add 3 trigger synonyms for the skill description"
- "Add an input/output example for the edge case of empty input"
- "Move the API reference section to references/api.md"
- "Replace 15-line verbose instruction block with 4-line concise version"

Bad changes (too broad):
- "Rewrite the entire skill" — not atomic
- "Make it better" — not specific
- "Add lots of examples" — not one change

## Phase 3: MODIFY

Apply the change to the skill files.

**Rules:**
- Only modify files inside the target skill directory
- Preserve existing formatting conventions
- Maintain YAML frontmatter integrity (validate after edit)
- If adding a reference file, add a clear pointer from SKILL.md
- If removing content, ensure nothing else depends on it

**Frontmatter edits (high-risk):**
The `description` field in frontmatter is the primary trigger mechanism.
Changes here directly affect when the skill activates. Be precise:
- Include both what the skill does AND when to use it
- Add specific trigger phrases users might say
- Include negative boundaries ("do NOT use for X")
- Keep under ~200 words — too long dilutes matching

## Phase 4: COMMIT

```bash
git add -A
git commit -m "skillforge: [dimension] [one-sentence description]"
```

Commit BEFORE running verification. This ensures clean rollback.

Commit message format:
```
skillforge: [structure|triggers|quality|edges|efficiency|composability] description
```

Examples:
- `skillforge: triggers add deployment-related synonyms to description`
- `skillforge: quality add input/output example for CSV parsing edge case`
- `skillforge: efficiency compress setup instructions from 20 to 8 lines`

## Phase 5: VERIFY

Run the evaluation suite against the modified skill.

**Structural scoring** (automated):
```bash
bash scripts/analyze-skill.sh /path/to/skill/SKILL.md
```

**Trigger scoring** (requires eval suite):
For each test prompt in the eval suite:
1. Would Claude load this skill for this prompt? (positive triggers should → yes)
2. Would Claude avoid loading this skill? (negative triggers should → yes)
3. Score = correct decisions / total test prompts × 100

**Output quality scoring**:
For each test case with expected output:
1. Follow the skill instructions to complete the task
2. Check assertions against the output
3. Score = passing assertions / total assertions × 100

**Composite score calculation:**
```
total = (structure × 0.15) + (triggers × 0.25) + (quality × 0.25)
      + (edges × 0.15) + (efficiency × 0.10) + (composability × 0.10)
```

Trigger accuracy and output quality are weighted highest because they
have the most direct impact on user experience.

## Phase 6: DECIDE

Compare the new total score against the previous best:

| Condition | Action |
|-----------|--------|
| total_new > total_prev | **KEEP** — advance the branch |
| total_new == total_prev | **DISCARD** — no improvement, revert |
| total_new < total_prev | **DISCARD** — regression, revert |
| Eval crashed | **FIX** — attempt fix (max 3 tries), then revert |

On DISCARD:
```bash
git revert HEAD --no-edit
```

On dimension-specific improvements:
Even if the total score is flat, KEEP if the target dimension improved by 5+
AND no other dimension regressed by more than 2.

## Phase 7: LOG

Append one row to `skillforge-results.tsv`:

```tsv
iteration	commit	structure	triggers	quality	edges	efficiency	composability	total	delta	status	description
```

Every 10 iterations, print a progress summary:
```
=== SkillForge Progress (iteration 20) ===
Baseline: 64.2 → Current best: 78.5 (+14.3)
Keeps: 8 | Discards: 10 | Crashes: 2
Strongest: triggers 85 (+27) | Weakest: edges 55 (+15)
Last 5: keep, discard, discard, keep, keep
```

## Phase 8: REPEAT

Go to Phase 1. Continue until:
- User interrupts (Ctrl+C)
- N iterations reached (if bounded)
- All dimensions score 90+ (goal achieved)
- 10 consecutive discards with no dimension improvement (plateau — notify user)

## Crash Recovery

| Failure | Response |
|---------|----------|
| YAML parse error in SKILL.md | Fix frontmatter immediately, don't count as iteration |
| Eval script fails | Check script syntax, fix, retry (max 3 times) |
| Git conflict | Reset to last known good state |
| Skill too large for context | Split into SKILL.md + references, retry |
| External dependency missing | Skip that eval, score remaining dimensions |

## Stuck Protocol

After 5 consecutive discards:

1. Re-read ALL files from scratch (clear cached assumptions)
2. Review full results log — find patterns in what worked vs didn't
3. Try combining two near-miss changes that individually scored close
4. Try the OPPOSITE of the last 3 failed approaches
5. Switch to a completely different dimension
6. If still stuck after 3 more discards → notify user, suggest manual review
