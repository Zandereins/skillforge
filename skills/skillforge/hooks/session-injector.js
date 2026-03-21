#!/usr/bin/env node
/**
 * SkillForge Session Injector — Reads failures.jsonl and injects summary
 * as additionalContext when >=3 untriaged failures exist.
 *
 * Reads from stdin: {"session_id": "...", "cwd": "...", "type": "init"}
 * Outputs to stdout: {"additionalContext": "..."} or empty {}
 *
 * Failure log location: <cwd>/.skillforge/failures.jsonl (project-local)
 */

const fs = require("fs");
const path = require("path");

const MAX_FILE_SIZE = 1_000_000; // 1 MB
const MIN_UNTRIAGED = 3;
const MAX_FIELD_LEN = 120; // Sanitize fields to prevent prompt injection

function sanitize(value) {
  return String(value || "")
    .replace(/[\x00-\x1f\x7f]/g, " ") // ASCII control chars
    .replace(/[\u202A-\u202E\u2066-\u2069\u200F]/g, "") // Unicode bidi overrides
    .slice(0, MAX_FIELD_LEN);
}

function readFailures(failuresPath) {
  if (!fs.existsSync(failuresPath)) return [];

  let stat;
  try {
    stat = fs.statSync(failuresPath);
  } catch {
    return [];
  }
  if (!stat.isFile() || stat.size > MAX_FILE_SIZE) return [];

  const content = fs.readFileSync(failuresPath, "utf8");
  const entries = [];
  let skipped = 0;
  for (const line of content.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      entries.push(JSON.parse(trimmed));
    } catch {
      skipped++;
    }
  }
  if (skipped > 0) {
    process.stderr.write(
      `[skillforge] session-injector: skipped ${skipped} malformed JSONL lines\n`,
    );
  }
  return entries;
}

function markInjected(failuresPath, entries) {
  const lines = entries.map((e) => {
    if (!e.injected) e.injected = true;
    return JSON.stringify(e);
  });
  // Write to temp file then rename for atomicity
  const tmpPath = failuresPath + ".tmp";
  try {
    fs.writeFileSync(tmpPath, lines.join("\n") + "\n");
    fs.renameSync(tmpPath, failuresPath);
  } catch (err) {
    process.stderr.write(
      `[skillforge] session-injector: failed to mark injected: ${err.message}\n`,
    );
    // Clean up temp file if rename failed
    try {
      fs.unlinkSync(tmpPath);
    } catch {
      /* ignore */
    }
  }
}

function main() {
  let input = "";
  process.stdin.setEncoding("utf8");

  process.stdin.on("data", (chunk) => {
    input += chunk;
  });

  process.stdin.on("end", () => {
    let context = {};
    try {
      const data = JSON.parse(input);

      // Validate cwd: must be absolute and an existing directory
      const rawCwd = data.cwd || process.cwd();
      const resolvedCwd = path.resolve(rawCwd);
      if (
        !path.isAbsolute(resolvedCwd) ||
        !fs.existsSync(resolvedCwd) ||
        !fs.statSync(resolvedCwd).isDirectory()
      ) {
        process.stdout.write("{}");
        return;
      }

      const failuresPath = path.join(
        resolvedCwd,
        ".skillforge",
        "failures.jsonl",
      );

      const entries = readFailures(failuresPath);
      const untriaged = entries.filter((e) => !e.injected);

      if (untriaged.length >= MIN_UNTRIAGED) {
        // Cluster by skill + failure_type
        const clusters = {};
        for (const entry of untriaged) {
          const key = `${sanitize(entry.skill)}:${sanitize(entry.failure_type)}`;
          if (!clusters[key]) clusters[key] = { count: 0, examples: [] };
          clusters[key].count++;
          if (clusters[key].examples.length < 2) {
            clusters[key].examples.push(
              sanitize(entry.assertion_id || entry.description || "no details"),
            );
          }
        }

        let summary = `SkillForge: ${untriaged.length} untriaged failures detected.\n`;
        for (const [key, clusterData] of Object.entries(clusters)) {
          summary += `  - ${key}: ${clusterData.count} failures (e.g., ${clusterData.examples.join(", ")})\n`;
        }
        summary += `Run /skillforge:triage to investigate and auto-generate fixes.`;

        context = { additionalContext: summary };

        // Mark as injected
        markInjected(failuresPath, entries);
      }
    } catch (err) {
      process.stderr.write(
        `[skillforge] session-injector error: ${err.message}\n`,
      );
    }

    process.stdout.write(JSON.stringify(context));
  });
}

main();
