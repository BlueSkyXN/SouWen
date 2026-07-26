"""Deterministic tests for the frozen SouWen server multi-call entry point."""

from __future__ import annotations

import sys

import pytest

from deploy.process import server_main
from deploy.process.supervisor import INTERNAL_ROLE_ENV


def test_product_entry_applies_bounded_listener_overrides(
    monkeypatch,
) -> None:
    observed: dict[str, str] = {}

    def run_supervisor() -> int:
        observed["host"] = server_main.os.environ["HOST"]
        observed["port"] = server_main.os.environ["PORT"]
        return 0

    monkeypatch.setattr(server_main, "supervisor_main", run_supervisor)

    assert server_main.main(["--host", "127.0.0.1", "--port", "49300"]) == 0
    assert observed == {"host": "127.0.0.1", "port": "49300"}


def test_frozen_entry_uses_only_bundle_local_playwright_runtime(monkeypatch, tmp_path) -> None:
    executable = tmp_path / "souwen-server"
    browser_root = tmp_path / "ms-playwright"
    browser_root.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "/untrusted/external-browser")
    monkeypatch.setattr(server_main, "supervisor_main", lambda: 0)

    assert server_main.main([]) == 0
    assert server_main.os.environ["PLAYWRIGHT_BROWSERS_PATH"] == str(browser_root)


def test_frozen_entry_fails_closed_without_bundled_playwright(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "souwen-server"))
    monkeypatch.setattr(server_main, "supervisor_main", lambda: pytest.fail("must not start"))

    assert server_main.main([]) == 1


def test_internal_roles_are_hidden_and_rejected_outside_supervisor(monkeypatch) -> None:
    monkeypatch.delenv(INTERNAL_ROLE_ENV, raising=False)
    assert "--internal-role" not in server_main._parser().format_help()

    with pytest.raises(SystemExit) as exc_info:
        server_main.main(["--internal-role", "worker"])
    assert exc_info.value.code == 2


@pytest.mark.parametrize("role, runner", [("worker", "_run_worker"), ("api", "_run_api")])
def test_internal_role_dispatch_requires_supervisor_marker(monkeypatch, role, runner) -> None:
    calls: list[str] = []
    monkeypatch.setenv(INTERNAL_ROLE_ENV, "1")
    monkeypatch.setattr(server_main, runner, lambda: calls.append(role))

    assert server_main.main(["--internal-role", role]) == 0
    assert calls == [role]
