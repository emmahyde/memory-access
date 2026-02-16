#!/usr/bin/env -S uv run --script
# /// script
# dependencies = []
# ///

import json

import sys
from pathlib import Path
from time import time


def parse_yaml_frontmatter(text: str) -> dict:
    lines = text.strip().split('\n')
    result = {}
    _current_key = None
    current_list = None
    current_dict = None

    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if indent == 0 and ':' in line:
            key, _, value = line.partition(':')
            key = key.strip()
            value = value.strip().strip('"')

            if value:
                result[key] = value
            else:
                _current_key = key
                current_list = []
                result[key] = current_list
                current_dict = None

        elif current_list is not None and indent > 0 and stripped.startswith('- '):
            item_content = stripped[2:].strip()

            if ':' in item_content:
                if current_dict is None:
                    current_dict = {}
                    current_list.append(current_dict)

                item_key, _, item_value = item_content.partition(':')
                current_dict[item_key.strip()] = item_value.strip().strip('"')
            else:
                current_list.append(item_content.strip('"'))
                current_dict = None

        elif current_dict is not None and indent > 2 and ':' in line:
            item_key, _, item_value = line.partition(':')
            current_dict[item_key.strip()] = item_value.strip().strip('"')

    return result


def find_most_recent_task_report(outputs_dir: Path) -> Path | None:
    try:
        task_reports = list(outputs_dir.glob('task__*.md'))
        if not task_reports:
            return None
        return max(task_reports, key=lambda p: p.stat().st_mtime)
    except Exception:
        return None


def is_report_recent(report_path: Path, max_age_seconds: int = 60) -> bool:
    try:
        mod_time = report_path.stat().st_mtime
        age = time() - mod_time
        return age <= max_age_seconds
    except Exception:
        return False


def extract_frontmatter(report_path: Path) -> str:
    try:
        with open(report_path, 'r') as f:
            lines = f.readlines()

        in_frontmatter = False
        started = False
        frontmatter_lines = []

        for line in lines:
            if line.strip() == '---':
                if not started:
                    started = True
                    in_frontmatter = True
                    continue
                else:
                    break

            if in_frontmatter:
                frontmatter_lines.append(line)

        return ''.join(frontmatter_lines)
    except Exception:
        return ''


def build_files_touched_xml(files_touched: list) -> str:
    if not files_touched:
        return ''

    xml_lines = ['  <files_touched>']
    for entry in files_touched:
        if isinstance(entry, dict):
            resource = entry.get('resource', '')
            action = entry.get('action', '')
            xml_lines.append(f'    <file resource="{resource}" action="{action}" />')
    xml_lines.append('  </files_touched>')

    return '\n'.join(xml_lines)


def build_acceptance_check_xml(acceptance_check: list) -> str:
    if not acceptance_check:
        return ''

    xml_lines = ['  <acceptance_check>']
    for entry in acceptance_check:
        if isinstance(entry, dict):
            criterion = entry.get('criterion', '')
            status = entry.get('status', '')
            evidence = entry.get('evidence', '')
            xml_lines.append(f'    <criterion name="{criterion}" status="{status}" evidence="{evidence}" />')
    xml_lines.append('  </acceptance_check>')

    return '\n'.join(xml_lines)


def build_notes_xml(notes: list) -> str:
    if not notes:
        return ''

    xml_lines = ['  <notes>']
    for note in notes:
        if isinstance(note, str):
            xml_lines.append(f'    <note>{note}</note>')
    xml_lines.append('  </notes>')

    return '\n'.join(xml_lines)


def build_additional_context_xml(task_id: str, status: str, report_relpath: str,
                                   files_xml: str, acceptance_xml: str, notes_xml: str) -> str:
    xml_parts = [f'<subagent-result task_id="{task_id}" status="{status}" report_path="{report_relpath}">']

    if files_xml:
        xml_parts.append(files_xml)
    if acceptance_xml:
        xml_parts.append(acceptance_xml)
    if notes_xml:
        xml_parts.append(notes_xml)

    xml_parts.append('</subagent-result>')

    return '\n'.join(xml_parts)


def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    cwd = input_data.get('cwd')
    if not cwd:
        sys.exit(0)

    outputs_dir = Path(cwd) / '.orchestrator' / 'outputs'
    if not outputs_dir.is_dir():
        sys.exit(0)

    report = find_most_recent_task_report(outputs_dir)
    if not report:
        sys.exit(0)

    if not is_report_recent(report):
        sys.exit(0)

    frontmatter_text = extract_frontmatter(report)
    if not frontmatter_text:
        sys.exit(0)

    frontmatter = parse_yaml_frontmatter(frontmatter_text)

    task_id = frontmatter.get('task_id', '')
    status = frontmatter.get('status', '')
    report_basename = report.name
    report_relpath = f'.orchestrator/outputs/{report_basename}'

    files_touched = frontmatter.get('files_touched', [])
    acceptance_check = frontmatter.get('acceptance_check', [])
    notes_for_orchestrator = frontmatter.get('notes_for_orchestrator', [])

    files_xml = build_files_touched_xml(files_touched)
    acceptance_xml = build_acceptance_check_xml(acceptance_check)
    notes_xml = build_notes_xml(notes_for_orchestrator)

    additional_context = build_additional_context_xml(
        task_id, status, report_relpath, files_xml, acceptance_xml, notes_xml
    )

    system_message = f'Output for {report_basename} has been injected into context.'

    output = {
        'systemMessage': system_message,
        'additionalContext': additional_context
    }

    print(json.dumps(output))


if __name__ == '__main__':
    main()
