"""WARP runtime logging security regressions."""

from __future__ import annotations

import asyncio
import logging
import os
import pathlib
from urllib.parse import quote

import pytest

from souwen.server.warp import WarpManager


def _warp_log_messages(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(
        record.getMessage() for record in caplog.records if record.name == "souwen.warp"
    )


def test_apply_proxy_preserves_authenticated_env_without_logging_credentials(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    username = "local-user-secret"
    password = "local-password-token-secret"
    port = 11888
    expected_proxy = (
        f"socks5://{quote(username, safe='')}:{quote(password, safe='')}@127.0.0.1:{port}"
    )
    monkeypatch.setenv("SOUWEN_WARP_PROXY_USERNAME", username)
    monkeypatch.setenv("SOUWEN_WARP_PROXY_PASSWORD", password)

    with caplog.at_level(logging.INFO, logger="souwen.warp"):
        WarpManager._apply_proxy(port)

    messages = _warp_log_messages(caplog)
    assert os.environ["SOUWEN_PROXY"] == expected_proxy
    assert username not in messages
    assert password not in messages
    assert expected_proxy not in messages
    assert "proxy_type=socks5" in messages
    assert f"port={port}" in messages
    assert "auth_configured=True" in messages


def test_apply_external_proxy_preserves_env_without_logging_endpoint_or_credentials(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    proxy_url = (
        "socks5://external-user-secret:external-password-secret@proxy.example:1080"
        "?token=external-token-secret&region=hk#session=external-session-secret"
    )

    with caplog.at_level(logging.INFO, logger="souwen.warp"):
        WarpManager._apply_external_proxy(proxy_url)

    messages = _warp_log_messages(caplog)
    assert os.environ["SOUWEN_PROXY"] == proxy_url
    for sensitive_value in (
        proxy_url,
        "proxy.example",
        "external-user-secret",
        "external-password-secret",
        "external-token-secret",
        "external-session-secret",
    ):
        assert sensitive_value not in messages
    assert messages == "SOUWEN_PROXY 外部代理已配置并重载"


# ---------------------------------------------------------------------------
# usque 启动分支：真实 _start_mode → 真实 _start_usque，只替换外部进程与网络。
# 复核 R1：auto 候选链推荐 usque、_start_mode 调用 _start_usque，但整个源码树
# 没有该方法定义，实际容器里 usque 一尝试就 AttributeError 回退 wireproxy。
# ---------------------------------------------------------------------------


class _FakeProcess:
    """Record the command instead of launching an external process."""

    last_pid = 4000

    def __init__(self, cmd: list[str]) -> None:
        _FakeProcess.last_pid += 1
        self.cmd = cmd
        self.pid = _FakeProcess.last_pid
        self.terminated = False

    def poll(self) -> int | None:
        return 0 if self.terminated else None

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        return 0


class _FakeSubprocess:
    """Stands in for the subprocess module inside souwen.server.warp."""

    DEVNULL = -3  # same value as subprocess.DEVNULL; never actually used

    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.processes: list[_FakeProcess] = []
        self.run_calls: list[list[str]] = []

    def Popen(self, cmd: list[str], **_kwargs: object) -> _FakeProcess:
        self.commands.append(cmd)
        process = _FakeProcess(cmd)
        self.processes.append(process)
        return process

    def run(self, cmd: list[str], **_kwargs: object) -> object:
        self.run_calls.append(cmd)

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()


def _warp_manager_with_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, fake: _FakeSubprocess
) -> WarpManager:
    """Isolate the manager from real processes, binaries and the state file."""

    import souwen.server.warp as warp_module

    config_file = tmp_path / "usque-config.json"
    config_file.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(warp_module, "WARP_DATA_DIR", tmp_path)
    monkeypatch.setattr(warp_module, "subprocess", fake)
    monkeypatch.setenv("WARP_USQUE_CONFIG", str(config_file))
    monkeypatch.setenv("WARP_BIND_ADDRESS", "127.0.0.1")
    monkeypatch.delenv("WARP_PROXY_USERNAME", raising=False)
    monkeypatch.delenv("WARP_PROXY_PASSWORD", raising=False)
    return WarpManager()


def test_start_mode_usque_builds_the_socks_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    fake = _FakeSubprocess()
    monkeypatch.setenv("WARP_USQUE_TRANSPORT", "http2")
    manager = _warp_manager_with_env(monkeypatch, tmp_path, fake)
    usque_bin = tmp_path / "usque"
    usque_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(WarpManager, "_find_binary", staticmethod(lambda *_a: str(usque_bin)))

    asyncio.run(manager._start_mode("usque", 1080, 0, None))

    config_file = str(pathlib.Path(os.environ["WARP_USQUE_CONFIG"]))
    assert fake.commands == [
        [
            str(usque_bin),
            "-c",
            config_file,
            "--http2",
            "socks",
            "--bind",
            "127.0.0.1",
            "--port",
            "1080",
        ]
    ]
    assert manager._state.pid == fake.processes[0].pid
    assert manager._state.protocol == "masque"
    assert manager._state.proxy_type == "socks5"
    assert manager._state.http_port == 0


def test_start_mode_usque_starts_the_http_proxy_when_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    fake = _FakeSubprocess()
    monkeypatch.setenv("WARP_USQUE_TRANSPORT", "quic")
    manager = _warp_manager_with_env(monkeypatch, tmp_path, fake)
    usque_bin = tmp_path / "usque"
    monkeypatch.setattr(WarpManager, "_find_binary", staticmethod(lambda *_a: str(usque_bin)))

    asyncio.run(manager._start_mode("usque", 1080, 8000, None))

    assert len(fake.commands) == 2
    socks_cmd, http_cmd = fake.commands
    assert socks_cmd[-5:] == ["socks", "--bind", "127.0.0.1", "--port", "1080"]
    assert http_cmd[-5:] == ["http-proxy", "--bind", "127.0.0.1", "--port", "8000"]
    assert "--http2" not in socks_cmd
    assert manager._state.http_port == 8000
    assert manager._state.proxy_type == "both"


def test_start_mode_usque_adds_credentials_only_when_both_are_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    fake = _FakeSubprocess()
    monkeypatch.setenv("WARP_USQUE_TRANSPORT", "quic")
    manager = _warp_manager_with_env(monkeypatch, tmp_path, fake)
    monkeypatch.setenv("WARP_PROXY_USERNAME", "socks-user")
    monkeypatch.setenv("WARP_PROXY_PASSWORD", "socks-password-secret")
    usque_bin = tmp_path / "usque"
    monkeypatch.setattr(WarpManager, "_find_binary", staticmethod(lambda *_a: str(usque_bin)))

    asyncio.run(manager._start_mode("usque", 1080, 0, None))

    cmd = fake.commands[0]
    assert cmd[-4:] == ["-u", "socks-user", "-w", "socks-password-secret"]

    fake.commands.clear()
    monkeypatch.delenv("WARP_PROXY_PASSWORD", raising=False)
    from souwen.config import get_config

    get_config.cache_clear()  # the first start cached the credential pair
    asyncio.run(manager._start_mode("usque", 1080, 0, None))
    assert "-u" not in fake.commands[0] and "-w" not in fake.commands[0]


def test_start_mode_usque_falls_back_to_http2_when_quic_never_becomes_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    fake = _FakeSubprocess()
    monkeypatch.setenv("WARP_USQUE_TRANSPORT", "auto")
    manager = _warp_manager_with_env(monkeypatch, tmp_path, fake)
    usque_bin = tmp_path / "usque"
    monkeypatch.setattr(WarpManager, "_find_binary", staticmethod(lambda *_a: str(usque_bin)))
    waits: list[int] = []

    async def fake_wait(_self: object, _port: int, _retries: int = 10) -> bool:
        waits.append(_port)
        return len(waits) > 1  # first QUIC round never becomes ready

    monkeypatch.setattr(WarpManager, "_wait_for_proxy", fake_wait)

    asyncio.run(manager._start_mode("usque", 1080, 0, None))

    assert len(waits) == 1  # one readiness wait inside the usque start method
    assert len(fake.commands) == 2
    assert "--http2" not in fake.commands[0]
    assert "--http2" in fake.commands[1]
    # the failed QUIC process was cleaned up before the HTTP/2 retry
    assert fake.processes[0].terminated


def test_start_mode_usque_propagates_a_missing_binary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    fake = _FakeSubprocess()
    manager = _warp_manager_with_env(monkeypatch, tmp_path, fake)
    monkeypatch.setattr(WarpManager, "_find_binary", staticmethod(lambda *_a: None))

    with pytest.raises(RuntimeError, match="usque 未安装"):
        asyncio.run(manager._start_mode("usque", 1080, 0, None))

    assert fake.commands == []
    assert manager._process is None


def test_start_mode_usque_propagates_a_failed_registration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    import souwen.server.warp as warp_module

    fake = _FakeSubprocess()
    monkeypatch.setattr(warp_module, "WARP_DATA_DIR", tmp_path)
    monkeypatch.setattr(warp_module, "subprocess", fake)
    monkeypatch.setenv("WARP_USQUE_TRANSPORT", "quic")
    monkeypatch.delenv("WARP_USQUE_CONFIG", raising=False)
    manager = WarpManager()
    monkeypatch.setattr(WarpManager, "_find_binary", staticmethod(lambda *_a: "usque"))

    async def failed_register(*_args: object) -> tuple[bool, str]:
        return False, "exit=1: failed to read user input"

    monkeypatch.setattr(WarpManager, "_usque_register", staticmethod(failed_register))

    with pytest.raises(RuntimeError, match="failed to read user input"):
        asyncio.run(manager._start_mode("usque", 1080, 0, None))

    assert fake.commands == []
    assert manager._process is None


def test_usque_register_builds_the_register_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    import souwen.server.warp as warp_module

    fake = _FakeSubprocess()
    monkeypatch.setattr(warp_module, "subprocess", fake)
    config_file = tmp_path / "registered.json"
    monkeypatch.setenv("WARP_DEVICE_NAME", "probe-device")
    asyncio.run(WarpManager._usque_register("usque", str(config_file)))
    # --accept-tos 不是可选项：不带它 usque 会读 stdin 询问 TOS，服务进程的
    # stdin 不是终端，注册必然失败（容器里的真实失败形态）。
    assert fake.run_calls == [
        ["usque", "-c", str(config_file), "register", "--accept-tos", "-n", "probe-device"]
    ]


def test_start_mode_usque_is_dispatched_to_a_real_implementation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """复核 R1 反例：_start_mode('usque') 此前抛 AttributeError。"""

    assert hasattr(WarpManager, "_start_usque")

    fake = _FakeSubprocess()
    monkeypatch.setenv("WARP_USQUE_TRANSPORT", "quic")
    manager = _warp_manager_with_env(monkeypatch, tmp_path, fake)
    usque_bin = tmp_path / "usque"
    monkeypatch.setattr(WarpManager, "_find_binary", staticmethod(lambda *_a: str(usque_bin)))

    asyncio.run(manager._start_mode("usque", 1080, 0, None))

    assert fake.commands, "_start_mode('usque') must reach the real start method"
