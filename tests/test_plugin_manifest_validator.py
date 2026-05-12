from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools" / "validate_plugin_manifest.py"
EXAMPLE = ROOT / "examples" / "minimal-plugin" / "souwen-plugin.json"


def test_minimal_plugin_manifest_validates() -> None:
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(EXAMPLE)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "OK:" in result.stdout


def test_plugin_manifest_validator_reports_contract_errors(tmp_path: Path) -> None:
    manifest = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    manifest["adapters"][0]["methods"] = ["not_a_real_capability"]
    manifest["adapters"][0]["auth_requirement"] = "required"
    manifest["adapters"][0]["config_field"] = None
    manifest["adapters"][0]["credential_fields"] = []
    path = tmp_path / "bad-plugin.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "unknown non-namespaced capability" in result.stderr
    assert "requires config_field or credential_fields" in result.stderr
