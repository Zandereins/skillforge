#!/usr/bin/env node
/**
 * SkillForge Session Injector — Reads failures.jsonl and injects summary
 * as additionalContext when ≥3 untriaged failures exist.
 *
 * Reads from stdin: {"session_id": "...", "cwd": "...", "type": "init"}
 * Outputs to stdout: {"additionalContext": "..."} or empty {}
 *
 * Failure log location: .skillforge/failures.jsonl (project-local)
 */

const fs = require('fs');
const path = require('path');

const MAX_FILE_SIZE = 1_000_000; // 1 MB
const MIN_UNTRIAGED = 3;

function readFailures(failuresPath) {
  if (!fs.existsSync(failuresPath)) return [];

  const stat = fs.statSync(failuresPath);
  if (stat.size > MAX_FILE_SIZE) return [];

  const content = fs.readFileSync(failuresPath, 'utf8');
  const entries = [];
  for (const line of content.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      entries.push(JSON.parse(trimmed));
    } catch {
      // Skip malformed lines
    }
  }
  return entries;
}

function markInjected(failuresPath, entries) {
  // Rewrite file with injected: true on untriaged entries
  const lines = entries.map(e => {
    if (!e.injected) e.injected = true;
    return JSON.stringify(e);
  });
  fs.writeFileSync(failuresPath, lines.join('\n') + '\n');
}

function main() {
  let input = '';
  process.stdin.setEncoding('utf8');

  process.stdin.on('data', chunk => { input += chunk; });

  process.stdin.on('end', () => {
    let context = {};
    try {
      const data = JSON.parse(input);
      const cwd = data.cwd || process.cwd();
      const failuresPath = path.join(cwd, '.skillforge', 'failures.jsonl');

      const entries = readFailures(failuresPath);
      const untriaged = entries.filter(e => !e.injected);

      if (untriaged.length >= MIN_UNTRIAGED) {
        // Cluster by skill + failure_type
        const clusters = {};
        for (const entry of untriaged) {
          const key = `${entry.skill || 'unknown'}:${entry.failure_type || 'unknown'}`;
          if (!clusters[key]) clusters[key] = { count: 0, examples: [] };
          clusters[key].count++;
          if (clusters[key].examples.length < 2) {
            clusters[key].examples.push(entry.assertion_id || entry.description || 'no details');
          }
        }

        let summary = `SkillForge: ${untriaged.length} untriaged failures detected.\n`;
        for (const [key, data] of Object.entries(clusters)) {
          summary += `  - ${key}: ${data.count} failures (e.g., ${data.examples.join(', ')})\n`;
        }
        summary += `Run /skillforge:triage to investigate and auto-generate fixes.`;

        context = { additionalContext: summary };

        // Mark as injected
        markInjected(failuresPath, entries);
      }
    } catch {
      // Silent failure — hook should never block session
    }

    process.stdout.write(JSON.stringify(context));
  });
}

main();
