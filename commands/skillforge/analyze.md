---
name: skillforge:analyze
description: >
  Deep analysis of an existing Claude Code skill. Examines structure,
  trigger description, examples, progressive disclosure, edge-case
  handling, and composability. Outputs a detailed report with actionable
  improvement recommendations ranked by impact.
---

# /skillforge:analyze

Perform a comprehensive analysis of the target skill.

## Instructions

1. Read the user's message to identify the target skill path.
   If not provided, ask: "Which skill should I analyze? Give me the path to its SKILL.md."

2. Read the SKILL.md file completely.

3. If a `references/` directory exists, list its contents and read each file.

4. Run the structural analysis:
   ```bash
   bash /path/to/skillforge/scripts/analyze-skill.sh /path/to/target/SKILL.md
   ```

5. Score each dimension manually:
   - **Structure**: Frontmatter, headers, length, examples, progressive disclosure
   - **Trigger accuracy**: Is the description specific enough? Does it include synonyms?
   - **Output quality**: Do the instructions produce correct results?
   - **Edge coverage**: Does it handle errors, missing input, ambiguity?
   - **Token efficiency**: Any redundancy, hedging, or unnecessary explanations?
   - **Composability**: Scope boundaries, handoff points, conflict risk

6. Present findings as a structured report:

```
## SkillForge Analysis: [skill-name]

### Composite Score: XX/100

| Dimension | Score | Key Finding |
|-----------|-------|-------------|
| Structure | XX | ... |
| Triggers | XX | ... |
| Quality | XX | ... |
| Edges | XX | ... |
| Efficiency | XX | ... |
| Composability | XX | ... |

### Top 3 Improvements (by impact)
1. ...
2. ...
3. ...

### Detailed Findings
[per-dimension breakdown]
```

7. Offer to run `/skillforge` to start the autonomous improvement loop.
