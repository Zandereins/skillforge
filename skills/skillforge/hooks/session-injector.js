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
  return (
    String(value || "")
      .replace(/[\x00-\x1f\x7f]/g, " ") // ASCII control chars
      .replace(/[\u200B-\u200F\u202A-\u202E\u2060-\u2069\uFEFF\u00AD]/g, "") // Unicode bidi, zero-width, and invisible chars
      // Strip XML-like tags and prompt injection markers
      .replace(/<\/?[a-zA-Z][^>]*>/g, "")
      .replace(/\b(Human|Assistant|System)\s*:/gi, "")
      .replace(/<\/?system[^>]*>/gi, "")
      .slice(0, MAX_FIELD_LEN)
  );
}

function stripProto(obj, depth = 0) {
  if (depth > 10 || obj === null || typeof obj !== "object") return obj;
  delete obj["__proto__"];
  delete obj["constructor"];
  delete obj["prototype"];
  for (const k of Object.keys(obj)) {
    if (typeof obj[k] === "object" && obj[k] !== null)
      stripProto(obj[k], depth + 1);
  }
  return obj;
}

function readFailures(failuresPath) {
  // Single try/catch eliminates TOCTOU race (existsSync+statSync+readFileSync)
  let content;
  try {
    content = fs.readFileSync(failuresPath, "utf8");
  } catch {
    return []; // File doesn't exist or is unreadable
  }

  // Size check after read (content already in memory)
  if (content.length > MAX_FILE_SIZE) return [];

  const entries = [];
  let skipped = 0;
  for (const line of content.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      entries.push(stripProto(JSON.parse(trimmed)));
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

function acquireLock(failuresPath) {
  const lockPath = failuresPath + ".lock";
  try {
    fs.mkdirSync(lockPath); // mkdir is atomic on all platforms
    return true;
  } catch {
    return false;
  }
}

function releaseLock(failuresPath) {
  const lockPath = failuresPath + ".lock";
  try {
    fs.rmdirSync(lockPath);
  } catch {
    /* ignore — lock may already be gone */
  }
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

  const MAX_STDIN_SIZE = 1_000_000; // 1 MB
  process.stdin.on("data", (chunk) => {
    input += chunk;
    if (input.length > MAX_STDIN_SIZE) {
      process.stdout.write("{}");
      process.exit(0);
    }
  });

  process.stdin.on("end", () => {
    let context = {};
    try {
      const data = stripProto(JSON.parse(input));

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

      // Advisory lock to prevent concurrent read-modify-write races
      if (!acquireLock(failuresPath)) {
        // Another process holds the lock — skip injection this time
        process.stdout.write("{}");
        return;
      }

      try {
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
                sanitize(
                  entry.assertion_id || entry.description || "no details",
                ),
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
      } finally {
        releaseLock(failuresPath);
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
