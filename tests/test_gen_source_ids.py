"""tools/gen_source_ids.py regression tests."""

from __future__ import annotations

import subprocess
import sys


def test_check_flag_runs_from_source_tree():
    result = subprocess.run(
        [
            sys.executable,
            "tools/gen_source_ids.py",
            "--check",
        ],
        check=False,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "source ids match registry adapter names" in result.stdout
