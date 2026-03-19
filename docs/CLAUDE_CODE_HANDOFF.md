# SkillForge — Claude Code Handoff Prompt

Kopiere den folgenden Prompt in Claude Code (oder als CLAUDE.md ins Repo):

---

## Der Prompt

```
Du arbeitest am SkillForge Plugin — einem autonomen Skill-Improvement-System für Claude Code.
Repo: ~/skillforge (oder der aktuelle Pfad)

### Kontext — Was bereits passiert ist

In Cowork wurden 2 Verbesserungsrunden mit 5+ spezialisierten Subagents durchgeführt:

**Aktuelle Scores (gemessen):**
- Composite: 88.6 / 100 (vorher ~60)
- Structure: 90 (vorher 72)
- Efficiency: 83 (vorher ~45)
- Composability: 92 (vorher -1, war Placeholder)
- Triggers: TF-IDF-basiert, vorher naive Word-Overlap
- Quality & Edges: -1 (brauchen Runtime-Evals)

**Was gefixt wurde:**
1. JSON-Injection in analyze-skill.sh → sichere Python-Serialisierung
2. Trigger-Scoring → TF-IDF mit Stopwords + Negation-Erkennung
3. Effizienz-Metrik → Signal-to-Noise-Density statt bloat-rewarding
4. Composability → 5-Kriterien statische Analyse (war Placeholder)
5. Alle Referenzen TSV→JSONL vereinheitlicht
6. Neue Scripts: run-eval.sh, progress.py, init.md, JSONL-Templates
7. improvement-protocol.md: 9-Phasen mit Stuck-Protocol, Crash Recovery

**Dateien die geändert wurden (alle unstaged):**
- skills/skillforge/SKILL.md (komplett überarbeitet, 236 Zeilen)
- skills/skillforge/scripts/score-skill.py (komplett neu, TF-IDF + Composability)
- skills/skillforge/scripts/analyze-skill.sh (Security-Fix + bessere Example-Detection)
- skills/skillforge/scripts/run-eval.sh (NEU — unified eval runner)
- skills/skillforge/scripts/progress.py (NEU — Fortschritts-Tracking + ASCII Charts)
- skills/skillforge/references/improvement-protocol.md (9-Phasen, 768 Zeilen)
- skills/skillforge/references/metrics-catalog.md (aktualisiert)
- skills/skillforge/templates/eval-suite-template.json (bessere Trigger-Prompts)
- skills/skillforge/templates/improvement-log-template.jsonl (NEU, ersetzt TSV)
- commands/skillforge/init.md (NEU)
- commands/skillforge/eval.md (überarbeitet)
- commands/skillforge/bench.md (überarbeitet)
- commands/skillforge/analyze.md (überarbeitet)
- commands/skillforge/report.md (überarbeitet)
- skills/skillforge/history/ (NEU, Verzeichnis erstellt)
- README.md (aktualisiert)
- .claude-plugin/marketplace.json + plugin.json (aktualisiert)
- SKILLFORGE_FINAL_REPORT.md (Analysebericht)
- SKILLFORGE_DEEP_ANALYSIS.md (initiale Tiefenanalyse)

### Deine Aufgabe

Nutze das Superpowers-Plugin und arbeite mit mehreren Subagents parallel.
Starte mit einem sauberen Commit aller Änderungen, dann:

**Phase 1: Commit + Push**
- `git add` aller geänderten/neuen Dateien (NICHT die Report-MDs)
- Commit: "feat: SkillForge v2 — TF-IDF scoring, composability analysis, 9-phase protocol"
- Push zu GitHub

**Phase 2: Selbst-Verbesserung (Ralph-Loop)**
Führe `/skillforge:init` auf SkillForge selbst aus, dann starte den autonomen Loop:
- Goal: "Maximize SkillForge's own composite score to 95+"
- Metric: Composite score from `python3 scripts/score-skill.py SKILL.md --json`
- Verify: `python3 skills/skillforge/scripts/score-skill.py skills/skillforge/SKILL.md --json | python3 -c "import sys,json;print(json.load(sys.stdin)['composite_score'])"`
- Iterations: 20
- Time budget: 30 min

**Phase 3: Quality + Edges messbar machen**
Die zwei fehlenden Dimensionen (Quality, Edges) brauchen Runtime-Eval-Suites:
1. Generiere eine eval-suite.json für SkillForge selbst
2. Implementiere Quality-Tests (gibt SkillForge korrekte Empfehlungen?)
3. Implementiere Edge-Tests (Malformed SKILL.md, leere Dateien, Unicode-Pfade)
4. Re-run scoring mit allen 6 Dimensionen

**Phase 4: Plugin-Release vorbereiten**
- Cleanup: SKILLFORGE_DEEP_ANALYSIS.md und SKILLFORGE_FINAL_REPORT.md entfernen oder nach docs/ verschieben
- Version bump in plugin.json
- README.md mit finalen Scores aktualisieren
- Tag + Release auf GitHub

### Architektur-Hinweise
- Scoring: score-skill.py ist das Herzstück — TF-IDF für Triggers, Signal/Noise für Effizienz, statische Analyse für Composability
- Protocol: improvement-protocol.md definiert den 9-Phasen-Loop (Phase 0 SETUP bis Phase 9 STUCK)
- Format: JSONL für alle Logs, JSON für Configs, Bash+Python für Scripts
- Kein jq required (Python-Fallback überall)
- Autoresearch-Pattern: Constraint + Metric + Autonome Iteration = Compound Gains
```

---

## Alternativ: Als CLAUDE.md ins Repo

Wenn du den Kontext persistent machen willst, kopiere den Prompt-Block oben
in eine `CLAUDE.md` Datei im Root des Repos. Claude Code liest diese automatisch.
