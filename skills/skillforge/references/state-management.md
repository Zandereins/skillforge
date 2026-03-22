# SkillForge State Management

SkillForge stores state across four locations with different scopes and lifetimes.

## State Locations

### Per-Skill State (`<skill_dir>/.skillforge/`)

Files created during improvement iterations for a specific skill:

| File | Purpose | Created By |
|------|---------|------------|
| `auto-improve-state.jsonl` | Iteration state, scores, decisions | `auto-improve.py` |
| `snapshots/exp-NNN.md` | SKILL.md snapshots per experiment | improvement loop |
| `failures.jsonl` | Logged failures during evaluation | `log-failure` command |

### Per-Skill Results (`<skill_dir>/skillforge-results.jsonl`)

Append-only log of experiment results. Each line is a JSON object:
```json
{"exp": 0, "timestamp": "...", "trigger": "init", "composite_score": 72, "pass_rate": "5/8", "scores": {...}}
```

### Per-Project State (`<project>/.skillforge/`)

Project-scoped files shared across all skills in a project:

| File | Purpose | Created By |
|------|---------|------------|
| `failures.jsonl` | Failure log surfaced by session hook | `session-injector.js` |

### Global Meta-Learning (`~/.skillforge/meta/`)

Cross-project learning data that persists across all SkillForge sessions:

| File | Purpose | Size Cap |
|------|---------|----------|
| `episodes.jsonl` | Cross-session strategy memory | 10 MB |
| `calibrated-weights.json` | Learned scoring weights | N/A (small) |
| `calibration-log.jsonl` | Scoring calibration history | 10 MB |
| `strategy-log.jsonl` | Strategy effectiveness data | 10 MB |

## Cleanup

To purge all global meta-learning data:
```bash
rm -rf ~/.skillforge/meta/
```

To reset a specific skill's improvement state:
```bash
rm -rf <skill_dir>/.skillforge/
rm -f <skill_dir>/skillforge-results.jsonl
```
