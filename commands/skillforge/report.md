---
name: skillforge:report
description: >
  Generate a comprehensive improvement report for a skill that has been
  through one or more SkillForge improvement cycles. Summarizes baseline
  vs current scores, lists all kept improvements, identifies remaining
  gaps, and recommends next steps.
---

# /skillforge:report

Generate a post-improvement summary report.

## Instructions

1. Read `skillforge-results.tsv` from the skill directory.

2. Parse all iterations and compute:
   - Baseline scores (iteration 0)
   - Current best scores (latest kept iteration)
   - Total iterations run
   - Keep/discard/crash ratio
   - Per-dimension improvement delta

3. Generate the report:

```markdown
# SkillForge Improvement Report

## Skill: [name]
## Date: [today]
## Iterations: [N total] ([K kept] / [D discarded] / [C crashed])

### Score Summary

| Dimension | Baseline | Current | Delta |
|-----------|----------|---------|-------|
| Structure | XX | XX | +XX |
| Triggers | XX | XX | +XX |
| Quality | XX | XX | +XX |
| Edges | XX | XX | +XX |
| Efficiency | XX | XX | +XX |
| Composability | XX | XX | +XX |
| **Composite** | **XX** | **XX** | **+XX** |

### Kept Improvements (chronological)
1. [iteration] [commit] — [description] (+X.X)

### Remaining Gaps
- [dimension]: [specific issue still present]

### Recommendations
1. [highest-impact next improvement]
```

4. Save the report as `skillforge-report.md` in the skill directory.

5. If `present_files` is available, share the report with the user.
