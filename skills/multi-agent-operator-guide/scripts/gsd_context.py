#!/usr/bin/env python3
"""GSD context extraction helpers for orchestrator agents.

Wraps common gsd-tools.cjs calls to extract phase context, roadmap sections,
and prior decisions without dumping large content blobs into orchestrator context.

Usage:
    python gsd_context.py phase-context <phase_number> [--includes key1,key2,...]
    python gsd_context.py phase-section <phase_number>
    python gsd_context.py prior-decisions
    python gsd_context.py content-sizes <phase_number> [--includes key1,key2,...]

Environment:
    GSD_TOOLS_PATH  Path to gsd-tools.cjs (default: ~/.claude/get-shit-done/bin/gsd-tools.cjs)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def get_gsd_tools_path() -> str:
    return os.environ.get(
        "GSD_TOOLS_PATH",
        str(Path.home() / ".claude" / "get-shit-done" / "bin" / "gsd-tools.cjs"),
    )


def run_gsd(args: list[str]) -> tuple[int, str, str]:
    """Run gsd-tools.cjs with given args. Returns (returncode, stdout, stderr)."""
    tools_path = get_gsd_tools_path()
    cmd = ["node", tools_path] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.returncode, result.stdout, result.stderr


def emit_error(message: str, details: dict[str, Any] | None = None) -> int:
    payload: dict[str, Any] = {"error": True, "message": message}
    if details:
        payload["details"] = details
    print(json.dumps(payload, separators=(",", ":")), file=sys.stderr)
    return 1


def emit_json(data: dict[str, Any]) -> int:
    print(json.dumps(data, separators=(",", ":")))
    return 0


def cmd_phase_context(phase: str, includes: str | None) -> int:
    """Extract phase context, writing content fields to temp files."""
    args = ["init", "plan-phase", phase]
    if includes:
        args += ["--include", includes]

    rc, stdout, stderr = run_gsd(args)
    if rc != 0:
        return emit_error(f"gsd-tools init plan-phase failed: {stderr.strip()}")

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        return emit_error(f"Failed to parse gsd-tools output: {e}")

    # Separate content fields from metadata
    metadata: dict[str, Any] = {}
    content_files: dict[str, dict[str, Any]] = {}

    for key, value in data.items():
        if key.endswith("_content") and isinstance(value, str):
            # Write to temp file
            tmp_path = os.path.join(tempfile.gettempdir(), f"gsd_phase{phase}_{key}.txt")
            with open(tmp_path, "w") as f:
                f.write(value)
            content_files[key] = {"path": tmp_path, "chars": len(value)}
        else:
            metadata[key] = value

    return emit_json({"metadata": metadata, "content_files": content_files})


def cmd_phase_section(phase: str) -> int:
    """Extract the roadmap section for a phase."""
    rc, stdout, stderr = run_gsd(["roadmap", "get-phase", phase])
    if rc != 0:
        return emit_error(f"gsd-tools roadmap get-phase failed: {stderr.strip()}")

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        # If not JSON, output raw
        print(stdout.strip())
        return 0

    section = data.get("section", "")
    if not section:
        return emit_error(f"No section found for phase {phase}")

    print(section)
    return 0


def cmd_prior_decisions() -> int:
    """Extract decisions from state snapshot."""
    rc, stdout, stderr = run_gsd(["state-snapshot"])
    if rc != 0:
        return emit_error(f"gsd-tools state-snapshot failed: {stderr.strip()}")

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        return emit_error(f"Failed to parse state-snapshot: {e}")

    decisions = data.get("decisions", [])
    if not decisions:
        print("No prior decisions")
        return 0

    for d in decisions:
        phase = d.get("phase", "?")
        summary = d.get("summary", d.get("decision", ""))
        rationale = d.get("rationale", "")
        line = f"{phase}: {summary}"
        if rationale:
            line += f" - {rationale}"
        print(line)
    return 0


def cmd_content_sizes(phase: str, includes: str | None) -> int:
    """Report content field sizes without writing temp files."""
    args = ["init", "plan-phase", phase]
    if includes:
        args += ["--include", includes]

    rc, stdout, stderr = run_gsd(args)
    if rc != 0:
        return emit_error(f"gsd-tools init plan-phase failed: {stderr.strip()}")

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        return emit_error(f"Failed to parse gsd-tools output: {e}")

    sizes: dict[str, int] = {}
    for key, value in data.items():
        if key.endswith("_content") and isinstance(value, str):
            sizes[key] = len(value)

    return emit_json({"phase": phase, "content_sizes": sizes})


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 1

    cmd = sys.argv[1]

    if cmd == "phase-context":
        if len(sys.argv) < 3:
            return emit_error("Usage: gsd_context.py phase-context <phase_number> [--includes key1,key2,...]")
        phase = sys.argv[2]
        includes = None
        if "--includes" in sys.argv:
            idx = sys.argv.index("--includes")
            if idx + 1 < len(sys.argv):
                includes = sys.argv[idx + 1]
        return cmd_phase_context(phase, includes)

    elif cmd == "phase-section":
        if len(sys.argv) < 3:
            return emit_error("Usage: gsd_context.py phase-section <phase_number>")
        return cmd_phase_section(sys.argv[2])

    elif cmd == "prior-decisions":
        return cmd_prior_decisions()

    elif cmd == "content-sizes":
        if len(sys.argv) < 3:
            return emit_error("Usage: gsd_context.py content-sizes <phase_number> [--includes key1,key2,...]")
        phase = sys.argv[2]
        includes = None
        if "--includes" in sys.argv:
            idx = sys.argv.index("--includes")
            if idx + 1 < len(sys.argv):
                includes = sys.argv[idx + 1]
        return cmd_content_sizes(phase, includes)

    else:
        return emit_error(f"Unknown command: {cmd}")


if __name__ == "__main__":
    sys.exit(main())
