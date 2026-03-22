# SkillForge Improvement Protocol — 9-Phase Loop Detail

This document describes the unified improvement loop that combines best practices from
Karpathy's autoresearch, Uditgoenka's generalized autoresearch, and Olelehmann's
skill-specific enhancements. The loop runs autonomously (no human confirmation) until
the goal is met or a stop condition occurs.

**Core principles:**
- One atomic change per iteration
- Fixed time budget per iteration (no hung experiments)
- User-defined goal + metric + verification, with defaults
- Binary assertions alongside continuous scoring
- Experiment numbering and grep-able logs
- History snapshots for diffing
- Automatic retry on crash (up to 2 retries)

---

## Phase 0: SETUP

Initialize the autonomous improvement session with user-provided configuration.

**Required inputs from user:**
1. **GOAL** (natural language): What should the skill achieve?
   - Example: "Handle CSV parsing with quoted fields and escaped quotes"
   - Example: "Improve trigger accuracy for data pipeline tasks"

2. **METRIC** (metric name): What measurement defines success?
   - Option A: Custom user-defined metric (name + verification command)
   - Option B: Use SkillForge defaults (structure, triggers, quality, edges, efficiency, composability)
   - Default metric if not specified: `total_score` (weighted across all 6 dimensions)

3. **VERIFY_COMMAND** (bash script or function call): How to measure progress?
   - Example: `bash scripts/analyze-skill.sh {skill_path}`
   - Example: `python3 eval/test-csv-parser.py {skill_path}`
   - Must exit with code 0 (success) or non-zero (failure)
   - Must output structured results (JSON, TSV, or simple key=value pairs)

4. **TIME_BUDGET** (seconds per iteration, default 300):
   - If any phase exceeds this, kill the experiment and treat as failure
   - Prevents hung evaluations from blocking the loop

5. **MAX_RETRIES** (default 2):
   - On crash/timeout, retry up to N times before discarding

6. **MAX_ITERATIONS** (default unlimited):
   - Stop after N iterations even if goal not met

**Setup phase actions:**
- Create `skillforge-session.json` with all config
- Initialize git branch: `git checkout -b skillforge-session-{timestamp}`
- Create `.skillforge/` directory for session artifacts
- Reserve `.skillforge/history/` for iteration snapshots
- Pre-validate that VERIFY_COMMAND works on baseline skill
- Print summary and confirm loop is ready to start

**Setup output:**
```json
{
  "session_id": "skillforge-20260319-143022",
  "goal": "Handle CSV parsing with quoted fields",
  "metric": "total_score",
  "verify_command": "bash scripts/analyze-skill.sh {skill_path}",
  "time_budget": 300,
  "max_retries": 2,
  "max_iterations": null,
  "baseline_score": 64.2,
  "timestamp": "2026-03-19T14:30:22Z"
}
```

---

## Phase 1: REVIEW

Read the current state and identify improvement opportunities.

**Actions:**
- Re-read SKILL.md in full (never assume state is cached)
- Re-read all reference files linked from SKILL.md
- Read git log: `git log --oneline -20`
- Load `skillforge-results.jsonl` and analyze score trends
- Load `.skillforge/experiment-log.txt` for recent attempts
- Identify which dimension (or custom metric) has most room for improvement

**Decision framework (for 6-dimension default):**

```
IF structure_score < 70 → fix structural issues first
ELIF trigger_score < 70 → improve trigger description
ELIF quality_score < 70 → add/improve examples and instructions
ELIF edge_score < 60 → add edge-case handling
ELIF efficiency_score < 75 → compress and optimize
ELSE → focus on lowest-scoring dimension
```

**For custom metrics:**
- Analyze trends in `skillforge-results.jsonl` for the user-defined metric
- Identify which code/content blocks correlate with metric improvements
- Look for patterns: which types of changes moved the metric most?

**Stopping condition check:**
- If 10 consecutive discards with zero metric improvement → stop, notify user
- If metric reached goal threshold → stop, celebrate
- If max_iterations reached → stop

**Special case: Dimension thrashing**
- If same dimension discarded 3+ times consecutively → switch to different dimension
- For custom metrics: rotate focus every 5 discards to avoid local minima

**Output:**
```
=== Phase 1: REVIEW (iteration 5) ===
Current structure: 68.5
Last change: [exp-004] Added 2 trigger synonyms
Trend: +2.1 pts in last 3 iterations
Focus dimension: triggers (lowest at 62.3)
Ready to ideate.
```

---

## Phase 2: IDEATE

Choose ONE specific, atomic change.

**Rules for atomic changes:**
- Expressible in a single sentence
- Affects exactly one aspect of the skill
- Testable (will move the metric)
- Reversible (clean `git revert` rollback)

**Good examples:**
- "Add 3 trigger synonyms to description for data pipeline tasks"
- "Add input/output example for CSV with quoted fields edge case"
- "Compress 20-line setup block to 4 lines of concise steps"
- "Fix frontmatter format: description field exceeds 200 chars"

**Bad examples (too broad):**
- "Rewrite the entire skill" — not atomic
- "Make it better" — not specific
- "Add lots of examples" — unbounded

**Ideation strategy (text-gradient-first):**
- Run `python3 scripts/text-gradient.py SKILL.md --json --top 5` to get ranked improvements
- Pick the highest-priority gradient that hasn't been tried in the last 3 iterations
- If all top gradients have been tried, fall back to manual ideation:
  - Look at recent discards: what assumptions did they violate?
  - Check git diff on recent keeps: what patterns worked?
  - If custom metric: find the highest-impact code blocks from Phase 1 analysis
  - For default metrics: use the decision framework from Phase 1

**Output:**
```
=== Phase 2: IDEATE (iteration 5) ===
Experiment: exp-005
Proposed change: Add "data pipeline", "workflow automation" to trigger description
Reasoning: Triggers score 62.3; these are common user phrasings from eval logs
Reversibility: Straightforward revert of description edit
Ready to modify.
```

---

## Phase 3: MODIFY

Apply the change to skill files.

**Pre-modification:**
- Set a timer (start time budget countdown)
- Record hash of SKILL.md before changes
- Pre-load ALL target files into context (never edit partially)

**Rules:**
- Only modify files within the target skill directory
- Preserve formatting conventions
- Maintain YAML frontmatter validity
- If adding reference files, add pointer from SKILL.md
- If removing content, verify no other files depend on it

**Frontmatter edits (high-risk):**
- The `description` field is the primary trigger mechanism
- Keep under 200 words (longer descriptions dilute matching)
- Include both what it does AND when to use it
- Include specific trigger phrases
- Include negative boundaries ("do NOT use for...")
- After edit, validate with: `python3 -c "import yaml; yaml.safe_load(open('SKILL.md'))" `

**Output:**
```
=== Phase 3: MODIFY (iteration 5) ===
Experiment: exp-005
Files modified:
  - SKILL.md (description field, +15 chars)
Changes:
  - Added "data pipeline, workflow automation" synonyms to description
  - Frontmatter valid: ✓
  - No dependencies broken: ✓
  - Time elapsed: 8 sec / 300 sec budget
Ready to commit.
```

---

## Phase 4: COMMIT

Save the change to git with experiment metadata.

**Commit format:**

```
experiment: exp-005 [dimension|metric] description

Experiment: exp-005
Dimension: triggers
Change: Add "data pipeline", "workflow automation" to trigger description
Goal: Improve trigger accuracy for domain-specific phrases
```

**Commit message guidelines:**
- First line: `experiment: exp-{NN} [dimension] one-sentence description`
- Add metadata in body (experiment number, dimension, goal)
- Enable filtering: `git log --grep="experiment:"`
- Sequential numbering essential for traceability

**Example commits:**
- `experiment: exp-001 [structure] validate frontmatter and add missing sections`
- `experiment: exp-042 [triggers] add deployment-related synonyms to description`
- `experiment: exp-083 [quality] add input/output example for CSV edge case`

**Commands:**
```bash
git add -A
git commit -m "experiment: exp-005 [triggers] Add data pipeline, workflow automation

Experiment: exp-005
Dimension: triggers
Gradient-ID: triggers:false_negatives:2
Change: Extended description with domain-specific trigger phrases
Goal: Improve trigger matching accuracy for real-world use cases"
```

**Gradient traceability:** When a gradient from `text-gradient.py` is applied, include
the `gradient_id` (format: `dimension:issue`) in the commit message trailer. This enables
tracking which gradients have high keep-rates via `strategy-log.jsonl`.

**Output:**
```
=== Phase 4: COMMIT (iteration 5) ===
Experiment: exp-005
Commit hash: a7f2d3e
Branch: skillforge-session-20260319-143022
Ready to verify.
```

---

## Phase 5: VERIFY

Run evaluation suite and measure the metric.

**Pre-verification:**
- Note current time (for timeout)
- Capture environment for reproducibility

**For default 6-dimension scoring:**

1. **Structure score** (automated):
   ```bash
   bash scripts/analyze-skill.sh /path/to/skill/SKILL.md
   ```
   Checks: YAML validity, required frontmatter fields, file organization

2. **Triggers score** (eval suite):
   - For each positive trigger test case: does skill load? Should be YES
   - For each negative trigger test case: does skill not load? Should be YES
   - Score = (correct decisions / total tests) × 100

3. **Quality score** (eval suite):
   - Execute skill per instructions
   - Validate output against expected results
   - Score = (passing assertions / total assertions) × 100

4. **Edge score**:
   - Test boundary conditions (empty input, max-size input, malformed input)
   - Score = (assertions pass / assertions fail) × 100

5. **Efficiency score**:
   - Line count, cyclomatic complexity, instruction clarity
   - Score = (efficiency metrics / targets) × 100

6. **Composability score**:
   - Does skill integrate cleanly with other skills?
   - References clear? Frontmatter unambiguous?

**For custom metrics:**
- Execute VERIFY_COMMAND
- Parse output (JSON, TSV, key=value)
- Extract the user-defined metric value
- Validate it's comparable to baseline

**Timeout handling (Karpathy's fixed time budget):**
- If verification phase exceeds TIME_BUDGET (default 300 sec):
  - Kill the evaluation process
  - Treat as crash/timeout
  - Log: `timeout exp-005 after 301 sec`
  - Advance to Phase 6 (DECIDE) with `status=timeout`
  - Don't mark as pass or fail; trigger retry logic

**Assertion handling (Olelehmann's binary eval):**
- Track both continuous scores AND pass/fail assertions
- Example: "Does skill output valid YAML? YES/NO"
- Pass rate = (assertions passed / total assertions) × 100
- Include pass rate in results alongside dimension scores

**Error handling:**
- YAML parse error: log error, don't fail; record structure_score=0
- Eval script crash: log error; advance to Phase 6 with `status=eval_error`
- Missing dependencies: skip that dimension; note in results

**Output:**
```
=== Phase 5: VERIFY (iteration 5) ===
Experiment: exp-005
Status: complete
Duration: 45 sec / 300 sec budget

Structure:     68.5 (YAML valid, all fields present)
Triggers:      65.2 (+3.1 from exp-004)
Quality:       72.1 (8/9 assertions pass)
Edges:         61.0 (3/5 edge cases pass)
Efficiency:    78.5 (234 lines, under target)
Composability: 72.0 (clear references)

Pass rate: 11/14 assertions (78.6%)
Total score: 69.7 (+0.9 from baseline 68.8)

Ready to decide.
```

---

## Phase 6: DECIDE

Compare new score against best-so-far and decide: KEEP or DISCARD.

**Decision table:**

| Condition | Action | Retry? |
|-----------|--------|--------|
| score_new > score_best | KEEP | N/A |
| score_new == score_best | DISCARD | No |
| score_new < score_best | DISCARD | No |
| timeout / crash | RETRY | Yes (up to max_retries) |
| eval_error | RETRY | Yes (up to max_retries) |

**Retry logic (Uditgoenka's feature):**
- On first crash/timeout: immediately retry (don't count as iteration)
- On second crash: retry once more
- On third crash: discard permanently; revert and log
- Track retry count: `exp-005_retry_1`, `exp-005_retry_2`

**Dimension-level decision:**
- If total score is flat, KEEP if:
  - Target dimension improved by 5+ points, AND
  - No other dimension regressed by more than 2 points

**Custom metric decision:**
- KEEP if metric moved closer to goal
- DISCARD if metric moved away
- If tied, check secondary metrics (dimensions) for tiebreaker

**On KEEP:**
- Advance skill files
- Continue to Phase 7 (LOG)

**On DISCARD:**
```bash
git revert HEAD --no-edit
git log --oneline -1  # Confirm revert
```

**On RETRY (crash/timeout):**
- Revert any partial modifications
- Re-run Phase 3 (MODIFY) again
- Re-run Phase 4 (COMMIT) with retry suffix
- Re-run Phase 5 (VERIFY)
- Return to Phase 6 (DECIDE) with new results
- Increment retry counter (max 2)

**Output:**
```
=== Phase 6: DECIDE (iteration 5) ===
Experiment: exp-005
Score: 69.7 (best so far: 68.8)
Delta: +0.9
Decision: KEEP
Target dimension triggers improved: 62.3 → 65.2 (+2.9)
No regressions > 2 points
Advancing skill to commit a7f2d3e
Ready to log.
```

---

## Phase 7: LOG

Record the iteration result and create history snapshot.

**Append to `skillforge-results.jsonl`:**

```jsonl
{"iteration": 5, "experiment": "exp-005", "commit": "a7f2d3e", "structure": 68.5, "triggers": 65.2, "quality": 72.1, "edges": 61.0, "efficiency": 78.5, "composability": 72.0, "pass_rate": "78.6", "total": 69.7, "delta": "+0.9", "status": "keep", "description": "Add data pipeline, workflow automation to triggers"}
```

**JSONL schema (one JSON object per line):**
- `iteration`: sequential iteration number (1, 2, 3...)
- `experiment`: exp-NNN identifier
- `commit`: git commit hash (first 7 chars)
- `structure`, `triggers`, `quality`, `edges`, `efficiency`, `composability`: scores
- `pass_rate`: assertion pass rate (X/Y)
- `total`: weighted composite score
- `delta`: change from previous best
- `status`: keep, discard, timeout, eval_error, retry
- `description`: one-line change summary

**Grep-able experiment log (`skillforge-experiment-log.txt`):**

```
[exp-005] 2026-03-19T14:35:22Z | status=keep | delta=+0.9 | description="Add data pipeline, workflow automation to triggers"
```

Format enables quick filtering:
```bash
grep "status=keep" .skillforge/experiment-log.txt
grep "delta=+" .skillforge/experiment-log.txt | awk -F'|' '{print $3}' | sort -t= -k2 -rn
```

**History snapshot (Olelehmann's feature):**

Save complete skill state at each kept iteration:
```bash
mkdir -p .skillforge/history/exp-005/
cp -r . .skillforge/history/exp-005/  # (exclude .git, .skillforge)
echo "exp-005 | 2026-03-19T14:35:22Z | score 69.7" > .skillforge/history/exp-005/METADATA.txt
```

Enables diffing between iterations:
```bash
diff -u .skillforge/history/exp-004/SKILL.md .skillforge/history/exp-005/SKILL.md
```

**Progress summary (every 10 iterations):**

```
=== SkillForge Progress Summary (iteration 50) ===
Session: skillforge-20260319-143022
Goal: Handle CSV parsing with quoted fields
Metric: total_score
Baseline: 64.2 → Current best: 78.5 (+14.3)

Keeps: 23 | Discards: 22 | Timeouts: 3 | Eval errors: 2
Keep rate: 46% | Average delta per keep: +0.62

Dimension progress:
  structure:     64.0 → 72.5 (+8.5)   [strongest improvement]
  triggers:      58.2 → 79.1 (+20.9)  [highest score]
  quality:       65.5 → 71.2 (+5.7)
  edges:         52.0 → 63.8 (+11.8)
  efficiency:    75.2 → 78.9 (+3.7)   [weakest improvement]
  composability: 68.0 → 76.5 (+8.5)

Last 10 decisions: keep, keep, discard, discard, keep, timeout, keep, discard, keep, keep

Next focus: efficiency (currently 78.9, has most room)
Experiments on efficiency: 6 keeps, 8 discards (75% discard rate)
```

**Output:**
```
=== Phase 7: LOG (iteration 5) ===
Experiment: exp-005
Result appended to skillforge-results.jsonl (entry 6)
History snapshot: .skillforge/history/exp-005/
Experiment log updated: [exp-005] status=keep delta=+0.9
Ready for iteration 6.
```

---

## Phase 8: REPEAT

Return to Phase 1 (REVIEW) for the next iteration.

**Loop continues until a stop condition:**

1. **Goal reached**: metric reaches user-defined threshold
   - Print: `=== Goal achieved! metric = {value} ==="
   - Finalize session
   - Exit cleanly

2. **Max iterations**: loop counter reaches `max_iterations`
   - Print: `=== Max iterations reached (N) ===`
   - Report best score and list top improvements
   - Exit cleanly

3. **User interrupt**: Ctrl+C received
   - Log graceful shutdown
   - Save all artifacts
   - Exit with code 0

4. **Plateau detected**: 10 consecutive discards with zero metric improvement
   - Print: `=== Plateau: 10 consecutive discards, no improvement ===`
   - Suggest manual review
   - Exit with code 1 (signal to user)

5. **Stuck protocol** (Phase 9, below)

**Output:**
```
=== Phase 8: REPEAT ===
Iteration 5 complete.
Advancing to iteration 6.
Status: progressing (current_best 69.7 > baseline 64.2)
```

---

## Phase 9: STUCK PROTOCOL

Triggered after 5 consecutive discards with zero metric improvement.

**Recovery steps:**

1. **Full re-read** (clear cached assumptions):
   - Re-read entire SKILL.md line-by-line
   - Re-read all reference files
   - Re-read eval suite test cases (if accessible)
   - Record observations in `.skillforge/debug-notes.txt`

2. **Analysis**:
   - Review full results log for patterns
   - Which change types worked? Which failed?
   - Which dimensions show progress? Which stuck?
   - Are there clusters of similar failed attempts?

3. **Combo strategy** (Uditgoenka feature):
   - Identify 2-3 near-miss changes that individually scored close
   - Design ONE change that combines their insights
   - Example: if "add examples" scored 68.4 and "compress instructions" scored 68.1,
     try "add examples AND make concise"

4. **Reversal strategy**:
   - Identify last 3 failed approaches
   - Try the opposite approach
   - If "add more detail" failed, try "remove clutter"
   - If "expand description" failed, try "tighten wording"

5. **Dimension switch**:
   - If stuck on same dimension for 5+ discards
   - Switch to completely different dimension
   - Force diversity: don't return to stuck dimension until others improve

6. **Escalation**:
   - If still stuck after 3 more discards post-recovery
   - Log detailed analysis to `.skillforge/stuck-analysis.md`
   - Notify user: `=== SkillForge stuck. Manual review recommended. ==="
   - Exit with status code 2

**Output:**
```
=== Phase 9: STUCK PROTOCOL (iteration 18) ===
Detected: 5 consecutive discards (exp-014 through exp-018)
Metric improvement: 0 points in last 5 iterations
Starting recovery...

Step 1: Full re-read [DONE]
Step 2: Pattern analysis [DONE]
  - Structure changes: 3 keeps, 2 discards (60% success)
  - Trigger changes: 2 keeps, 8 discards (20% success) [STUCK HERE]
  - Quality changes: 3 keeps, 1 discard (75% success)
  
Step 3: Combo strategy
  - Attempting hybrid of "add examples" + "clarify wording"
  - New experiment: exp-019
  
Resuming main loop...
```

---

## Error Handling & Crash Recovery

**YAML/frontmatter errors:**
- Log error, set structure_score = 0
- Repair YAML (fix formatting, validate syntax)
- Don't count repair as iteration
- Retry Phase 5 (VERIFY)

**Eval script crash:**
- Log full error message and traceback
- Check script syntax
- If fixable: fix and retry (up to 3 times total)
- If not fixable: skip that dimension, score others

**Git conflicts:**
- This should not occur; if it does:
  - Reset to last known good state: `git reset --hard HEAD~1`
  - Log incident
  - Retry from Phase 3 (MODIFY)

**Skill too large for context:**
- If SKILL.md exceeds token limit:
  - Split into SKILL.md + `references/detailed.md`
  - Add pointer in SKILL.md
  - Retry Phase 5 (VERIFY)

**Timeout (Phase 5):**
- Kill evaluation process
- Log timeout event
- Treat as recoverable error
- Trigger retry logic in Phase 6 (DECIDE)

---

## Session Artifacts

All created in `.skillforge/` directory:

- **`skillforge-session.json`** — Configuration and baseline (Phase 0)
- **`skillforge-results.jsonl`** — Iteration results (Phase 7, append each iteration as JSON line)
- **`skillforge-experiment-log.txt`** — Grep-able experiment log (Phase 7)
- **`history/exp-NNN/`** — Snapshot of skill at each kept iteration (Phase 7)
- **`debug-notes.txt`** — Observations during stuck recovery (Phase 9)
- **`stuck-analysis.md`** — Detailed analysis if recovery exhausted (Phase 9)

---

## Example: Full Loop Iteration

```
=== Iteration 5 ===

[Phase 0 - SETUP] (one-time, before loop)
  Session initialized with:
    goal="Handle CSV parsing with quoted fields"
    metric="total_score"
    time_budget=300 seconds
    baseline_score=64.2

[Phase 1 - REVIEW]
  Current score: 68.8
  Best dimension: triggers 65.2
  Worst dimension: edges 61.0
  Focus: triggers (last 3 attempts on structure, switching focus)

[Phase 2 - IDEATE]
  Proposed: Add "data pipeline", "workflow automation" to description
  Rationale: Common phrasings in eval logs

[Phase 3 - MODIFY]
  Modified: SKILL.md description field (+15 chars)
  Time: 8 sec

[Phase 4 - COMMIT]
  Hash: a7f2d3e
  Message: "experiment: exp-005 [triggers] Add data pipeline, workflow automation"

[Phase 5 - VERIFY]
  Duration: 45 sec / 300 sec budget
  Scores: struct=68.5, trig=65.2, qual=72.1, edge=61.0, eff=78.5, comp=72.0
  Pass rate: 11/14 (78.6%)
  Total: 69.7 (+0.9)

[Phase 6 - DECIDE]
  69.7 > 68.8 → KEEP

[Phase 7 - LOG]
  Results appended to TSV
  Snapshot saved to history/exp-005/
  Experiment log updated

[Phase 8 - REPEAT]
  Loop continues to iteration 6
```

---

## Performance Targets

For a well-tuned skill (target: all dimensions 90+):

- **Typical keeps**: 40–60% (rest are discards)
- **Average delta per keep**: +0.5 to +1.5 points
- **Plateau detection**: 10 consecutive no-progress discards
- **Time per iteration**: 1–5 minutes (Phase 3 + Phase 4 + Phase 5)
- **Typical session length**: 50–150 iterations to reach goal

---

## Configuration Reference

**Example `skillforge-session.json`:**

```json
{
  "session_id": "skillforge-20260319-143022",
  "goal": "Handle CSV parsing with quoted fields and escaped quotes",
  "metric": "total_score",
  "metric_threshold": 85,
  "verify_command": "bash scripts/analyze-skill.sh {skill_path}",
  "time_budget_seconds": 300,
  "max_retries": 2,
  "max_iterations": null,
  "skill_path": "/path/to/skill/",
  "git_branch": "skillforge-session-20260319-143022",
  "baseline_score": 64.2,
  "baseline_timestamp": "2026-03-19T14:22:00Z",
  "dimensions": ["structure", "triggers", "quality", "edges", "efficiency", "composability"],
  "dimension_weights": {
    "structure": 0.15,
    "triggers": 0.20,
    "quality": 0.20,
    "edges": 0.15,
    "efficiency": 0.10,
    "composability": 0.05,
    "runtime": 0.15
  }
}
```

---

## Quick Reference: Command Cheat Sheet

```bash
# Start a session
skillforge improve --goal "CSV parsing" --metric total_score --time-budget 300

# View results
cat .skillforge/skillforge-results.jsonl
grep "status=keep" .skillforge/skillforge-experiment-log.txt

# Analyze best experiments
grep "status=keep" .skillforge/skillforge-experiment-log.txt | \
  awk -F'|' '{print $3}' | sort -t= -k2 -rn | head -5

# View history diff
diff -u .skillforge/history/exp-010/SKILL.md .skillforge/history/exp-020/SKILL.md

# Check git experiments
git log --grep="experiment:" --oneline | head -20

# Stop current session (graceful)
# Press Ctrl+C

# Resume session from last iteration
skillforge resume --session-id skillforge-20260319-143022
```

---

## Glossary

- **Atomic change**: One focused modification, reversible with `git revert`
- **Dimension**: Evaluation category (structure, triggers, quality, edges, efficiency, composability)
- **Experiment**: One proposed change with unique exp-NNN identifier
- **Iteration**: One complete 9-phase cycle (Review → Ideate → Modify → Commit → Verify → Decide → Log → Repeat [→ Stuck])
- **Keep**: Decision to advance the change (score improved or dimension-level gain)
- **Discard**: Decision to revert the change (no progress or regression)
- **Retry**: Second/third attempt at a failed experiment (on crash/timeout)
- **Pass rate**: Fraction of assertions that passed (binary eval feature)
- **Plateau**: 10+ consecutive discards with no metric improvement; triggers stuck protocol
- **Metric**: User-defined or default measurement of skill quality
- **Time budget**: Max seconds allowed per iteration; exceeded → timeout
- **History snapshot**: Full skill state saved at each kept iteration for diffing
