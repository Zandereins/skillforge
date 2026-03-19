# SkillForge Deep Analysis Report

**Datum:** 19. März 2026
**Analysemethode:** 4 parallele Subagents (Architektur, Code-Qualität, Metriken, UX/Produkt)
**Gesamtaufwand:** ~355.000 Tokens, 71 Tool-Calls, ~8 Minuten parallele Analyse

---

## Executive Summary

SkillForge ist ein ambitioniertes Meta-Skill-Projekt mit einer überzeugenden Vision: Das Autoresearch-Pattern von Karpathy auf die Verbesserung von Claude Code Skills anwenden. Die Architektur ist durchdacht, die Dokumentation professionell und das Plugin-Format korrekt.

**Aber:** Die Analyse durch 4 spezialisierte Subagents deckt fundamentale Schwächen auf, die den Kern-Claim "autonomous improvement" untergraben. Die wichtigsten Erkenntnisse:

1. **Nur 3 von 6 Dimensionen sind messbar** — Quality, Edges und Composability geben `-1` zurück
2. **Trigger-Scoring ist naiv** — Simples Wort-Overlap statt semantischem Verständnis
3. **Efficiency-Metrik belohnt Aufblähung** — Mehr Headers = besserer Score (perverser Anreiz)
4. **Keine automatische Crash-Recovery** — Nur Prosa-Guidelines, kein Code
5. **Kein Onboarding** — User muss eval-suite manuell erstellen, bevor irgendetwas läuft

**Gesamtbewertung: 65/100** — Starke Vision, solide Struktur, aber die Scoring-Engine (das Herzstück) braucht fundamentale Überarbeitung.

---

## Teil 1: Kritische Bugs & Code-Probleme

### KRITISCH: JSON-Injection in analyze-skill.sh

**Datei:** `scripts/analyze-skill.sh`, Zeilen 137-154
**Problem:** Dateipfade werden unescaped in JSON-Output eingefügt. Pfade mit Anführungszeichen oder Backslashes brechen die JSON-Ausgabe.

```bash
# VORHER (kaputt):
cat <<EOF
{ "skill_path": "$SKILL_PATH", ... }
EOF

# NACHHER (sicher):
python3 -c "import json; print(json.dumps({'skill_path': '$SKILL_PATH', ...}))"
```

### HOCH: Example-Erkennung zählt Code-Blöcke als Examples

**Datei:** `scripts/analyze-skill.sh`, Zeile 74
**Problem:** `grep -ciE 'example|```'` zählt JEDES Code-Fence als "Beispiel". Ein Skill mit 3 Code-Blöcken und 0 echten Beispielen bekommt volle Punktzahl.

```bash
# VORHER:
EXAM_COUNT=$(echo "$CONTENT" | grep -ciE 'example|```' || true)

# NACHHER:
EXAM_COUNT=$(echo "$CONTENT" | grep -ciE '(example|input.*output|e\.g\.)' || true)
CODE_BLOCKS=$(echo "$CONTENT" | grep -c '```' || true)
COMBINED=$((EXAM_COUNT + CODE_BLOCKS / 3))
```

### HOCH: Description-Extraktion bricht bei bestimmten YAML-Formaten

**Datei:** `scripts/analyze-skill.sh`, Zeile 46
**Problem:** `sed -n '/^description:/,/^[a-z]/p'` bricht wenn das nächste YAML-Feld mit Großbuchstabe beginnt oder die Description ein Block-Scalar mit anderer Einrückung nutzt.

### HOCH: Duplicate Scoring Logic (Bash vs Python)

**Dateien:** `analyze-skill.sh` und `score-skill.py` (`_score_structure_inline`)
**Problem:** Zwei verschiedene Implementierungen des gleichen Scorings mit unterschiedlichen Punktwerten. Welche ist korrekt?

**Fix:** Bash-Script als Single Source of Truth, Python ruft es auf (bereits so im Hauptpfad, aber der Fallback weicht ab).

### MITTEL: TSV-Format ist fragil

**Problem:** Tabs in Descriptions brechen das Parsing. Newlines ebenso.
**Fix:** JSON-Lines (.jsonl) statt TSV, oder Description-Feld escapen.

### MITTEL: Keine Tests im gesamten Projekt

**Problem:** Zero Test Coverage. Kein einziger Unit-Test für die Scripts.
**Fix:** Minimaler Test-Suite: `test_analyze.sh`, `test_score.py` mit 3-5 Fixture-Skills.

---

## Teil 2: Scoring-System — Fundamentale Probleme

### Problem 1: Die 6 Dimensionen sind nicht orthogonal

| Dimension A | Dimension B | Überlappung |
|-------------|-------------|-------------|
| Structure | Token Efficiency | **HOCH** — beide messen Headers, Länge, Organisation |
| Edge Coverage | Output Quality | **MITTEL** — Edges sind ein Subset von Quality |
| Structure | Composability | **GERING** — gut strukturierte Skills sind automatisch kompatibler |

**Konsequenz:** Ein Improvement an der Struktur verbessert automatisch 2-3 andere Dimensionen. Das System zählt denselben Fortschritt mehrfach.

### Problem 2: Trigger-Scoring ist funktional kaputt

**Aktueller Algorithmus (score-skill.py, Zeile 151-158):**
```python
prompt_words = set(re.findall(r"\b\w{4,}\b", prompt))
desc_words = set(re.findall(r"\b\w{4,}\b", desc_lower))
overlap = len(prompt_words & desc_words)
would_trigger = overlap >= 2
```

**Warum das nicht funktioniert:**

| Szenario | Erwartung | Ergebnis | Problem |
|----------|-----------|----------|---------|
| Prompt: "Help me deploy" / Desc: "Do NOT use for deployment" | Nicht triggern | TRIGGER | Negation wird ignoriert |
| Prompt: "Set up database" / Desc: "Initialize data store" | Triggern | KEIN TRIGGER | Synonyme fehlen |
| Prompt mit "create", "help", "file" | Variiert | TRIGGER (fast immer) | Common words = Noise |

**Geschätzte Real-World-Genauigkeit: 40-60%.** Ein Münzwurf wäre kaum schlechter.

### Problem 3: Efficiency-Scoring belohnt das Falsche

**Aktuelle Formel:**
```
capabilities = headers + code_blocks/2 + examples + imperatives/3
words_per_capability = total_words / capabilities
```

**Perverser Anreiz:** Skill fügt 10 leere Headers hinzu → `capabilities` steigt → `words_per_capability` sinkt → **Score steigt**. Der Skill wird aufgebläht, nicht effizienter.

### Problem 4: Composite Score springt je nach verfügbaren Dimensionen

**Aktuelles Verhalten:** `compute_composite()` normalisiert Gewichte wenn Dimensionen `-1` sind. Das bedeutet:
- Gleicher Skill, nur Structure gemessen → Score X
- Gleicher Skill, Structure + Triggers gemessen → Score Y (anders)
- Die Zahlen sind nicht vergleichbar!

### Vorschlag: Überarbeitetes Scoring-System (v2)

**Von 6 auf 4 unabhängige Dimensionen reduzieren:**

| Dimension | Gewicht | Was sie misst | Automatisierbar? |
|-----------|---------|---------------|------------------|
| **Discoverability** | 0.30 | Trigger-Accuracy via Semantik | Teilweise (Embeddings) |
| **Correctness** | 0.35 | Output Quality + Edge Coverage | Nur mit Eval-Suite |
| **Efficiency** | 0.20 | Value/Token statt Structure/Tokens | Teilweise |
| **Composability** | 0.15 | Scope-Boundaries + Dependency-Clarity | Statisch ja |

---

## Teil 3: Architektur-Analyse

### Das Autonomie-Paradox

SkillForge verspricht: "Set a goal, start the loop, walk away."

**Realität:**
- 3 von 6 Dimensionen unmessbar → Loop optimiert nur halbe Wahrheit
- Die 3 messbaren Dimensionen (Structure, Triggers, Efficiency) sind korreliert → effektiv 1 unabhängige Variable
- Der Loop optimiert de facto **nur die Trigger-Description** (Synonyme hinzufügen) und **Struktur** (Headers hinzufügen)
- Quality/Edges/Composability brauchen Human Evaluation

**Vorschlag:** Ehrliches Reframing als "Agent-Assisted Improvement" statt "Autonomous". Das ist nicht weniger wertvoll — aber ehrlicher.

### Fehlende Crash-Recovery

**Aktueller Flow:**
```
1. Modify skill
2. git commit
3. Run eval suite
4. If better → keep, else → git revert
```

**Problem:** Wenn eval zwischen Schritt 2 und 4 crasht, bleibt ein unverified Commit im Repo. Die "Crash Recovery" in `improvement-protocol.md` ist nur Prosa (Markdown-Tabelle), kein Code.

**Vorschlag:** Atomic Transaction Wrapper:
```python
def run_iteration(skill_path, change):
    backup = git_hash()
    try:
        apply_change(skill_path, change)
        validate_yaml(skill_path)
        git_commit(f"skillforge: {change}")
        score = run_eval(skill_path)
        if score <= best_score:
            git_revert(backup)
            return "DISCARD"
        return "KEEP"
    except Exception:
        git_revert(backup)
        return "CRASH"
```

### Fehlende Integration mit skill-creator

**Claim:** "skill-creator builds v1, SkillForge grinds to production."
**Realität:** Kein shared Data-Format, kein Handoff-Protokoll, keine gemeinsamen Eval-Schemata.

**Vorschlag:** `HANDOFF.md` erstellen mit:
- Input-Contract (was skill-creator liefern muss)
- Quality-Gate (Minimum-Score für Handoff)
- Shared Eval-Suite Schema
- Git-State Requirements

---

## Teil 4: UX & Produkt-Lücken

### Fehlende Commands

| Command | Zweck | Impact |
|---------|-------|--------|
| `/skillforge:init` | Eval-Suite bootstrappen + erster Baseline | **HOCH** — größte Hürde für neue User |
| `/skillforge:status` | Echtzeit-Fortschritt während Loop | **HOCH** — "Walk away" braucht Sichtbarkeit |
| `/skillforge:undo N` | Letzte N Iterationen rückgängig | **MITTEL** — Sicherheitsnetz |
| `/skillforge:compare` | Visual Diff Baseline vs. Current | **MITTEL** — Ergebnis greifbar machen |

### Marketplace-Readiness: ~40%

**Probleme:**
- Kein Screenshot, kein Demo-Video, kein animiertes GIF
- Tagline "autoresearch for skills" spricht nur Insider an
- Kategorie "meta" existiert möglicherweise nicht im Marketplace
- Kein reales Before/After-Beispiel

**Bessere Tagline:** "Verbessere deine Claude Code Skills automatisch über Nacht — kein manuelles Tweaking nötig"

### Documentation Gaps

- Kein Troubleshooting-Guide
- Kein reales Beispiel (Before/After eines echten Skills)
- Kein Changelog
- CONTRIBUTING.md ohne Roadmap

---

## Teil 5: Priorisierte Verbesserungen

### Tier 1: Critical Fixes (Woche 1-2)

| # | Verbesserung | Impact | Effort | Details |
|---|-------------|--------|--------|---------|
| 1 | **JSON-Injection in analyze-skill.sh fixen** | Kritisch | Niedrig | jq oder Python für JSON-Output nutzen |
| 2 | **Example-Erkennung korrigieren** | Hoch | Niedrig | Code-Fences getrennt von echten Examples zählen |
| 3 | **Trigger-Scoring: TF-IDF statt Wort-Overlap** | Hoch | Mittel | sklearn TfidfVectorizer + cosine similarity |
| 4 | **Efficiency-Metrik: Info-Density statt Headers-Count** | Hoch | Mittel | Imperative Verbs / (Total Words - Noise) |
| 5 | **Honest Metrics Doc: 3/6 Dimensionen sind Placeholder** | Hoch | Niedrig | README + SKILL.md aktualisieren |

### Tier 2: Core Improvements (Woche 3-4)

| # | Verbesserung | Impact | Effort | Details |
|---|-------------|--------|--------|---------|
| 6 | **`/skillforge:init` Command** | Hoch | Mittel | Eval-Suite-Generator mit interaktiven Prompts |
| 7 | **Composability statisch implementieren** | Mittel | Mittel | Scope-Boundaries, Dependencies, Global-State checks |
| 8 | **Atomic Transaction Wrapper** | Hoch | Mittel | try/except um jede Loop-Iteration |
| 9 | **Tests hinzufügen** | Mittel | Mittel | 5-10 Fixture-Skills + pytest/bats |
| 10 | **TSV → JSONL Migration** | Mittel | Niedrig | Robusteres Logging-Format |

### Tier 3: Growth Features (Woche 5-8)

| # | Verbesserung | Impact | Effort | Details |
|---|-------------|--------|--------|---------|
| 11 | **Reales Before/After-Beispiel** | Hoch | Niedrig | Ein Skill durch 20 Iterationen, Ergebnisse zeigen |
| 12 | **Progress Dashboard** | Mittel | Mittel | HTML-Viewer für Score-Trends |
| 13 | **CI/CD-Integration** | Hoch | Mittel | GitHub Action die SkillForge bei Skill-Änderungen ausführt |
| 14 | **Skill-Creator Handoff-Protokoll** | Mittel | Niedrig | HANDOFF.md mit shared Schemas |
| 15 | **Marketplace-Overhaul** | Mittel | Niedrig | Neue Tagline, Screenshots, Kategorien |

### Tier 4: Competitive Moat (Woche 9+)

| # | Verbesserung | Impact | Effort | Details |
|---|-------------|--------|--------|---------|
| 16 | **Regression Testing** (Cross-Skill) | Hoch | Hoch | Detect wenn Skill A bricht wenn Skill B sich ändert |
| 17 | **Community Benchmark Database** | Hoch | Hoch | Anonyme Leaderboard, Vergleich mit anderen |
| 18 | **Multi-Skill Optimization** | Mittel | Hoch | Suite von Skills gemeinsam optimieren |
| 19 | **Smart Suggestions Engine** | Mittel | Mittel | "Dein Trigger fehlt deployment-Synonyme" |
| 20 | **Konfigurierbare Gewichte** | Niedrig | Niedrig | `.claude/skillforge-config.json` |

---

## Teil 6: Quick Wins (sofort umsetzbar)

Diese Verbesserungen kosten jeweils <30 Minuten und haben sofortigen Impact:

1. **README:** "walk away" durch "agent-assisted overnight improvement" ersetzen
2. **marketplace.json:** Tagline auf User-Benefit umschreiben
3. **plugin.json:** Dependencies deklarieren (python3, bash, git)
4. **analyze-skill.sh:** `set -euo pipefail` ist gut, aber JSON-Output mit jq absichern
5. **score-skill.py:** `compute_composite()` sollte warnen wenn >2 Dimensionen `-1` sind
6. **CONTRIBUTING.md:** Roadmap-Section mit den Top-5 gewünschten Features
7. **templates/:** `eval-suite-template.json` mit realistischeren Beispielen befüllen

---

## Fazit

SkillForge hat das richtige Konzept am richtigen Punkt: Die Idee, Karpathys Autoresearch auf Skill-Improvement anzuwenden, ist brillant. Das Problem ist nicht die Vision — es ist die Execution der Scoring-Engine.

**Der kritischste Pfad:**
Trigger-Scoring fixen → Efficiency-Metrik fixen → Placeholder-Dimensionen implementieren → Dann ist der autonome Loop tatsächlich autonomous.

Ohne diese Fixes optimiert der Loop im Wesentlichen nur Trigger-Descriptions und Header-Anzahl — was ironischerweise genau die Anti-Patterns erzeugt, die SkillForge selbst in `skill-patterns.md` beschreibt ("The Kitchen Sink", "The Chatty Instructor").

Die gute Nachricht: Die Architektur ist sauber genug, dass alle Fixes inkrementell machbar sind. Kein Rewrite nötig — nur gezielte Verbesserungen an den richtigen Stellen.
