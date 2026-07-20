from __future__ import annotations

import builtins
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts._functional_common import CheckSkipped
from scripts import article_extract_functional_check as check


def test_newspaper_import_missing_is_skip_when_not_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "newspaper":
            raise ImportError("missing newspaper")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(CheckSkipped):
        check.verify_newspaper_import(require_runtime=False)


def test_newspaper_import_missing_fails_when_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "newspaper":
            raise ImportError("missing newspaper")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ImportError):
        check.verify_newspaper_import(require_runtime=True)


def test_readability_import_missing_is_skip_when_not_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "readability":
            raise ImportError("missing readability")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(CheckSkipped):
        check.verify_readability_import(require_runtime=False)


def test_readability_import_missing_fails_when_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "readability":
            raise ImportError("missing readability")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ImportError):
        check.verify_readability_import(require_runtime=True)


def test_local_fixture_override_binds_only_the_owned_origin() -> None:
    """Functional fixture bypass must cover the bound transport without allowing other loopback URLs."""
    from souwen.web import fetch as fetch_module

    fixture_url = "http://127.0.0.1:43123/article"
    original_resolve = fetch_module.resolve_fetch_target

    with check.allow_local_fixture_url(fixture_url):
        target, reason = fetch_module.resolve_fetch_target(fixture_url)
        other_target, other_reason = fetch_module.resolve_fetch_target(
            "http://127.0.0.1:43124/article"
        )

        assert reason == ""
        assert target == fetch_module.ResolvedFetchTarget(
            original_url=fixture_url,
            connect_url=fixture_url,
            host_header="127.0.0.1:43123",
            sni_hostname=None,
        )
        assert fetch_module.validate_fetch_url(fixture_url) == (True, "")
        assert other_target is None
        assert "内部/私有" in other_reason

    assert fetch_module.resolve_fetch_target is original_resolve
    restored_target, restored_reason = fetch_module.resolve_fetch_target(fixture_url)
    assert restored_target is None
    assert "内部/私有" in restored_reason


def test_offline_mode_writes_skip_report(tmp_path: Path) -> None:
    json_report = tmp_path / "article.json"
    markdown_report = tmp_path / "article.md"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/article_extract_functional_check.py",
            "--mode",
            "offline",
            "--json-report",
            str(json_report),
            "--markdown-report",
            str(markdown_report),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "SKIP offline_mode" in completed.stdout
    data = json.loads(json_report.read_text(encoding="utf-8"))
    assert data["script"] == "article_extract_functional_check"
    assert data["mode"] == "offline"
    assert data["overall"] == "SKIP"
    assert data["checks"][0]["name"] == "offline_mode"
    assert data["checks"][0]["outcome"] == "SKIP"
    assert "Overall: **SKIP**" in markdown_report.read_text(encoding="utf-8")
