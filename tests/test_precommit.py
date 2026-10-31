import os
import shlex
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECKS = [
    "bun run check",
    "uv run ruff check transcripts tests",
    "uv run ruff format --check transcripts tests",
    "uv run ty check transcripts",
    "uv run pytest tests",
]


@pytest.mark.parametrize("failed_check", [None, *CHECKS])
def test_pre_commit_runs_checks_and_stops_on_failure(tmp_path, failed_check):
    log = tmp_path / "checks.log"
    tools = tmp_path / "bin"
    tools.mkdir()
    for name in ("bun", "uv"):
        executable = tools / name
        executable.write_text(
            '#!/bin/sh\ncommand="${0##*/} $*"\n'
            f"printf '%s\\n' \"$command\" >> {shlex.quote(str(log))}\n"
            f'if [ "$command" = {shlex.quote(failed_check or "")} ]; then exit 17; fi\n',
            encoding="utf-8",
        )
        executable.chmod(0o755)

    result = subprocess.run(
        ["sh", str(ROOT / ".husky/pre-commit")],
        cwd=ROOT,
        env={**os.environ, "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )
    completed = log.read_text().splitlines() if log.exists() else []

    if failed_check is None:
        assert result.returncode == 0, result.stderr
        assert completed == CHECKS
    else:
        assert result.returncode == 17, result.stderr
        assert completed == CHECKS[: CHECKS.index(failed_check) + 1]
