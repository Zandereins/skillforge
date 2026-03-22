---
name: skillforge:eval
description: >
  Run the unified evaluation suite against a skill combining 6-dimension scoring
  with binary assertions. Produces pass rates and composite quality scores.
---

# /skillforge:eval

Comprehensive skill evaluation combining metric scoring and binary test assertions.

## Overview

The eval system operates in two modes that can be combined:

1. **Dimension Scoring** (6 dimensions)
   - `structure`: Code organization, headers, examples (0-100)
   - `triggers`: Prompt matching accuracy using eval suite (0-100)
   - `efficiency`: Token efficiency and information density (0-100)
   - `composability`: Interplay with other skills (0-100)
   - `quality`: Output quality against test assertions (0-100)
   - `edges`: Edge case handling (0-100)

2. **Binary Assertions** (pass/fail)
   - Defined in the eval suite JSON
   - Run against actual skill outputs
   - Produce pass rate: X/Y assertions (percentage)

The `composite_score` is a weighted average of measured dimensions. The `pass_rate` 
tracks binary assertion success independently.

## Usage

```
/skillforge:eval <skill_path> [--quick] [--compare BASELINE] [--timeout SECONDS]
```

### Arguments

- `<skill_path>`: Path to SKILL.md (required)
- `--quick`: Run assertions only, skip dimension scoring (faster, ~30s vs ~120s)
- `--compare BASELINE_FILE`: Show delta from baseline results JSON
- `--timeout SECONDS`: Timeout for the entire eval (default: 300)

### Examples

#### Standard evaluation (all dimensions + assertions)
```
/skillforge:eval .claude/skills/my-skill/SKILL.md
```

#### Quick pass/fail check
```
/skillforge:eval .claude/skills/my-skill/SKILL.md --quick
```

#### Compare to previous run
```
/skillforge:eval .claude/skills/my-skill/SKILL.md --compare .skillforge-eval/exp-15.json
```

#### With custom timeout
```
/skillforge:eval .claude/skills/my-skill/SKILL.md --timeout 600
```

## Instructions

### 1. Identify the skill and its eval suite

Read the SKILL.md to extract the skill name and location.

Look for `eval-suite.json` in the skill directory:
```bash
ls <skill_dir>/eval-suite.json
```

If no eval suite exists, offer to generate one from the template:
```
Would you like me to generate an eval suite from the template?
I'll create triggers, test cases, and edge cases for <skill_name>.
```

If the user approves, copy the eval-suite-template.json and customize it for the skill.

### 2. Run the Python scorer (unless --quick mode)

```bash
python3 scripts/score-skill.py <SKILL.md> --eval-suite <eval-suite.json> --json
```

This produces:
- `composite_score` (weighted average, 0-100)
- `dimensions` (per-dimension breakdown)
- `confidence` (how many dimensions were measured)

**Note:** Some dimensions (`quality`, `edges`) require runtime eval. If unmeasured, 
the confidence will be lower. Static dimensions that always work:
- `structure` (code organization)
- `triggers` (description matching)
- `efficiency` (token efficiency)
- `composability` (scoping and handoff points)

### 3. Run binary assertions (unless --quick is not used)

For each test case in the eval suite:

```json
{
  "id": "tc-1",
  "prompt": "User request",
  "input_files": [],
  "assertions": [
    {"type": "contains", "value": "text", "description": "..."},
    {"type": "pattern", "value": "regex", "description": "..."},
    {"type": "excludes", "value": "text", "description": "..."}
  ]
}
```

**For each test case:**

1. Follow the skill's instructions with the given `prompt`
2. Capture the output (including file changes, console output, etc.)
3. Run each assertion against the output:
   - `contains`: Output includes the value (case-insensitive substring match)
   - `pattern`: Output matches the regex (case-insensitive)
   - `excludes`: Output does NOT include the value
   - `json_path`: Extract value at JSON path and compare
4. Record: `{test_case, assertion, passed, evidence}`

**Edge cases:** Also run these separately:

```json
{
  "id": "ec-1",
  "prompt": "User request",
  "category": "category_name",
  "expected_behavior": "What should happen",
  "assertions": [...]
}
```

Edge cases stress-test error handling and boundary conditions.

### 4. Produce unified results

Use `/skillforge:eval`'s internal runner (`run-eval.sh`), which orchestrates:
- Python scorer
- Binary assertion runner
- Results compilation

Output JSON structure:
```json
{
  "experiment_id": 42,
  "skill_name": "my-skill",
  "skill_path": "/path/to/SKILL.md",
  "timestamp": "2026-03-19T15:30:45Z",
  "pass_rate": {
    "passed": 8,
    "total": 10,
    "percentage": 80
  },
  "dimension_scores": {
    "structure": 85,
    "triggers": 92,
    "efficiency": 78,
    "composability": 88,
    "quality": -1,
    "edges": -1
  },
  "composite_score": 85.3,
  "binary_results": [
    {
      "test_case": "tc-1",
      "assertion_type": "contains",
      "assertion_desc": "Report includes structure dimension",
      "passed": true,
      "evidence": "Found 'structure' in output"
    },
    ...
  ]
}
```

### 5. Display results in tabular format

Print results as:

```
╔═════════════════════════════════════════════════════════════════╗
║                   SkillForge Eval Results                       ║
║                     [Experiment #42]                            ║
╠═════════════════════════════════════════════════════════════════╣
║  Skill: my-skill (dev)                                          ║
║  Time: 2026-03-19 15:30:45 UTC                                  ║
╠═════════════════════════════════════════════════════════════════╣

DIMENSION SCORES
  ✓ structure        85/100  (well organized)
  ✓ triggers         92/100  (high accuracy)
  ✓ efficiency       78/100  (could trim 200 words)
  ✓ composability    88/100  (clear scope boundaries)
  ◆ quality          ━ (requires runtime eval)
  ◆ edges            ━ (requires runtime eval)

COMPOSITE SCORE:     85.3/100  [4/6 dimensions measured]

BINARY ASSERTIONS
  Pass rate:         8/10  (80%)
  ✓ tc-1.a1          Contains "structure" in output
  ✓ tc-1.a2          Matches pattern \\d+/100
  ✗ tc-2.a1          Excludes placeholder text (found 3 TODOs)
  ✓ tc-3.a1          JSON path report.triggers exists
  ...

IMPROVEMENT TRACKING
  Previous run:      78/100 (exp #41, 2026-03-19 15:15:12)
  Delta:             +7 pts  ✓ IMPROVED

RECOMMENDATIONS
  • Reduce verbosity in examples (add -250 words for +5 pts)
  • Add 2 more edge case tests (currently 4, suggest 6)
  • Consider adding progressive disclosure with /references
```

### 6. Save results and tracking

Results are saved to:
- **JSON**: `.skillforge-eval/exp-<N>.json` (full details)
- **JSONL log**: `.skillforge-eval/results.jsonl` (one line per run, for graphing)

The results log format (JSONL):
```jsonl
{"experiment_id": 42, "skill_name": "my-skill", "pass_rate": 80, "composite_score": 85.3, "timestamp": "2026-03-19T15:30:45Z"}
{"experiment_id": 43, "skill_name": "my-skill", "pass_rate": 85, "composite_score": 86.8, "timestamp": "2026-03-19T15:45:20Z"}
```

### 7. Handle --compare baseline

If `--compare` is provided:

1. Load the baseline JSON file
2. Compute deltas for all metrics:
   - Dimension score changes (per-dimension)
   - Pass rate change (e.g., 70% → 80%)
   - Composite score change
3. Show in results with color/symbols:
   - `✓` = improved
   - `═` = unchanged
   - `✗` = regressed

Example:
```
COMPARISON TO BASELINE [exp #38]

  composite_score:   82.1 → 85.3  (+3.2)  ✓
  pass_rate:         75% → 80%    (+5)    ✓
  structure:         80 → 85      (+5)    ✓
  triggers:          90 → 92      (+2)    ✓
  efficiency:        75 → 78      (+3)    ✓
  composability:     85 → 88      (+3)    ✓
```

## Tips

- **Quick iterations**: Use `--quick` mode during skill development (assertions only).
- **Full validation**: Run the full eval before committing improvements.
- **Baseline tracking**: Save a baseline after each major improvement, then use 
  `--compare` to verify that refactoring didn't regress quality.
- **Minimal evals**: A skill with just 3-4 positive triggers + 2-3 test cases is 
  usually enough to catch regressions.
- **Timeout strategy**: Set `--timeout 600` for complex skills with many assertions 
  (default 300s is usually sufficient).

