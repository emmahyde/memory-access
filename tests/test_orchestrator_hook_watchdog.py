from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WATCHDOG_SCRIPT = REPO_ROOT / "hooks" / "scripts" / "watchdog-timeout.sh"
HOOK_EXAMPLES_DIR = REPO_ROOT / "hooks" / "examples"


def _run_watchdog(example_name: str) -> tuple[int, dict]:
    payload = (HOOK_EXAMPLES_DIR / example_name).read_text()
    proc = subprocess.run(
        ["bash", str(WATCHDOG_SCRIPT)],
        input=payload,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.stdout.strip(), f"expected JSON stdout, stderr={proc.stderr!r}"
    return proc.returncode, json.loads(proc.stdout)


def test_watchdog_allows_live_tasks() -> None:
    code, output = _run_watchdog("watchdog-pass.json")
    assert code == 0
    assert output["allow"] is True
    assert output["code"] == "OK"


def test_watchdog_blocks_timed_out_tasks() -> None:
    code, output = _run_watchdog("watchdog-timeout.json")
    assert code != 0
    assert output["allow"] is False
    assert output["code"] == "R-WD-001"
    assert output["details"]["timed_out"][0]["task_id"] == "T-12"


def test_watchdog_blocks_future_skew_heartbeat() -> None:
    code, output = _run_watchdog("watchdog-future-skew.json")
    assert code != 0
    assert output["allow"] is False
    assert output["code"] == "R-WD-002"
