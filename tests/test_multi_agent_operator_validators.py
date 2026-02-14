from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "skills" / "multi-agent-operator-guide" / "scripts"
EXAMPLES_DIR = REPO_ROOT / "skills" / "multi-agent-operator-guide" / "examples"


def _run_script(script_name: str, payload: dict) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script_name)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.stdout.strip(), f"expected JSON stdout from {script_name}, stderr={proc.stderr!r}"
    return proc.returncode, json.loads(proc.stdout)


def _load_example(name: str) -> dict:
    return json.loads((EXAMPLES_DIR / name).read_text())


def test_validate_packet_accepts_valid_assignment() -> None:
    code, output = _run_script("validate_packet.py", _load_example("01-assignment-valid.json"))
    assert code == 0
    assert output["allow"] is True
    assert output["code"] == "OK"


def test_validate_packet_rejects_empty_normalized_lock_scope() -> None:
    code, output = _run_script("validate_packet.py", _load_example("01-assignment-invalid-empty-normalized-lock.json"))
    assert code != 0
    assert output["allow"] is False
    assert output["code"] == "SCHEMA_INVALID"
    assert "lock_scope" in output["reason"]


def test_validate_packet_rejects_invalid_dependency_id_format() -> None:
    code, output = _run_script("validate_packet.py", _load_example("01-assignment-invalid-dependency-id.json"))
    assert code != 0
    assert output["allow"] is False
    assert output["code"] == "SCHEMA_INVALID"
    assert "dependencies" in output["reason"]


def test_validate_result_rejects_done_with_empty_acceptance_check() -> None:
    code, output = _run_script("validate_result.py", _load_example("03-result-invalid-empty-acceptance.json"))
    assert code != 0
    assert output["allow"] is False
    assert output["code"] == "ACCEPTANCE_FAILED"


def test_validate_result_rejects_secret_in_notes_for_orchestrator() -> None:
    code, output = _run_script("validate_result.py", _load_example("03-result-invalid-secret-note.json"))
    assert code != 0
    assert output["allow"] is False
    assert output["code"] == "UNTRUSTED_CONTEXT_BLOCK"


def test_validate_result_accepts_valid_done_result() -> None:
    code, output = _run_script("validate_result.py", _load_example("03-result-valid.json"))
    assert code == 0
    assert output["allow"] is True
    assert output["code"] == "OK"
