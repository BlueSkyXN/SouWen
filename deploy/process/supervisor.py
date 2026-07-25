"""Bounded two-process supervisor for the API runtime and Browser Worker."""

from __future__ import annotations

import json
import logging
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from http.client import HTTPConnection
from typing import Protocol

from souwen import __version__
from souwen.common_runtime.observability import get_source_sha
from souwen.delivery.api.rollout import RolloutMode, resolve_rollout_mode
from souwen.worker.browser_fetch.protocol import (
    BROWSER_WORKER_CONTRACT_MAJOR,
    BROWSER_WORKER_DEFAULT_PORT,
    BROWSER_WORKER_PROVIDER_INVENTORY_DIGEST,
    WorkerProbeResponse,
)


logger = logging.getLogger("souwen.deployment.supervisor")
_FULL_SHA_LENGTH = 40


class ChildProcess(Protocol):
    pid: int
    returncode: int | None

    def poll(self) -> int | None: ...

    def send_signal(self, signum: int) -> None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


ProcessFactory = Callable[[Sequence[str], Mapping[str, str]], ChildProcess]
ReadinessProbe = Callable[["DeploymentSettings", str, float], bool]
Sleep = Callable[[float], None]


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{name} must be a number") from None
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _validated_sha(value: str | None, name: str, *, required: bool) -> str | None:
    normalized = (value or "").strip().lower()
    if not normalized:
        if required:
            raise ValueError(f"{name} must contain an immutable 40-character source SHA")
        return None
    if len(normalized) != _FULL_SHA_LENGTH or any(
        char not in "0123456789abcdef" for char in normalized
    ):
        raise ValueError(f"{name} must contain exactly 40 lowercase hexadecimal characters")
    return normalized


@dataclass(frozen=True, slots=True)
class DeploymentSettings:
    """Validated non-secret process and provenance settings."""

    rollout_mode: RolloutMode
    api_host: str
    api_port: int
    worker_host: str
    worker_port: int
    source_sha: str | None
    wrapper_sha: str | None
    config_revision: str | None
    worker_startup_timeout: float
    worker_restart_limit: int
    worker_restart_backoff: float
    termination_timeout: float

    @property
    def worker_required(self) -> bool:
        return self.rollout_mode is RolloutMode.TARGET

    @classmethod
    def from_env(cls) -> "DeploymentSettings":
        rollout_mode = resolve_rollout_mode()
        api_host = os.environ.get("HOST", "0.0.0.0").strip()
        if api_host not in {"0.0.0.0", "127.0.0.1"}:
            raise ValueError("HOST must be exactly 0.0.0.0 or 127.0.0.1")
        api_port = _bounded_int("PORT", 49265, 1, 65535)
        worker_host = os.environ.get("SOUWEN_BROWSER_WORKER_HOST", "127.0.0.1").strip()
        if worker_host != "127.0.0.1":
            raise ValueError("Browser Worker must bind exactly 127.0.0.1")
        worker_port = _bounded_int(
            "SOUWEN_BROWSER_WORKER_PORT",
            BROWSER_WORKER_DEFAULT_PORT,
            1,
            65535,
        )
        if worker_port == api_port:
            raise ValueError("Browser Worker and API ports must differ")

        source_sha = _validated_sha(
            os.environ.get("SOUWEN_SOURCE_SHA") or get_source_sha(),
            "SOUWEN_SOURCE_SHA",
            required=rollout_mode is RolloutMode.TARGET,
        )
        wrapper_sha = _validated_sha(
            os.environ.get("SOUWEN_WRAPPER_SHA"),
            "SOUWEN_WRAPPER_SHA",
            required=False,
        )
        config_revision = os.environ.get("SOUWEN_CONFIG_REVISION", "").strip() or None
        if rollout_mode is RolloutMode.TARGET and config_revision is None:
            if source_sha is None:  # Defensive; target source SHA is already required above.
                raise ValueError("target rollout requires an immutable config revision")
            config_revision = f"source-{source_sha}"
        if config_revision is not None and not 1 <= len(config_revision) <= 128:
            raise ValueError("SOUWEN_CONFIG_REVISION must contain 1 to 128 characters")

        return cls(
            rollout_mode=rollout_mode,
            api_host=api_host,
            api_port=api_port,
            worker_host=worker_host,
            worker_port=worker_port,
            source_sha=source_sha,
            wrapper_sha=wrapper_sha,
            config_revision=config_revision,
            worker_startup_timeout=_bounded_float(
                "SOUWEN_BROWSER_WORKER_STARTUP_TIMEOUT", 30.0, 1.0, 120.0
            ),
            worker_restart_limit=_bounded_int("SOUWEN_BROWSER_WORKER_RESTART_LIMIT", 3, 0, 10),
            worker_restart_backoff=_bounded_float(
                "SOUWEN_BROWSER_WORKER_RESTART_BACKOFF", 0.5, 0.0, 10.0
            ),
            termination_timeout=_bounded_float(
                "SOUWEN_PROCESS_TERMINATION_TIMEOUT", 10.0, 1.0, 60.0
            ),
        )


def _default_process_factory(command: Sequence[str], env: Mapping[str, str]) -> ChildProcess:
    kwargs: dict[str, object] = {"env": dict(env)}
    if os.name == "posix":
        kwargs["start_new_session"] = True
    elif hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(list(command), **kwargs)


def _worker_readiness(settings: DeploymentSettings, token: str, timeout: float) -> bool:
    request_id = "deployment-supervisor-readiness"
    connection = HTTPConnection(settings.worker_host, settings.worker_port, timeout=timeout)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-SouWen-Contract-Major": str(BROWSER_WORKER_CONTRACT_MAJOR),
        "X-Request-ID": request_id,
        "X-SouWen-Deadline-Ms": str(int((time.time() + timeout) * 1000)),
    }
    try:
        connection.request("GET", "/internal/v1/readiness", headers=headers)
        response = connection.getresponse()
        body = response.read(64 * 1024)
        if response.status != 200:
            return False
        receipt = WorkerProbeResponse.model_validate(json.loads(body))
    except Exception:
        return False
    finally:
        connection.close()
    evidence = receipt.evidence
    return bool(
        receipt.ready
        and receipt.status == "ready"
        and receipt.request_id == request_id
        and evidence.contract_major == BROWSER_WORKER_CONTRACT_MAJOR
        and evidence.source_sha == settings.source_sha
        and evidence.runtime_version == __version__
        and evidence.config_revision == settings.config_revision
        and evidence.provider_inventory_digest == BROWSER_WORKER_PROVIDER_INVENTORY_DIGEST
    )


class DeploymentSupervisor:
    """Own child startup order, signal fanout and bounded Worker restarts."""

    def __init__(
        self,
        settings: DeploymentSettings,
        *,
        process_factory: ProcessFactory = _default_process_factory,
        readiness_probe: ReadinessProbe = _worker_readiness,
        sleep: Sleep = time.sleep,
        token: str | None = None,
    ) -> None:
        self.settings = settings
        self._token = token or secrets.token_urlsafe(48)
        if len(self._token) < 32:
            raise ValueError("Browser Worker token must contain at least 32 characters")
        self._process_factory = process_factory
        self._use_process_groups = process_factory is _default_process_factory
        self._readiness_probe = readiness_probe
        self._sleep = sleep
        self._stop = threading.Event()
        self._signal: int | None = None
        self._api: ChildProcess | None = None
        self._worker: ChildProcess | None = None

    def _child_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["SOUWEN_V2_ROLLOUT"] = self.settings.rollout_mode.value
        env["SOUWEN_BROWSER_WORKER_HOST"] = self.settings.worker_host
        env["SOUWEN_BROWSER_WORKER_PORT"] = str(self.settings.worker_port)
        env["SOUWEN_BROWSER_WORKER_TOKEN"] = self._token
        if self.settings.source_sha is not None:
            env["SOUWEN_SOURCE_SHA"] = self.settings.source_sha
        if self.settings.wrapper_sha is not None:
            env["SOUWEN_WRAPPER_SHA"] = self.settings.wrapper_sha
        if self.settings.config_revision is not None:
            env["SOUWEN_CONFIG_REVISION"] = self.settings.config_revision
        return env

    def _worker_command(self) -> tuple[str, ...]:
        return (sys.executable, "-m", "souwen.worker.browser_fetch.runtime")

    def _api_command(self) -> tuple[str, ...]:
        return (
            sys.executable,
            "-m",
            "uvicorn",
            "souwen.server.app:app",
            "--host",
            self.settings.api_host,
            "--port",
            str(self.settings.api_port),
            "--workers",
            "1",
            "--log-level",
            "info",
            "--access-log",
            "--timeout-keep-alive",
            "120",
        )

    def _spawn_worker(self) -> ChildProcess:
        worker = self._process_factory(self._worker_command(), self._child_env())
        deadline = time.monotonic() + self.settings.worker_startup_timeout
        while time.monotonic() < deadline and not self._stop.is_set():
            if worker.poll() is not None:
                self._terminate_process(worker)
                raise RuntimeError("Browser Worker exited before readiness")
            remaining = max(0.05, min(1.0, deadline - time.monotonic()))
            if self._readiness_probe(self.settings, self._token, remaining):
                logger.info("Browser Worker ready on loopback port %s", self.settings.worker_port)
                return worker
            self._sleep(min(0.1, remaining))
        self._terminate_process(worker)
        raise RuntimeError("Browser Worker did not become ready within the bounded startup timeout")

    def _start_api(self) -> ChildProcess:
        api = self._process_factory(self._api_command(), self._child_env())
        logger.info("API runtime started on port %s", self.settings.api_port)
        return api

    def _handle_signal(self, signum: int, _frame: object) -> None:
        self._signal = signum
        self._stop.set()
        for process in (self._worker, self._api):
            if process is not None and process.poll() is None:
                try:
                    self._send_signal(process, signum)
                except OSError:
                    pass

    def _install_signal_handlers(self) -> None:
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, signal.SIG_IGN)

    def _terminate_process(self, process: ChildProcess | None) -> None:
        if process is None:
            return
        if process.poll() is not None:
            self._kill_remaining_group(process)
            return
        try:
            self._send_signal(process, signal.SIGTERM)
            process.wait(timeout=self.settings.termination_timeout)
        except (OSError, subprocess.TimeoutExpired):
            try:
                if self._use_process_groups and os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.wait(timeout=self.settings.termination_timeout)
            except (OSError, subprocess.TimeoutExpired):
                logger.error("child process %s did not terminate", process.pid)
        else:
            self._kill_remaining_group(process)

    def _send_signal(self, process: ChildProcess, signum: int) -> None:
        if self._use_process_groups and os.name == "posix":
            os.killpg(process.pid, signum)
        else:
            process.send_signal(signum)

    def _kill_remaining_group(self, process: ChildProcess) -> None:
        if not self._use_process_groups or os.name != "posix":
            return
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        os.killpg(process.pid, signal.SIGKILL)

    def _shutdown(self) -> None:
        self._terminate_process(self._api)
        self._terminate_process(self._worker)

    def _restart_worker(self, restart_number: int) -> ChildProcess | None:
        backoff = min(
            self.settings.worker_restart_backoff * (2 ** max(0, restart_number - 1)),
            10.0,
        )
        if backoff:
            self._stop.wait(backoff)
        if self._stop.is_set():
            return None
        try:
            return self._spawn_worker()
        except RuntimeError as exc:
            logger.error("Browser Worker restart %s failed: %s", restart_number, exc)
            return None

    def run(self) -> int:
        self._install_signal_handlers()
        try:
            if self.settings.worker_required:
                self._worker = self._spawn_worker()
            self._api = self._start_api()
            restarts = 0
            while not self._stop.is_set():
                api_code = self._api.poll()
                if api_code is not None:
                    return api_code
                if self._worker is not None and self._worker.poll() is not None:
                    crashed_worker = self._worker
                    self._worker = None
                    self._terminate_process(crashed_worker)
                    while restarts < self.settings.worker_restart_limit and not self._stop.is_set():
                        restarts += 1
                        self._worker = self._restart_worker(restarts)
                        if self._worker is not None:
                            break
                    if self._worker is None and restarts >= self.settings.worker_restart_limit:
                        logger.error(
                            "Browser Worker entered terminal crash-loop state after %s restarts; "
                            "API health remains available and readiness fails closed",
                            restarts,
                        )
                self._stop.wait(0.1)
            return 0
        finally:
            self._shutdown()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        settings = DeploymentSettings.from_env()
        return DeploymentSupervisor(settings).run()
    except (RuntimeError, ValueError) as exc:
        logger.error("deployment supervisor failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["DeploymentSettings", "DeploymentSupervisor", "main"]
