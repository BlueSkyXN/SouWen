"""SouWen WARP 代理运行时管理器

提供从管理面板和 API 动态控制 Cloudflare WARP 代理的能力。
支持 wireproxy、kernel、usque、warp-cli、external 等模式。

状态持久化通过 /run/souwen-warp.json 与 shell entrypoint 共享。
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import re as _re
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("souwen.warp")

STATE_FILE = Path("/run/souwen-warp.json")
WARP_DATA_DIR = Path("/app/data")

# ---------- input sanitisation helpers ----------

_SAFE_TOKEN_RE = _re.compile(r"^[\w.:/+@=-]{1,512}$")


def _validate_bind_address(addr: str) -> str:
    """确保 bind address 是合法的 IP 地址字面量。"""
    try:
        return str(ipaddress.ip_address(addr))
    except ValueError:
        raise ValueError(f"非法 bind_address: {addr!r}") from None  # noqa: B904


def _validate_port(port: int) -> int:
    """确保端口号在合法范围内。"""
    if not (0 < port < 65536):
        raise ValueError(f"非法端口号: {port}")
    return port


def _sanitize_token(value: str | None, label: str = "参数") -> str | None:
    """校验简单 token 类字符串（路径/用户名/密码/key）不含 shell 元字符。"""
    if value is None:
        return None
    if not _SAFE_TOKEN_RE.match(value):
        raise ValueError(f"{label} 包含非法字符: {value!r}")
    return value


class WarpStatus(str, Enum):
    DISABLED = "disabled"
    STARTING = "starting"
    ENABLED = "enabled"
    STOPPING = "stopping"
    ERROR = "error"


class WarpMode(str, Enum):
    AUTO = "auto"
    WIREPROXY = "wireproxy"
    KERNEL = "kernel"
    USQUE = "usque"
    WARP_CLI = "warp-cli"
    EXTERNAL = "external"


@dataclass
class WarpState:
    owner: str = "none"  # none | shell | python
    mode: str = "auto"
    status: str = "disabled"
    socks_port: int = 1080
    http_port: int = 0  # HTTP 代理端口（usque/warp-cli）
    pid: int = 0
    interface: str = "wg0"
    ip: str = ""
    last_error: str = ""
    config_path: str = ""
    protocol: str = "wireguard"  # wireguard | masque | official
    proxy_type: str = "socks5"  # socks5 | http | both

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "mode": self.mode,
            "status": self.status,
            "socks_port": self.socks_port,
            "http_port": self.http_port,
            "pid": self.pid,
            "interface": self.interface,
            "ip": self.ip,
            "last_error": self.last_error,
            "config_path": self.config_path,
            "protocol": self.protocol,
            "proxy_type": self.proxy_type,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WarpState:
        return cls(
            owner=d.get("owner", "none"),
            mode=d.get("mode", "auto"),
            status=d.get("status", "disabled"),
            socks_port=d.get("socks_port", 1080),
            http_port=d.get("http_port", 0),
            pid=d.get("pid", 0),
            interface=d.get("interface", "wg0"),
            ip=d.get("ip", ""),
            last_error=d.get("last_error", ""),
            config_path=d.get("config_path", ""),
            protocol=d.get("protocol", "wireguard"),
            proxy_type=d.get("proxy_type", "socks5"),
        )


class WarpManager:
    """WARP 代理生命周期管理器 (单例)"""

    _instance: WarpManager | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._state = WarpState()
        self._process: subprocess.Popen | None = None
        self._http_process: subprocess.Popen | None = None
        self._warp_svc_process: subprocess.Popen | None = None

    @classmethod
    def get_instance(cls) -> WarpManager:
        """获取 WarpManager 全局单例 — 线程内首次调用时延迟创建"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------ state file I/O ------

    def _save_state(self) -> None:
        """将当前 WARP 状态持久化到 /run/souwen-warp.json 文件

        便于 shell 脚本和 Python 进程间状态同步。写入失败时静默处理。
        """
        try:
            STATE_FILE.write_text(
                json.dumps(self._state.to_dict(), ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _load_state(self) -> WarpState | None:
        """从 /run/souwen-warp.json 加载已持久化的 WARP 状态

        用于启动时恢复 shell 脚本启动的 WARP 进程的状态。
        解析失败时返回 None。

        Returns:
            WarpState 或 None
        """
        if not STATE_FILE.is_file():
            return None
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return WarpState.from_dict(data)
        except (json.JSONDecodeError, OSError):
            return None

    # ------ capability detection ------

    @staticmethod
    def _has_wireproxy() -> bool:
        """检测当前系统是否已安装 wireproxy 二进制（用户态模式可用性）"""
        return shutil.which("wireproxy") is not None

    @staticmethod
    def _has_kernel_wg() -> bool:
        """检测内核 WireGuard 模式所需依赖是否齐备

        需要同时满足三个条件：
            1. 存在 wg-quick（WireGuard 用户空间工具）
            2. 存在 microsocks（轻量 SOCKS5 代理）
            3. /dev/net/tun 存在（容器需要 NET_ADMIN 权限）
        """
        return (
            shutil.which("wg-quick") is not None
            and shutil.which("microsocks") is not None
            and Path("/dev/net/tun").exists()
        )

    @staticmethod
    def _has_usque() -> bool:
        """检测 usque 二进制是否可用"""
        return shutil.which("usque") is not None

    @staticmethod
    def _has_warp_cli() -> bool:
        """检测 warp-cli 和 GOST 是否可用"""
        return shutil.which("warp-cli") is not None and shutil.which("gost") is not None

    def detect_best_mode(self) -> str:
        """自动检测最优可用 WARP 模式

        优先级：external(已配置) > usque > wireproxy > kernel > none

        Returns:
            "external" / "usque" / "wireproxy" / "kernel" / "none"
        """
        from souwen.config import get_config

        cfg = get_config()
        if cfg.warp_external_proxy:
            return "external"
        if self._has_usque():
            return "usque"
        if self._has_wireproxy():
            return "wireproxy"
        if self._has_kernel_wg():
            return "kernel"
        return "none"

    @staticmethod
    def _local_socks_url(port: int) -> str:
        """构造本机 SOCKS5 代理地址，包含可选认证。"""
        from souwen.config import get_config

        cfg = get_config()
        if cfg.warp_proxy_username and cfg.warp_proxy_password:
            return f"{cfg.warp_proxy_username}:{cfg.warp_proxy_password}@127.0.0.1:{port}"
        return f"127.0.0.1:{port}"

    @staticmethod
    def _check_socks_alive(port: int) -> bool:
        """检查 SOCKS5 代理是否存活 — 发送 curl 测试请求

        通过 curl 命令向 Cloudflare 1.1.1.1 发送 HTTPS 请求，检查响应中是否包含 "warp="。

        Args:
            port: SOCKS5 监听端口

        Returns:
            True 当代理响应正常，False 当超时或错误
        """
        try:
            result = subprocess.run(
                [
                    "curl",
                    "-s",
                    "--socks5-hostname",
                    WarpManager._local_socks_url(port),
                    "--max-time",
                    "3",
                    "https://1.1.1.1/cdn-cgi/trace",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return "warp=" in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    @staticmethod
    def _get_warp_ip(port: int) -> str:
        """获取通过 WARP 代理的外网 IP 地址

        使用 curl 通过 SOCKS5 代理查询 1.1.1.1/cdn-cgi/trace，提取响应中的 "ip=" 字段。

        Args:
            port: SOCKS5 监听端口

        Returns:
            IP 地址字符串，或 "unknown" 当查询失败
        """
        try:
            result = subprocess.run(
                [
                    "curl",
                    "-s",
                    "--socks5-hostname",
                    WarpManager._local_socks_url(port),
                    "--max-time",
                    "3",
                    "https://1.1.1.1/cdn-cgi/trace",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.splitlines():
                if line.startswith("ip="):
                    return line[3:]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return "unknown"

    @staticmethod
    def _check_external_proxy_alive(proxy_url: str) -> bool:
        """检查外部代理是否可用 — 使用 curl 通过代理访问 Cloudflare trace"""
        if not proxy_url:
            return False
        try:
            result = subprocess.run(
                [
                    "curl",
                    "-s",
                    "--proxy",
                    proxy_url,
                    "--max-time",
                    "3",
                    "https://1.1.1.1/cdn-cgi/trace",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return "warp=" in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    @staticmethod
    def _get_external_proxy_ip(proxy_url: str) -> str:
        """获取通过外部代理出口访问时的 IP 地址"""
        if not proxy_url:
            return "unknown"
        try:
            result = subprocess.run(
                [
                    "curl",
                    "-s",
                    "--proxy",
                    proxy_url,
                    "--max-time",
                    "3",
                    "https://1.1.1.1/cdn-cgi/trace",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.splitlines():
                if line.startswith("ip="):
                    return line[3:]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return "unknown"

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        """检查进程是否还活着 — 使用 os.kill(pid, 0) 信号检查

        Args:
            pid: 进程 ID

        Returns:
            True 当进程仍在运行，False 当进程不存在或权限不足
        """
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    # ------ reconcile (startup) ------

    async def reconcile(self) -> None:
        """启动时协调 — 检测 shell 脚本已启动的 WARP 并接管状态

        启动流程：
        1. 尝试从 /run/souwen-warp.json 加载 shell 启动的 WARP 状态
        2. 验证 shell 启动的 WARP 是否仍然存活（SOCKS5 响应检查）
        3. 若存活，继承该状态；否则标记为 disabled
        4. 检查配置文件中 warp_enabled 选项，若需要则启动 WARP

        不阻塞初始化，后台异步启动新的 WARP 实例。
        """
        async with self._lock:
            shell_state = self._load_state()
            if shell_state and shell_state.status == "enabled":
                # 验证 shell 启动的 WARP 是否仍然存活
                alive = self._check_socks_alive(shell_state.socks_port)
                if alive:
                    self._state = shell_state
                    logger.info(
                        "已检测到 shell 启动的 WARP (模式=%s, 端口=%d, PID=%d)",
                        shell_state.mode,
                        shell_state.socks_port,
                        shell_state.pid,
                    )
                    return
                else:
                    logger.warning("shell 状态文件存在但 SOCKS 代理无响应，标记为 disabled")

            # 也检查 config 中是否要求启用
            from souwen.config import get_config

            cfg = get_config()
            if cfg.warp_enabled and self._state.status == "disabled":
                logger.info("配置文件要求启用 WARP，正在启动...")
                # 释放锁后调用 enable
                asyncio.get_event_loop().call_soon(
                    lambda: asyncio.ensure_future(
                        self.enable(
                            mode=cfg.warp_mode,
                            socks_port=cfg.warp_socks_port,
                            endpoint=cfg.warp_endpoint,
                            http_port=cfg.warp_http_port,
                        )
                    )
                )

    def _auto_mode_candidates(self) -> list[str]:
        """按无特权优先顺序返回 auto 模式可尝试的候选链。"""
        from souwen.config import get_config

        cfg = get_config()
        candidates: list[str] = []
        if cfg.warp_external_proxy:
            candidates.append("external")
        if self._has_usque():
            candidates.append("usque")
        if self._has_wireproxy():
            candidates.append("wireproxy")
        if self._has_kernel_wg():
            candidates.append("kernel")
        return candidates

    async def _start_mode(
        self,
        mode: str,
        socks_port: int,
        http_port: int,
        endpoint: str | None,
    ) -> None:
        """按指定模式启动代理，失败时抛出异常。"""
        if mode == "wireproxy":
            await self._start_wireproxy(socks_port, endpoint)
        elif mode == "kernel":
            success = await self._start_kernel(socks_port, endpoint)
            if not success:
                raise RuntimeError(self._state.last_error or "内核模式启动失败")
        elif mode == "usque":
            await self._start_usque(socks_port, http_port, endpoint)
        elif mode == "warp-cli":
            success = await self._start_warp_cli(socks_port, http_port, endpoint)
            if not success:
                raise RuntimeError(self._state.last_error or "warp-cli 模式启动失败")
        elif mode == "external":
            await self._start_external()
        else:
            raise RuntimeError(f"未知模式: {mode}")

    def _cleanup_failed_start(self, mode: str) -> None:
        """清理失败候选模式遗留的进程/接口，便于 auto 继续降级。"""
        for attr in ("_process", "_http_process"):
            proc = getattr(self, attr)
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
            setattr(self, attr, None)
        if mode == "kernel":
            try:
                subprocess.run(["wg-quick", "down", "wg0"], capture_output=True, timeout=10)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
        if mode == "warp-cli":
            try:
                subprocess.run(
                    ["warp-cli", "--accept-tos", "disconnect"],
                    capture_output=True,
                    timeout=10,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            if self._warp_svc_process and self._warp_svc_process.poll() is None:
                self._warp_svc_process.terminate()
                try:
                    self._warp_svc_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._warp_svc_process.kill()
            self._warp_svc_process = None
        self._state.pid = 0
        self._state.http_port = 0

    # ------ enable / disable ------

    async def enable(
        self,
        mode: str = "auto",
        socks_port: int = 1080,
        endpoint: str | None = None,
        http_port: int | None = None,
    ) -> dict[str, Any]:
        """启用 WARP 代理

        加锁保证并发安全，按 mode 选择启动路径；auto 模式失败时自动回退。
        启动成功后会更新 SOUWEN_PROXY 环境变量并重载配置，使新代理立即生效。

        Args:
            mode: 启动模式（auto / wireproxy / kernel / usque / warp-cli / external）
            socks_port: 本地 SOCKS5 监听端口
            endpoint: 自定义 WARP Endpoint（可选）
            http_port: 本地 HTTP 代理监听端口（None 表示使用配置值）

        Returns:
            {"ok": True, "mode": str, "ip": str} 成功；
            {"ok": False, "error": str} 失败
        """
        async with self._lock:
            if self._state.status in ("enabled", "starting"):
                return {"ok": False, "error": f"WARP 当前状态: {self._state.status}，请先禁用"}

            self._state.status = "starting"
            self._state.last_error = ""
            self._state.socks_port = socks_port
            self._state.http_port = 0

            try:
                from souwen.config import get_config

                cfg = get_config()
                effective_http_port = cfg.warp_http_port if http_port is None else http_port

                if mode == "auto":
                    candidate_modes = self._auto_mode_candidates()
                    if not candidate_modes:
                        self._state.status = "error"
                        self._state.last_error = "未检测到可用的 WARP 组件"
                        self._save_state()
                        return {"ok": False, "error": self._state.last_error}
                    logger.info("WARP auto 候选链: %s", " > ".join(candidate_modes))
                else:
                    candidate_modes = [mode]

                last_error = ""
                for index, resolved_mode in enumerate(candidate_modes):
                    self._state.mode = resolved_mode
                    try:
                        await self._start_mode(
                            resolved_mode, socks_port, effective_http_port, endpoint
                        )

                        ready = (
                            True
                            if self._state.mode == "external"
                            else await self._wait_for_proxy(socks_port, cfg.warp_startup_timeout)
                        )
                        if not ready and mode == "auto":
                            raise RuntimeError("WARP 代理验证超时")
                        if ready:
                            if self._state.mode == "external":
                                self._state.ip = self._get_external_proxy_ip(
                                    self._state.config_path
                                )
                            else:
                                self._state.ip = self._get_warp_ip(socks_port)
                            self._state.status = "enabled"
                        else:
                            self._state.ip = "pending"
                            self._state.status = "enabled"
                            logger.warning("WARP 代理验证超时，但进程已启动")
                        break
                    except Exception as exc:
                        last_error = str(exc)
                        self._cleanup_failed_start(resolved_mode)
                        if mode != "auto" or index == len(candidate_modes) - 1:
                            raise
                        logger.warning(
                            "%s 模式失败，回退到 %s: %s",
                            resolved_mode,
                            candidate_modes[index + 1],
                            exc,
                        )
                else:
                    raise RuntimeError(last_error or "WARP auto 模式启动失败")

                self._state.owner = "python"
                self._save_state()

                # 更新 SouWen 代理配置
                if self._state.mode == "external":
                    self._apply_external_proxy(self._state.config_path)
                else:
                    self._apply_proxy(socks_port)

                return {"ok": True, "mode": self._state.mode, "ip": self._state.ip}

            except Exception as exc:
                self._state.status = "error"
                self._state.last_error = str(exc)
                self._save_state()
                logger.exception("WARP 启动失败")
                return {"ok": False, "error": str(exc)}

    async def disable(self) -> dict[str, Any]:
        """禁用 WARP 代理 — 终止进程并清理网络配置

        清理顺序：
            1. 终止 wireproxy 或 microsocks 子进程（先 SIGTERM 再 SIGKILL）
            2. 若为 kernel 模式，调用 wg-quick down 拆除 WireGuard 接口
            3. 清空 SOUWEN_PROXY 环境变量并重载配置
            4. 重置内部状态并持久化

        Returns:
            {"ok": True, "message": str} 或 {"ok": False, "error": str}
        """
        async with self._lock:
            if self._state.status == "disabled":
                return {"ok": True, "message": "WARP 已处于关闭状态"}
            if self._state.status == "stopping":
                return {"ok": False, "error": "WARP 正在关闭中"}

            self._state.status = "stopping"

            try:
                mode = self._state.mode

                # 停止进程
                if self._process and self._process.poll() is None:
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
                    self._process = None
                elif self._state.pid > 0 and self._pid_alive(self._state.pid):
                    try:
                        os.kill(self._state.pid, signal.SIGTERM)
                        time.sleep(1)
                        if self._pid_alive(self._state.pid):
                            os.kill(self._state.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass

                # 内核模式: 还需拆除 WireGuard 接口
                if mode == "kernel":
                    try:
                        subprocess.run(
                            ["wg-quick", "down", self._state.interface],
                            capture_output=True,
                            timeout=10,
                        )
                    except (subprocess.TimeoutExpired, FileNotFoundError):
                        pass

                # warp-cli 模式: 断开连接并停止本管理器启动的守护进程
                if mode == "warp-cli":
                    try:
                        subprocess.run(
                            ["warp-cli", "--accept-tos", "disconnect"],
                            capture_output=True,
                            timeout=10,
                        )
                    except (subprocess.TimeoutExpired, FileNotFoundError):
                        pass
                    if self._warp_svc_process and self._warp_svc_process.poll() is None:
                        self._warp_svc_process.terminate()
                        try:
                            self._warp_svc_process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            self._warp_svc_process.kill()
                    self._warp_svc_process = None

                # usque 模式: 停止 HTTP 代理进程
                if self._http_process and self._http_process.poll() is None:
                    self._http_process.terminate()
                    try:
                        self._http_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self._http_process.kill()
                self._http_process = None

                # 清除代理配置
                self._clear_proxy()

                self._state = WarpState()
                self._save_state()

                return {"ok": True, "message": "WARP 已关闭"}

            except Exception as exc:
                self._state.status = "error"
                self._state.last_error = str(exc)
                self._save_state()
                return {"ok": False, "error": str(exc)}

    # ------ status ------

    def get_status(self) -> dict[str, Any]:
        """返回当前 WARP 状态快照

        当 status == "enabled" 时会做实时存活校验：
            - wireproxy 模式：检查子进程或 PID 是否仍在运行
            - kernel 模式：检查 PID 或 SOCKS5 是否响应

        若发现进程已退出，会自动将状态改为 error 并持久化。

        Returns:
            包含 status、mode、owner、socks_port、http_port、ip、pid、interface、
            last_error 和 available_modes 的字典
        """
        from souwen.config import get_config

        try:
            cfg = get_config()
        except Exception:
            cfg = None
        s = self._state

        # 实时验证: 如果状态是 enabled, 检查进程是否还活着
        if s.status == "enabled":
            alive = False
            if s.mode == "wireproxy":
                alive = (self._process and self._process.poll() is None) or self._pid_alive(s.pid)
            elif s.mode == "kernel":
                alive = self._pid_alive(s.pid) or self._check_socks_alive(s.socks_port)
            elif s.mode in ("usque", "warp-cli"):
                alive = (self._process and self._process.poll() is None) or self._pid_alive(s.pid)
            elif s.mode == "external":
                alive = self._check_external_proxy_alive(s.config_path)
            if not alive:
                s.status = "error"
                s.last_error = "WARP 进程已退出"
                self._save_state()

        return {
            "status": s.status,
            "mode": s.mode,
            "owner": s.owner,
            "socks_port": s.socks_port,
            "http_port": s.http_port,
            "ip": s.ip,
            "pid": s.pid,
            "interface": s.interface if s.mode == "kernel" else None,
            "last_error": s.last_error,
            "protocol": s.protocol,
            "proxy_type": s.proxy_type,
            "available_modes": {
                "wireproxy": self._has_wireproxy(),
                "kernel": self._has_kernel_wg(),
                "usque": self._has_usque(),
                "warp-cli": self._has_warp_cli(),
                "external": bool(cfg.warp_external_proxy) if cfg else False,
            },
        }

    # ------ internal: wireproxy ------

    async def _start_wireproxy(self, socks_port: int, endpoint: str | None) -> None:
        """启动 wireproxy 子进程（用户态 SOCKS5）

        Raises:
            RuntimeError: 配置缺失或 wireproxy 未安装
        """
        conf_path = self._get_wireproxy_config(socks_port, endpoint)
        if not conf_path:
            raise RuntimeError("无法获取 wireproxy 配置 (需要 WARP_CONFIG_B64 或已注册配置)")

        if not shutil.which("wireproxy"):
            raise RuntimeError("wireproxy 未安装")

        self._process = subprocess.Popen(
            ["wireproxy", "-c", str(conf_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._state.pid = self._process.pid
        self._state.config_path = str(conf_path)

    def _get_wireproxy_config(self, socks_port: int, endpoint: str | None) -> Path | None:
        """获取 wireproxy 配置文件 — 三级回退策略

        优先级：
            1. WARP_CONFIG_B64 环境变量（Base64 配置）
            2. /app/data/wireproxy.conf 持久化文件
            3. 通过 wgcf 在线注册新账号

        Returns:
            就绪的配置文件路径，或 None 表示无可用配置
        """
        conf = Path("/tmp/wireproxy.conf")

        # 1. WARP_CONFIG_B64 环境变量
        b64 = os.getenv("WARP_CONFIG_B64", "")
        if b64:
            import base64

            conf.write_bytes(base64.b64decode(b64))
            return self._patch_wireproxy_conf(conf, socks_port, endpoint)

        # 2. 持久化文件
        persistent = WARP_DATA_DIR / "wireproxy.conf"
        if persistent.is_file():
            import shutil as shu

            shu.copy2(persistent, conf)
            return self._patch_wireproxy_conf(conf, socks_port, endpoint)

        # 3. 自动注册
        raw_conf = self._wgcf_register()
        if raw_conf:
            self._convert_wgcf_to_wireproxy(raw_conf, conf, socks_port)
            if persistent.parent.is_dir():
                import shutil as shu

                shu.copy2(conf, persistent)
            raw_conf.unlink(missing_ok=True)
            return self._patch_wireproxy_conf(conf, socks_port, endpoint)

        return None

    @staticmethod
    def _wgcf_register() -> Path | None:
        """调用 wgcf 注册 Cloudflare WARP 账号并生成 WireGuard 配置

        在临时目录执行 `wgcf register` + `wgcf generate`，将生成的
        wgcf-profile.conf 复制到 /tmp/wgcf-raw.conf 返回。

        Returns:
            原始 WireGuard 配置文件路径，或 None 表示注册失败
        """
        if not shutil.which("wgcf"):
            return None
        import tempfile

        tmpdir = Path(tempfile.mkdtemp())
        try:
            subprocess.run(
                ["wgcf", "register", "--accept-tos"],
                cwd=tmpdir,
                capture_output=True,
                timeout=30,
            )
            subprocess.run(
                ["wgcf", "generate"],
                cwd=tmpdir,
                capture_output=True,
                timeout=30,
            )
            profile = tmpdir / "wgcf-profile.conf"
            if profile.is_file():
                out = Path("/tmp/wgcf-raw.conf")
                import shutil as shu

                shu.copy2(profile, out)
                return out
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        finally:
            import shutil as shu

            shu.rmtree(tmpdir, ignore_errors=True)
        return None

    @staticmethod
    def _convert_wgcf_to_wireproxy(src: Path, dst: Path, socks_port: int) -> None:
        """将 wgcf 生成的 WireGuard 配置转换为 wireproxy 格式

        提取 PrivateKey、Address、PublicKey、Endpoint 字段，并附加
        [Socks5] 段以监听本地端口。
        """
        from souwen.config import get_config

        cfg = get_config()
        bind_addr = cfg.warp_bind_address or "127.0.0.1"
        text = src.read_text(encoding="utf-8")
        private_key = ""
        ipv4_addr = ""
        public_key = ""
        endpoint_val = ""

        for line in text.splitlines():
            if line.startswith("PrivateKey"):
                private_key = line.split("=", 1)[1].strip()
            elif line.startswith("Address"):
                m = _re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d+)", line)
                if m and not ipv4_addr:
                    ipv4_addr = m.group(1)
            elif line.startswith("PublicKey"):
                public_key = line.split("=", 1)[1].strip()
            elif line.startswith("Endpoint"):
                endpoint_val = line.split("=", 1)[1].strip()

        dst.write_text(
            f"[Interface]\nPrivateKey = {private_key}\nAddress = {ipv4_addr}\n\n"
            f"[Peer]\nPublicKey = {public_key}\nAllowedIPs = 0.0.0.0/0\n"
            f"Endpoint = {endpoint_val}\nPersistentKeepalive = 15\n\n"
            f"[Socks5]\nBindAddress = {bind_addr}:{socks_port}\n",
            encoding="utf-8",
        )

    @staticmethod
    def _patch_wireproxy_conf(conf: Path, socks_port: int, endpoint: str | None) -> Path:
        """就地修改 wireproxy 配置：覆盖 BindAddress 与可选 Endpoint

        Returns:
            原配置文件路径（已写入新内容）
        """
        from souwen.config import get_config

        cfg = get_config()
        bind_addr = cfg.warp_bind_address or "127.0.0.1"
        text = conf.read_text(encoding="utf-8")

        text = _re.sub(
            r"^BindAddress\s*=.*$",
            f"BindAddress = {bind_addr}:{socks_port}",
            text,
            flags=_re.MULTILINE,
        )
        if endpoint:
            text = _re.sub(r"^Endpoint\s*=.*$", f"Endpoint = {endpoint}", text, flags=_re.MULTILINE)
        conf.write_text(text, encoding="utf-8")
        return conf

    # ------ internal: kernel ------

    async def _start_kernel(self, socks_port: int, endpoint: str | None) -> bool:
        """启动内核 WireGuard + microsocks 模式

        流程：
            1. 写入 /etc/wireguard/wg0.conf（B64 / 持久化 / wgcf 三级回退）
            2. 修整配置（注入 Address、AllowedIPs、PersistentKeepalive 等）
            3. 执行 wg-quick up wg0 启动内核接口
            4. 启动 microsocks 子进程对外提供 SOCKS5 接入

        Returns:
            True 表示启动成功，False 表示失败（last_error 已记录原因）
        """
        from souwen.config import get_config

        cfg = get_config()
        bind_addr = cfg.warp_bind_address or "127.0.0.1"
        wg_conf = Path("/etc/wireguard/wg0.conf")
        wg_conf.parent.mkdir(parents=True, exist_ok=True)

        # 获取配置
        b64 = os.getenv("WARP_CONFIG_B64", "")
        if b64:
            import base64

            wg_conf.write_bytes(base64.b64decode(b64))
        elif (WARP_DATA_DIR / "wg0.conf").is_file():
            import shutil as shu

            shu.copy2(WARP_DATA_DIR / "wg0.conf", wg_conf)
        else:
            raw = self._wgcf_register()
            if not raw:
                self._state.last_error = "wgcf 注册失败"
                return False
            import shutil as shu

            shu.copy2(raw, wg_conf)
            raw.unlink(missing_ok=True)
            if WARP_DATA_DIR.is_dir():
                shu.copy2(wg_conf, WARP_DATA_DIR / "wg0.conf")

        # 洗白配置
        self._patch_kernel_conf(wg_conf, endpoint)

        # 启动 WireGuard 接口
        try:
            result = subprocess.run(
                ["wg-quick", "up", "wg0"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                self._state.last_error = f"wg-quick up 失败: {result.stderr.strip()}"
                return False
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            self._state.last_error = f"wg-quick 执行失败: {exc}"
            return False

        # 启动 microsocks
        if not shutil.which("microsocks"):
            self._state.last_error = "microsocks 未安装"
            subprocess.run(["wg-quick", "down", "wg0"], capture_output=True, timeout=10)
            return False

        self._process = subprocess.Popen(
            ["microsocks", "-i", bind_addr, "-p", str(socks_port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._state.pid = self._process.pid
        return True

    @staticmethod
    def _build_usque_cmd(
        usque_bin: str,
        config_path: str,
        subcommand: str,
        bind_addr: str,
        port: int,
        *,
        http2: bool,
        username: str | None,
        password: str | None,
    ) -> list[str]:
        bind_addr = _validate_bind_address(bind_addr)
        port = _validate_port(port)
        if subcommand not in ("socks", "http-proxy"):
            raise ValueError(f"非法 usque 子命令: {subcommand!r}")
        _sanitize_token(username, "proxy username")
        _sanitize_token(password, "proxy password")
        cmd = [usque_bin, "-c", config_path]
        if http2:
            cmd.append("--http2")
        cmd.extend([subcommand, "--bind", bind_addr, "--port", str(port)])
        if username and password:
            cmd.extend(["-u", username, "-w", password])
        return cmd

    async def _start_usque(self, socks_port: int, http_port: int, endpoint: str | None) -> None:
        """启动 usque MASQUE/QUIC 代理

        usque 是 Cloudflare WARP 的 MASQUE 协议开源实现。
        支持 SOCKS5 和 HTTP 代理模式。

        流程：
            1. 查找 usque 二进制和配置文件
            2. 如果没有配置，尝试自动注册 (usque register)
            3. 启动 usque socks 或 usque http-proxy 子进程

        Raises:
            RuntimeError: usque 未安装或注册失败
        """
        from souwen.config import get_config

        cfg = get_config()
        _ = endpoint
        bind_addr = _validate_bind_address(cfg.warp_bind_address or "127.0.0.1")
        transport = (cfg.warp_usque_transport or "auto").lower()
        if transport not in ("auto", "quic", "http2"):
            raise ValueError(f"非法 usque transport: {transport!r}")

        usque_bin = cfg.warp_usque_path or shutil.which("usque")
        if not usque_bin or not Path(usque_bin).is_file():
            raise RuntimeError("usque 未安装")

        # 确定配置文件路径
        config_path = cfg.warp_usque_config
        if not config_path:
            # 默认查找路径: /app/data/usque-config.json > 当前目录 config.json
            for candidate in [WARP_DATA_DIR / "usque-config.json", Path("config.json")]:
                if candidate.is_file():
                    config_path = str(candidate)
                    break

        # 如果没有配置文件，尝试自动注册
        if not config_path or not Path(config_path).is_file():
            config_path = str(WARP_DATA_DIR / "usque-config.json")
            Path(config_path).parent.mkdir(parents=True, exist_ok=True)
            reg_result = await self._usque_register(usque_bin, config_path)
            if not reg_result:
                raise RuntimeError("usque 注册失败（可能触发速率限制）")

        async def start_usque_processes(*, http2: bool) -> None:
            cmd = self._build_usque_cmd(
                usque_bin,
                config_path,
                "socks",
                bind_addr,
                socks_port,
                http2=http2,
                username=cfg.warp_proxy_username,
                password=cfg.warp_proxy_password,
            )
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._state.pid = self._process.pid
            self._state.config_path = config_path
            self._state.protocol = "masque"
            self._state.proxy_type = "socks5"

            # 如果配置了 HTTP 端口，额外启动 HTTP 代理进程
            if http_port > 0:
                http_cmd = self._build_usque_cmd(
                    usque_bin,
                    config_path,
                    "http-proxy",
                    bind_addr,
                    http_port,
                    http2=http2,
                    username=cfg.warp_proxy_username,
                    password=cfg.warp_proxy_password,
                )
                self._http_process = subprocess.Popen(
                    http_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._state.http_port = http_port
                self._state.proxy_type = "both"

        use_http2 = transport == "http2"
        await start_usque_processes(http2=use_http2)

        if transport == "auto" and not await self._wait_for_proxy(
            socks_port, cfg.warp_startup_timeout
        ):
            logger.warning("usque QUIC 启动健康检查失败，重试 HTTP/2 transport")
            self._cleanup_failed_start("usque")
            await start_usque_processes(http2=True)

    @staticmethod
    async def _usque_register(usque_bin: str, config_path: str) -> bool:
        """调用 usque register 注册新的 WARP 账号

        Args:
            usque_bin: usque 二进制路径
            config_path: 配置输出路径

        Returns:
            True 注册成功，False 失败
        """
        from souwen.config import get_config

        cfg = get_config()
        cmd = [usque_bin, "-c", config_path, "register"]
        if cfg.warp_device_name:
            _sanitize_token(cfg.warp_device_name, "warp_device_name")
            cmd.extend(["-n", cfg.warp_device_name])
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0 and Path(config_path).is_file()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    async def _start_warp_cli(
        self,
        socks_port: int,
        http_port: int,
        endpoint: str | None,
    ) -> bool:
        """启动 warp-cli 官方客户端 + GOST 代理

        流程：
            1. 启动 warp-svc 守护进程
            2. 配置 warp-cli（注册、模式设置等）
            3. 连接 WARP
            4. 启动 GOST 提供 SOCKS5/HTTP 代理

        Returns:
            True 启动成功，False 失败
        """
        _ = endpoint
        if not shutil.which("warp-cli") or not shutil.which("gost"):
            self._state.last_error = "warp-cli 或 GOST 未安装"
            return False

        # 启动 warp-svc 守护进程
        try:
            self._warp_svc_process = subprocess.Popen(
                ["warp-svc"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await asyncio.sleep(2)  # 等待守护进程就绪
        except FileNotFoundError:
            self._state.last_error = "warp-svc 未找到"
            return False

        # 检查注册状态，必要时注册
        try:
            reg_check = subprocess.run(
                ["warp-cli", "--accept-tos", "registration", "show"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if reg_check.returncode != 0:
                # 需要注册
                from souwen.config import get_config

                cfg = get_config()

                subprocess.run(
                    ["warp-cli", "--accept-tos", "registration", "new"],
                    capture_output=True,
                    timeout=15,
                )

                # 设置 License Key（如果有）
                if cfg.warp_license_key:
                    _sanitize_token(cfg.warp_license_key, "warp_license_key")
                    subprocess.run(
                        [
                            "warp-cli",
                            "--accept-tos",
                            "registration",
                            "license",
                            cfg.warp_license_key,
                        ],
                        capture_output=True,
                        timeout=10,
                    )

                # 设置 ZeroTrust Token（如果有）
                if cfg.warp_team_token:
                    _sanitize_token(cfg.warp_team_token, "warp_team_token")
                    subprocess.run(
                        [
                            "warp-cli",
                            "--accept-tos",
                            "registration",
                            "organization",
                            "--jwt-token",
                            cfg.warp_team_token,
                        ],
                        capture_output=True,
                        timeout=15,
                    )
        except subprocess.TimeoutExpired:
            self._state.last_error = "warp-cli 注册失败: 命令超时"
            return False
        except FileNotFoundError as exc:
            self._state.last_error = f"warp-cli 注册失败: {exc}"
            return False

        # 设置代理模式
        subprocess.run(
            ["warp-cli", "--accept-tos", "mode", "proxy"],
            capture_output=True,
            timeout=5,
        )

        # 连接
        result = subprocess.run(
            ["warp-cli", "--accept-tos", "connect"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            self._state.last_error = f"warp-cli connect 失败: {result.stderr.strip()}"
            return False

        # 启动 GOST 代理
        from souwen.config import get_config

        cfg = get_config()
        bind_addr = _validate_bind_address(cfg.warp_bind_address or "127.0.0.1")
        _validate_port(socks_port)
        # warp-cli proxy 模式默认监听 127.0.0.1:40000
        warp_upstream = "socks5://127.0.0.1:40000"
        if cfg.warp_gost_args:
            # warp_gost_args 允许管理员自定义 GOST 参数，校验每个 token
            gost_args = cfg.warp_gost_args.split()
            for arg in gost_args:
                _sanitize_token(arg, "warp_gost_args")
        elif http_port > 0:
            _validate_port(http_port)
            gost_args = [
                "-L",
                f"socks5://{bind_addr}:{socks_port}",
                "-F",
                warp_upstream,
                "-L",
                f"http://{bind_addr}:{http_port}",
                "-F",
                warp_upstream,
            ]
            self._state.http_port = http_port
        else:
            gost_args = ["-L", f"socks5://{bind_addr}:{socks_port}", "-F", warp_upstream]

        self._process = subprocess.Popen(
            ["gost", *gost_args],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._state.pid = self._process.pid
        self._state.protocol = "official"
        self._state.proxy_type = "both" if self._state.http_port > 0 else "socks5"

        return True

    async def _start_external(self) -> None:
        """启动 external 外部代理模式

        不启动任何进程，仅验证外部代理连通性并记录状态。

        Raises:
            RuntimeError: 外部代理地址未配置或不可达
        """
        from souwen.config import get_config

        cfg = get_config()

        proxy_url = cfg.warp_external_proxy
        if not proxy_url:
            raise RuntimeError("未配置 warp_external_proxy 外部代理地址")

        # 解析代理地址获取端口（用于健康检查）
        port_match = _re.search(r":(\d+)$", proxy_url.rstrip("/"))
        if port_match:
            self._state.socks_port = int(port_match.group(1))

        self._state.protocol = "wireguard"  # 外部代理协议未知，默认 wireguard
        self._state.proxy_type = "socks5" if "socks" in proxy_url.lower() else "http"
        self._state.config_path = proxy_url

        if not self._check_external_proxy_alive(proxy_url):
            raise RuntimeError("外部 WARP 代理不可达")

    @staticmethod
    def _patch_kernel_conf(conf: Path, endpoint: str | None) -> None:
        """规范化内核 WireGuard 配置以适配 wg-quick

        操作：
            - 提取 IPv4 Address 后清除原 Address/AllowedIPs/DNS 字段
            - 在 [Interface] 重新注入 Address，[Peer] 注入 AllowedIPs
            - 强制 PersistentKeepalive=15 防止 NAT 老化
            - 可选覆盖 Endpoint
        """

        text = conf.read_text(encoding="utf-8")
        # 提取 IPv4
        m = _re.search(r"Address\s*=\s*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d+)", text)
        ipv4 = m.group(1) if m else ""
        # 清除旧字段
        text = _re.sub(r"^Address\s*=.*$", "", text, flags=_re.MULTILINE)
        text = _re.sub(r"^AllowedIPs\s*=.*$", "", text, flags=_re.MULTILINE)
        text = _re.sub(r"^DNS\s*=.*$", "", text, flags=_re.MULTILINE)
        # 注入
        if ipv4:
            text = text.replace("[Interface]", f"[Interface]\nAddress = {ipv4}", 1)
        text = text.replace("[Peer]", "[Peer]\nAllowedIPs = 0.0.0.0/0", 1)
        # 心跳
        if "PersistentKeepalive" not in text:
            text = text.replace("[Peer]", "[Peer]\nPersistentKeepalive = 15", 1)
        else:
            text = _re.sub(r"PersistentKeepalive\s*=.*", "PersistentKeepalive = 15", text)
        # Endpoint
        if endpoint:
            text = _re.sub(r"^Endpoint\s*=.*$", f"Endpoint = {endpoint}", text, flags=_re.MULTILINE)
        conf.write_text(text, encoding="utf-8")

    # ------ internal: helpers ------

    async def _wait_for_proxy(self, port: int, retries: int = 10) -> bool:
        """轮询等待 SOCKS5 代理就绪 — 每秒重试一次

        Args:
            port: SOCKS5 端口
            retries: 最大重试次数（默认 10 次 ≈ 10 秒）

        Returns:
            True 表示代理已就绪，False 表示超时
        """
        for _ in range(retries):
            await asyncio.sleep(1)
            if self._check_socks_alive(port):
                return True
        return False

    @staticmethod
    def _apply_proxy(socks_port: int) -> None:
        """将 WARP SOCKS5 代理写入 SOUWEN_PROXY 并重载配置

        重载后所有 HTTP 客户端会自动使用该代理。
        """
        from souwen.config import get_config

        cfg = get_config()
        if cfg.warp_proxy_username and cfg.warp_proxy_password:
            from urllib.parse import quote

            username = quote(cfg.warp_proxy_username, safe="")
            password = quote(cfg.warp_proxy_password, safe="")
            proxy_url = f"socks5://{username}:{password}@127.0.0.1:{socks_port}"
        else:
            proxy_url = f"socks5://127.0.0.1:{socks_port}"
        os.environ["SOUWEN_PROXY"] = proxy_url
        from souwen.config import reload_config

        reload_config()
        logger.info("SOUWEN_PROXY=%s (已重载配置)", proxy_url)

    @staticmethod
    def _apply_external_proxy(proxy_url: str) -> None:
        """将外部 WARP 代理写入 SOUWEN_PROXY 并重载配置"""
        os.environ["SOUWEN_PROXY"] = proxy_url
        from souwen.config import reload_config

        reload_config()
        logger.info("SOUWEN_PROXY=%s (外部代理，已重载配置)", proxy_url)

    @staticmethod
    def _clear_proxy() -> None:
        """移除 SOUWEN_PROXY 环境变量并重载配置 — 关闭 WARP 时调用"""
        os.environ.pop("SOUWEN_PROXY", None)
        from souwen.config import reload_config

        reload_config()
        logger.info("SOUWEN_PROXY 已清除 (已重载配置)")
