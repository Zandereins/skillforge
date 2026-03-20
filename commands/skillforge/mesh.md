---
name: mesh
description: Scan all installed skills for trigger overlap, broken handoffs, and scope collisions
---

# /skillforge:mesh — Skill Mesh Health Check

Scan all installed skills and report conflicts, overlaps, and broken handoffs.

## Steps

1. Run `python3 scripts/skill-mesh.py --json` from the SkillForge skill directory
2. Parse the JSON output
3. Present findings grouped by severity (critical → warning → info)
4. For each critical issue, suggest a concrete fix
5. Report the mesh health score

## Options

- `--skill-dirs DIR...` — Scan specific directories (default: `~/.claude/skills/`, `.claude/skills/`)
- `--severity warning` — Show only warnings and critical issues
- `--json` — Machine-readable output

## Example

```
/skillforge:mesh
Scanning ~/.claude/skills/ and .claude/skills/...

Mesh Health: 72/100
Skills found: 12
Issues: 3 critical, 2 warning, 1 info

[CRITICAL] Trigger overlap: deploy-skill <-> release-skill (87% similarity)
  → Merge these skills or add distinct negative boundaries

[WARNING] Broken handoff: testing-skill references 'lint-master' — not found
  → Did you mean 'linter'? Update the reference.
```
