"""Deterministic lifecycle tests for the HFS two-process supervisor."""

from __future__ import annotations

import signal
from collections import deque

import pytest

from deploy.process import supervisor as supervisor_module
from deploy.process.supervisor import INTERNAL_ROLE_ENV, DeploymentSettings, DeploymentSupervisor
from souwen.delivery.api import RolloutMode


class _Process:
    _next_pid = 1000

    def __init__(self, polls=()) -> None:
        self.pid = _Process._next_pid
        _Process._next_pid += 1
        self._polls = deque(polls)
        self.returncode = None
        self.signals: list[int] = []
        self.terminated = False
        self.killed = False

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        if self._polls:
            value = self._polls.popleft()
            if value is not None:
                self.returncode = value
            return value
        return None

    def send_signal(self, signum: int) -> None:
        self.signals.append(signum)

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None) -> int:
        assert timeout is not None
        return int(self.returncode or 0)


def _settings(**overrides) -> DeploymentSettings:
    values = {
        "rollout_mode": RolloutMode.TARGET,
        "api_host": "0.0.0.0",
        "api_port": 49265,
        "worker_host": "127.0.0.1",
        "worker_port": 49266,
        "source_sha": "a" * 40,
        "wrapper_sha": "b" * 40,
        "config_revision": "source-" + "a" * 40,
        "worker_startup_timeout": 1.0,
        "worker_restart_limit": 2,
        "worker_restart_backoff": 0.0,
        "termination_timeout": 1.0,
    }
    values.update(overrides)
    return DeploymentSettings(**values)


def test_worker_is_ready_before_api_and_children_share_private_runtime_env(monkeypatch) -> None:
    worker = _Process([None])
    api = _Process([0])
    spawned: list[tuple[tuple[str, ...], dict[str, str]]] = []

    def spawn(command, env):
        spawned.append((tuple(command), dict(env)))
        return worker if len(spawned) == 1 else api

    supervisor = DeploymentSupervisor(
        _settings(),
        process_factory=spawn,
        readiness_probe=lambda *_args: True,
        token="t" * 48,
    )
    monkeypatch.setattr(supervisor, "_install_signal_handlers", lambda: None)

    assert supervisor.run() == 0

    assert "souwen.worker.browser_fetch.runtime" in spawned[0][0]
    assert "souwen.server.app:app" in spawned[1][0]
    for command, env in spawned:
        assert "t" * 48 not in command
        assert env["SOUWEN_BROWSER_WORKER_TOKEN"] == "t" * 48
        assert env["HOST"] == "0.0.0.0"
        assert env["PORT"] == "49265"
        assert env["SOUWEN_SOURCE_SHA"] == "a" * 40
        assert env["SOUWEN_WRAPPER_SHA"] == "b" * 40
        assert env["SOUWEN_CONFIG_REVISION"] == "source-" + "a" * 40
        assert env["SOUWEN_V2_ROLLOUT"] == "target"
        assert env[INTERNAL_ROLE_ENV] == "1"
    assert worker.signals == [signal.SIGTERM]


def test_initial_worker_failure_never_starts_api(monkeypatch) -> None:
    spawned: list[tuple[str, ...]] = []
    cleaned_groups: list[_Process] = []

    def spawn(command, _env):
        spawned.append(tuple(command))
        return _Process([1])

    supervisor = DeploymentSupervisor(
        _settings(),
        process_factory=spawn,
        readiness_probe=lambda *_args: False,
        token="t" * 48,
    )
    monkeypatch.setattr(supervisor, "_install_signal_handlers", lambda: None)
    monkeypatch.setattr(supervisor, "_kill_remaining_group", cleaned_groups.append)

    with pytest.raises(RuntimeError, match="exited before readiness"):
        supervisor.run()

    assert len(spawned) == 1
    assert "souwen.worker.browser_fetch.runtime" in spawned[0]
    assert len(cleaned_groups) == 1


def test_worker_restart_budget_is_bounded_while_api_remains_alive(monkeypatch) -> None:
    first_worker = _Process([None, 1])
    processes = deque(
        [
            first_worker,
            _Process([None, 1]),
            _Process([None, 1]),
            _Process([None, None, 0]),
        ]
    )
    spawned: list[tuple[str, ...]] = []
    cleaned_groups: list[_Process] = []

    def spawn(command, _env):
        spawned.append(tuple(command))
        if "souwen.server.app:app" in command:
            return processes.pop()
        return processes.popleft()

    supervisor = DeploymentSupervisor(
        _settings(worker_restart_limit=2),
        process_factory=spawn,
        readiness_probe=lambda *_args: True,
        token="t" * 48,
    )
    monkeypatch.setattr(supervisor, "_install_signal_handlers", lambda: None)
    monkeypatch.setattr(supervisor, "_kill_remaining_group", cleaned_groups.append)

    assert supervisor.run() == 0

    worker_spawns = [
        command for command in spawned if "souwen.worker.browser_fetch.runtime" in command
    ]
    api_spawns = [command for command in spawned if "souwen.server.app:app" in command]
    assert len(worker_spawns) == 3
    assert len(api_spawns) == 1
    assert first_worker in cleaned_groups


def test_signal_is_forwarded_to_both_children_without_exposing_token() -> None:
    supervisor = DeploymentSupervisor(
        _settings(), process_factory=lambda *_args: _Process(), token="t" * 48
    )
    supervisor._worker = _Process()
    supervisor._api = _Process()

    supervisor._handle_signal(signal.SIGTERM, None)

    assert supervisor._stop.is_set()
    assert supervisor._worker.signals == [signal.SIGTERM]
    assert supervisor._api.signals == [signal.SIGTERM]


def test_windows_break_signal_is_installed_when_available(monkeypatch) -> None:
    installed: dict[int, object] = {}
    sigbreak = getattr(signal, "SIGBREAK", 21)
    monkeypatch.setattr(signal, "SIGBREAK", sigbreak, raising=False)
    monkeypatch.setattr(signal, "signal", installed.__setitem__)

    supervisor = DeploymentSupervisor(
        _settings(), process_factory=lambda *_args: _Process(), token="t" * 48
    )
    supervisor._install_signal_handlers()

    assert installed[sigbreak] == supervisor._handle_signal


def test_windows_break_handler_maps_to_child_control_event(monkeypatch) -> None:
    sigbreak = getattr(signal, "SIGBREAK", 21)
    ctrl_break = getattr(signal, "CTRL_BREAK_EVENT", 1)
    monkeypatch.setattr(supervisor_module.os, "name", "nt")
    monkeypatch.setattr(signal, "SIGBREAK", sigbreak, raising=False)
    monkeypatch.setattr(signal, "CTRL_BREAK_EVENT", ctrl_break, raising=False)
    supervisor = DeploymentSupervisor(
        _settings(), process_factory=lambda *_args: _Process(), token="t" * 48
    )
    supervisor._worker = _Process()
    supervisor._api = _Process()

    supervisor._handle_signal(sigbreak, None)

    assert supervisor._worker.signals == [ctrl_break]
    assert supervisor._api.signals == [ctrl_break]


def test_target_settings_resolve_source_and_config_revision_from_deployment(monkeypatch) -> None:
    monkeypatch.setenv("SOUWEN_V2_ROLLOUT", "target")
    monkeypatch.setenv("SOUWEN_SOURCE_SHA", "A" * 40)
    monkeypatch.setenv("SOUWEN_WRAPPER_SHA", "B" * 40)
    monkeypatch.delenv("SOUWEN_CONFIG_REVISION", raising=False)

    settings = DeploymentSettings.from_env()

    assert settings.source_sha == "a" * 40
    assert settings.wrapper_sha == "b" * 40
    assert settings.config_revision == "source-" + "a" * 40
    assert settings.worker_required is True


def test_worker_port_cannot_be_exposed_as_the_api_port(monkeypatch) -> None:
    monkeypatch.setenv("SOUWEN_V2_ROLLOUT", "target")
    monkeypatch.setenv("SOUWEN_SOURCE_SHA", "a" * 40)
    monkeypatch.setenv("PORT", "49266")

    with pytest.raises(ValueError, match="ports must differ"):
        DeploymentSettings.from_env()


def test_supervisor_ignores_ambient_static_worker_token(monkeypatch) -> None:
    monkeypatch.setenv("SOUWEN_BROWSER_WORKER_TOKEN", "s" * 48)
    monkeypatch.setattr("deploy.process.supervisor.secrets.token_urlsafe", lambda _size: "g" * 48)

    supervisor = DeploymentSupervisor(_settings(), process_factory=lambda *_args: _Process())

    assert supervisor._child_env()["SOUWEN_BROWSER_WORKER_TOKEN"] == "g" * 48


def test_frozen_supervisor_reenters_same_executable_for_internal_roles(monkeypatch) -> None:
    monkeypatch.setattr(supervisor_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(supervisor_module.sys, "executable", "/bundle/souwen-server")
    supervisor = DeploymentSupervisor(
        _settings(api_host="127.0.0.1", api_port=49300),
        process_factory=lambda *_args: _Process(),
        token="t" * 48,
    )

    assert supervisor._worker_command() == (
        "/bundle/souwen-server",
        "--internal-role",
        "worker",
    )
    assert supervisor._api_command() == (
        "/bundle/souwen-server",
        "--internal-role",
        "api",
    )
    child_env = supervisor._child_env()
    assert child_env["HOST"] == "127.0.0.1"
    assert child_env["PORT"] == "49300"
    assert child_env[INTERNAL_ROLE_ENV] == "1"


def test_source_supervisor_keeps_python_module_child_commands(monkeypatch) -> None:
    monkeypatch.delattr(supervisor_module.sys, "frozen", raising=False)
    supervisor = DeploymentSupervisor(
        _settings(), process_factory=lambda *_args: _Process(), token="t" * 48
    )

    assert supervisor._worker_command() == (
        supervisor_module.sys.executable,
        "-m",
        "souwen.worker.browser_fetch.runtime",
    )
    assert supervisor._api_command()[:4] == (
        supervisor_module.sys.executable,
        "-m",
        "uvicorn",
        "souwen.server.app:app",
    )
