#!/usr/bin/env -S uv run --script
# /// script
# dependencies = []
# ///

import json
import sys
from pathlib import Path


def extract_assignment_packet(prompt: str) -> dict | None:
    try:
        marker = '[ASSIGNMENT PACKET]'
        if marker not in prompt:
            return None

        packet_text = prompt.split(marker, 1)[1].strip()

        lines = packet_text.split('\n')
        json_lines = []
        for line in lines:
            if line.strip().startswith('{'):
                json_lines = [line]
                continue
            if json_lines:
                json_lines.append(line)
                if line.strip().endswith('}') and line.count('}') >= line.count('{'):
                    break

        if json_lines:
            json_text = '\n'.join(json_lines)
            return json.loads(json_text)
    except Exception:
        pass

    return None


def build_lock_entries_from_scope(task_id: str, lock_scope: list) -> list[dict]:
    entries = []
    for resource in lock_scope:
        entries.append({
            'task_id': task_id,
            'resource': resource,
            'active': True
        })
    return entries


def deduplicate_locks(locks: list[dict]) -> list[dict]:
    seen = set()
    unique_locks = []

    for lock in locks:
        key = (lock.get('task_id', ''), lock.get('resource', ''))
        if key not in seen:
            seen.add(key)
            unique_locks.append(lock)

    return unique_locks


def merge_and_update_locks(cwd: Path, packet: dict):
    try:
        locks_file = cwd / '.claude/orchestrator' / 'active_locks.json'

        existing_locks = []
        if locks_file.is_file():
            with open(locks_file, 'r') as f:
                existing_locks = json.load(f)

        packet_locks = packet.get('active_locks', [])

        task_info = packet.get('task', {})
        task_id = task_info.get('task_id', 'unknown')
        lock_scope = task_info.get('lock_scope', [])
        task_locks = build_lock_entries_from_scope(task_id, lock_scope)

        all_locks = existing_locks + packet_locks + task_locks

        unique_locks = deduplicate_locks(all_locks)

        with open(locks_file, 'w') as f:
            json.dump(unique_locks, f, indent=2)
    except Exception:
        pass


def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    cwd_str = input_data.get('cwd')
    if not cwd_str:
        sys.exit(0)

    tool_input = input_data.get('tool_input', {})
    run_in_background = tool_input.get('run_in_background', False)

    if not run_in_background:
        sys.exit(0)

    cwd = Path(cwd_str)
    orchestrator_dir = cwd / '.claude/orchestrator'
    orchestrator_dir.mkdir(exist_ok=True)

    active_dispatch_marker = orchestrator_dir / '.active_dispatch'
    active_dispatch_marker.touch()

    prompt = tool_input.get('prompt', '')
    if prompt:
        packet = extract_assignment_packet(prompt)
        if packet:
            merge_and_update_locks(cwd, packet)

    sys.exit(0)


if __name__ == '__main__':
    main()
