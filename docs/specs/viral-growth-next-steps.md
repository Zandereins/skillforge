# SkillForge — Viral Growth: Next Steps

Status: PLAN (nicht gestartet)
Erstellt: 2026-03-22
Basiert auf: 5-Perspektiven Review (CEO, Dev Advocate, Security, Content Creator, OSS Maintainer)

---

## Phase 1: Social Proof (Prio 1 — diese Woche)

### 1.1 Beta-Tester akquirieren
- 5 Claude Code User finden (Discord, Reddit r/ClaudeAI, X)
- Ihnen `/skillforge:auto` auf ihre eigenen Skills laufen lassen
- Before/After Scores + 1-Satz Quote einsammeln
- Ergebnis: 3-5 Testimonials fuer README + Social Posts

### 1.2 Before/After Code-Diffs erstellen
- 3 echte Skills nehmen (deploy, code-review, testing)
- Vor/Nach-Patches als Side-by-Side zeigen
- Was genau hat SkillForge geaendert? (Frontmatter, Trigger-Keywords, Edge Cases)
- Format: Screenshot oder Markdown-Diff

### 1.3 "Share Your Results" GitHub Discussion
- GitHub Discussions aktivieren
- Pinned Thread: "Show your SkillForge score"
- Template verlinken (schon als Issue Template da)

---

## Phase 2: Content + Launch (Prio 2 — naechste Woche)

### 2.1 Twitter/X Thread (5 Tweets)
1. Problem-Statement (Skills driften, Maintenance nervt)
2. GIF: 56.9 → 99.9 in 18 Iterations
3. Before/After Code-Diff (konkreter Patch)
4. Doctor scanning 10+ Skills (Screenshot)
5. CTA + Testimonial-Quote + Link

### 2.2 Show HN Post
- Titel: "Show HN: SkillForge — Grind Claude Code Skills from [D] to [S] (Zero Human Input)"
- Timing: Dienstag 9am PT
- Text: Problem → Loesung → Proof → Try It

### 2.3 Reddit Posts
- r/ClaudeAI: "Built a tool that auto-improves Claude Code skills"
- r/Python: "Python CLI that scores and fixes SKILL.md files"

---

## Phase 3: Project Maturity (Prio 3 — Woche 3)

### 3.1 MAINTAINERS.md
- Primary: Franz Paul (@Zandereins)
- Decision process, merge SLA, release cadence

### 3.2 docs/ROADMAP.md
- v5.2: FAQ, Domain-spezifische Rubrics, Parallel Eval
- v6.0: Web Dashboard, Eval-Suite Marketplace, Team Features

### 3.3 SECURITY.md verlinken
- Im README unter Self-Score oder Contributing referenzieren
- Write-Path Confinement auf ~/.claude/ implementieren und testen

### 3.4 Dynamic CI Badges
- shields.io Endpoint von GitHub Actions Workflow
- Ersetzt hardcodierte Badges

---

## Phase 4: Platform-Features (Prio 4 — Monat 2)

### 4.1 Skill Certification Badges
- Oeffentliches Badge-System: `[![SkillForge Certified: S](badge)]`
- Registry-Idee: skills.skillforge.dev (spaeter)

### 4.2 Ecosystem Optimization
- `/skillforge:ecosystem` Command
- Trigger-Conflict-Map visuell
- Auto-generierte negative Boundaries

### 4.3 GitHub Action
- `Zandereins/skillforge-action@v5`
- Nightly Cron auf .claude/skills/**/*.md
- Auto-PR mit Report

---

## Erfolgskriterien

| Metrik | Ziel (30 Tage) | Ziel (90 Tage) |
|--------|----------------|----------------|
| GitHub Stars | 500+ | 5k+ |
| Wöchentliche Installs | 50+ | 500+ |
| Testimonials | 5+ | 20+ |
| Community Posts | 10+ | 50+ |
| HN Upvotes | 100+ | — |

---

## Naechste Aktion

→ Phase 1.1 starten: 5 Beta-Tester finden und ansprechen.
