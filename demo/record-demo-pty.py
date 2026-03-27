#!/usr/bin/env python3
"""PTY-based terminal recorder for schliff demo.

Captures real ANSI output via pty.openpty() and writes an asciinema v2 .cast file.
Then converts to GIF using agg.
"""

import json
import os
import pty
import select
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = [sys.executable, os.path.join(REPO_ROOT, "skills", "schliff", "scripts", "cli.py")]
CAST_FILE = os.path.join(REPO_ROOT, "demo", "schliff-demo.cast")
GIF_FILE = os.path.join(REPO_ROOT, "demo", "schliff-demo.gif")

COLS = 90
ROWS = 30

SCENES = [
    {
        "label": "schliff score demo/bad-skill/SKILL.md",
        "cmd": CLI + ["score", "demo/bad-skill/SKILL.md"],
        "pause_after": 3.0,
    },
    {
        "label": "schliff score skills/schliff/SKILL.md --eval-suite skills/schliff/eval-suite.json",
        "cmd": CLI + ["score", "skills/schliff/SKILL.md", "--eval-suite", "skills/schliff/eval-suite.json"],
        "pause_after": 3.0,
    },
    {
        "label": "schliff score demo/sample-cursorrules/.cursorrules",
        "cmd": CLI + ["score", "demo/sample-cursorrules/.cursorrules"],
        "pause_after": 3.0,
    },
    {
        "label": "schliff compare demo/bad-skill/SKILL.md skills/schliff/SKILL.md",
        "cmd": CLI + ["compare", "demo/bad-skill/SKILL.md", "skills/schliff/SKILL.md"],
        "pause_after": 3.0,
    },
    {
        "label": "schliff suggest demo/bad-skill/SKILL.md",
        "cmd": CLI + ["suggest", "demo/bad-skill/SKILL.md"],
        "pause_after": 3.0,
    },
    {
        "label": "schliff sync demo/sync-conflict/",
        "cmd": CLI + ["sync", "demo/sync-conflict/"],
        "pause_after": 3.0,
    },
    {
        "label": "schliff report demo/bad-skill/SKILL.md",
        "cmd": CLI + ["report", "demo/bad-skill/SKILL.md"],
        "pause_after": 3.0,
    },
    {
        "label": "schliff drift --repo .",
        "cmd": CLI + ["drift", "--repo", "."],
        "pause_after": 3.0,
    },
]


def read_pty_output(fd, timeout=5.0):
    """Read all available output from a PTY file descriptor."""
    output = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        ready, _, _ = select.select([fd], [], [], 0.1)
        if ready:
            try:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                output += chunk
            except OSError:
                break
        elif output:
            # Got some output and nothing more is coming
            break
    return output


def run_in_pty(cmd, env, cwd):
    """Run a command in a PTY and capture its output with real ANSI colors."""
    master_fd, slave_fd = pty.openpty()

    # Set terminal size
    import struct
    import fcntl
    import termios
    winsize = struct.pack("HHHH", ROWS, COLS, 0, 0)
    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)

    proc = subprocess.Popen(
        cmd,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        cwd=cwd,
        env=env,
        close_fds=True,
    )
    os.close(slave_fd)

    output = read_pty_output(master_fd, timeout=15.0)
    proc.wait()
    os.close(master_fd)

    return output.decode("utf-8", errors="replace")


def write_cast(scenes_output):
    """Write asciinema v2 cast file from recorded scenes."""
    header = {
        "version": 2,
        "width": COLS,
        "height": ROWS,
        "timestamp": int(time.time()),
        "env": {"SHELL": "/bin/zsh", "TERM": "xterm-256color"},
    }

    events = []
    t = 0.0

    for i, scene in enumerate(scenes_output):
        label = scene["label"]
        output = scene["output"]

        # Clear screen + show prompt in ONE event (no empty flash frame)
        clear_prefix = "\x1b[2J\x1b[H" if i > 0 else ""
        prompt_text = f"{clear_prefix}\x1b[1;36m$ {label}\x1b[0m\r\n\r\n"
        events.append([round(t, 3), "o", prompt_text])
        t += 0.5

        # Show the output (normalize line endings)
        output_text = output.replace("\n", "\r\n") if "\r\n" not in output else output
        # Remove duplicate \r\r\n that can happen
        output_text = output_text.replace("\r\r\n", "\r\n")
        events.append([round(t, 3), "o", output_text])
        t += 0.1

        # Blank line separator
        events.append([round(t, 3), "o", "\r\n"])
        t += scene["pause_after"]

    with open(CAST_FILE, "w") as f:
        f.write(json.dumps(header) + "\n")
        for event in events:
            f.write(json.dumps(event) + "\n")

    print(f"Cast file written: {CAST_FILE}")
    print(f"  {len(events)} events, {t:.1f}s total duration")


def convert_to_gif():
    """Convert cast file to GIF using agg."""
    cmd = [
        "agg",
        "--theme", "github-dark",
        "--cols", str(COLS),
        "--rows", str(ROWS),
        "--font-size", "16",
        "--speed", "1",
        "--last-frame-duration", "5",
        CAST_FILE,
        GIF_FILE,
    ]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"agg stderr: {result.stderr}")
        return False
    print(f"GIF written: {GIF_FILE}")
    return True


def main():
    env = os.environ.copy()
    env["FORCE_COLOR"] = "1"
    env["TERM"] = "xterm-256color"
    env["COLUMNS"] = str(COLS)
    env["LINES"] = str(ROWS)
    # Ensure no pager interferes
    env["NO_COLOR"] = ""
    # Remove NO_COLOR if set (we want color)
    env.pop("NO_COLOR", None)

    print(f"Recording {len(SCENES)} scenes...")
    scenes_output = []

    for i, scene in enumerate(SCENES, 1):
        label = scene["label"]
        print(f"  Scene {i}/{len(SCENES)}: {label}")
        output = run_in_pty(scene["cmd"], env, REPO_ROOT)
        # Strip trailing whitespace lines but keep content
        output = output.rstrip() + "\r\n"
        scenes_output.append({
            "label": label,
            "output": output,
            "pause_after": scene["pause_after"],
        })
        print(f"    -> {len(output)} chars captured")

    write_cast(scenes_output)

    if convert_to_gif():
        size = os.path.getsize(GIF_FILE)
        print(f"\nDone! GIF size: {size / 1024:.0f} KB")
    else:
        print("\nGIF conversion failed. Cast file is still available.")
        sys.exit(1)


if __name__ == "__main__":
    main()
