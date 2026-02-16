#!/usr/bin/env -S uv run --script
# /// script
# dependencies = []
# ///

import sys
import json
from pathlib import Path


ORCHESTRATOR_ALLOWED = (".claude/", "docs/")


def is_always_allowed(rel_path: str) -> bool:
    """Check if path is in always-allowed directories."""
    return (
        rel_path.startswith(".orchestrator/outputs/") or
        rel_path.startswith("worklogs/")
    )


def is_orchestrator_allowed(rel_path: str) -> bool:
    """When no lock file exists (orchestrator context), only allow these dirs."""
    return any(rel_path.startswith(prefix) for prefix in ORCHESTRATOR_ALLOWED)


def normalize_to_relative(file_path: str, cwd: str) -> str:
    """Convert absolute path to relative path from cwd."""
    file_path_obj = Path(file_path)
    cwd_obj = Path(cwd)

    if file_path_obj.is_absolute():
        try:
            return str(file_path_obj.relative_to(cwd_obj))
        except ValueError:
            return file_path
    return file_path


def matches_scope(rel_path: str, scope: str) -> bool:
    """Check if rel_path matches the scope entry."""
    # Exact match
    if rel_path == scope:
        return True

    # Directory prefix with trailing slash
    if scope.endswith("/") and rel_path.startswith(scope):
        return True

    # Directory prefix without trailing slash (add it for matching)
    if not scope.endswith("/") and rel_path.startswith(scope + "/"):
        return True

    return False


def get_active_scopes(locks_file: Path) -> list[str]:
    """Extract resource scopes from active lock entries."""
    try:
        with open(locks_file) as f:
            locks_data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

    active_entries = [entry for entry in locks_data if entry.get("active", False)]

    scopes = []
    for entry in active_entries:
        resources = entry.get("resource", [])
        if isinstance(resources, list):
            scopes.extend(resources)

    return scopes


def main():
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    cwd = hook_input.get("cwd")
    tool_input = hook_input.get("tool_input", {})
    file_path = tool_input.get("file_path")

    if not cwd or not file_path:
        sys.exit(0)

    rel_path = normalize_to_relative(file_path, cwd)

    if is_always_allowed(rel_path):
        sys.exit(0)

    locks_file = Path(cwd) / ".orchestrator" / "active_locks.json"
    if not locks_file.exists():
        # No lock file = orchestrator or main session context
        # Restrict writes to allowed directories only
        if is_orchestrator_allowed(rel_path):
            sys.exit(0)
        dirs = ", ".join(ORCHESTRATOR_ALLOWED)
        error_response = {
            "decision": "deny",
            "reason": f"File '{rel_path}' is outside allowed write directories ({dirs}). "
                      "Only .claude/ and docs/ are writable from this context."
        }
        print(json.dumps(error_response), file=sys.stderr)
        sys.exit(2)

    active_scopes = get_active_scopes(locks_file)

    if not active_scopes:
        error_response = {
            "decision": "deny",
            "reason": "No active resource locks found. You must acquire a lock before writing files."
        }
        print(json.dumps(error_response), file=sys.stderr)
        sys.exit(2)

    if not any(matches_scope(rel_path, scope) for scope in active_scopes):
        scopes_list = "\n".join(f"  - {scope}" for scope in active_scopes)
        error_response = {
            "decision": "deny",
            "reason": f"File '{rel_path}' is outside your locked resource scope. Allowed scopes:\n{scopes_list}"
        }
        print(json.dumps(error_response), file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
