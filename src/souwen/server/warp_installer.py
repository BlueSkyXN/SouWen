"""SouWen WARP 组件动态安装器

在运行时从 GitHub Releases 下载 WARP 相关二进制工具。
安装目录: /app/data/bin/ (可配置)
状态文件: /app/data/warp-components.json
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import re
import shutil
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("souwen.warp.installer")

COMPONENTS = {
    "usque": {
        "repo": "Diniboy1123/usque",
        "asset_pattern": "usque_{version}_linux_{arch}.zip",
        "extract_type": "zip",
        "binary_name": "usque",
        "default_version": "3.0.0",
    },
    "wireproxy": {
        "repo": "pufferffish/wireproxy",
        "asset_pattern": "wireproxy_linux_{arch}.tar.gz",
        "extract_type": "tar.gz",
        "binary_name": "wireproxy",
        "default_version": "1.1.2",
    },
    "wgcf": {
        "repo": "ViRb3/wgcf",
        "asset_pattern": "wgcf_{version}_linux_{arch}",
        "extract_type": "binary",
        "binary_name": "wgcf",
        "default_version": "2.2.30",
    },
}

ARCH_MAP = {
    "x86_64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
    "amd64": "amd64",
}

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_MIN_FREE_BYTES = 50 * 1024 * 1024
_DOWNLOAD_TIMEOUT = httpx.Timeout(60.0, connect=20.0)


class WarpInstaller:
    """WARP 组件安装管理器"""

    def __init__(
        self,
        bin_dir: str = "/app/data/bin",
        state_file: str = "/app/data/warp-components.json",
    ) -> None:
        self.bin_dir = Path(bin_dir).expanduser().resolve()
        self.state_file = Path(state_file).expanduser().resolve()

    def get_components_status(self) -> list[dict[str, Any]]:
        """获取所有组件状态列表

        Returns: [{
            "name": "usque",
            "installed": True,
            "version": "3.0.0",
            "path": "/app/data/bin/usque",
            "system_path": "/usr/local/bin/usque",
            "source": "runtime" | "system" | "not_installed",
        }, ...]
        """
        state = self._load_state()
        result: list[dict[str, Any]] = []

        for name, spec in COMPONENTS.items():
            binary_name = str(spec["binary_name"])
            runtime_path = self._component_path(name)
            runtime_installed = self._is_executable_file(runtime_path)
            system_path = shutil.which(binary_name)
            state_entry = state.get(name, {})

            if runtime_installed:
                source = "runtime"
                installed = True
                path = str(runtime_path)
                version = state_entry.get("version")
            elif system_path:
                source = "system"
                installed = True
                path = system_path
                version = None
            else:
                source = "not_installed"
                installed = False
                path = None
                version = None

            result.append(
                {
                    "name": name,
                    "installed": installed,
                    "version": version,
                    "path": path,
                    "system_path": system_path,
                    "source": source,
                }
            )

        return result

    async def install(self, component: str, version: str | None = None) -> dict[str, Any]:
        """安装或升级组件

        Args:
            component: 组件名 (usque, wireproxy, wgcf)
            version: 版本号（None 使用默认版本）

        Returns: {"ok": True, "component": str, "version": str, "path": str}
        Raises: ValueError (未知组件), RuntimeError (下载/校验失败)
        """
        spec = self._get_component_spec(component)
        target_version = version or str(spec["default_version"])
        self._validate_version(target_version)

        try:
            self.bin_dir.mkdir(parents=True, exist_ok=True)
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RuntimeError(f"WARP 组件目录不可写: {exc}") from exc

        self._ensure_space()
        arch = self._detect_arch()
        asset = str(spec["asset_pattern"]).format(version=target_version, arch=arch)
        url = self._release_url(str(spec["repo"]), target_version, asset)
        binary_name = str(spec["binary_name"])
        target_path = self._component_path(component)
        download_path = self._safe_bin_child(f".{binary_name}.download")
        new_binary_path = self._safe_bin_child(f".{binary_name}.new")

        logger.info("开始安装 WARP 组件: component=%s version=%s", component, target_version)
        try:
            self._cleanup_paths(download_path, new_binary_path)
            await self._download(url, download_path)
            self._validate_download(download_path)
            self._materialize_binary(
                download_path, new_binary_path, binary_name, str(spec["extract_type"])
            )
            self._validate_binary(new_binary_path)
            sha256 = self._sha256_file(new_binary_path)
            os.replace(new_binary_path, target_path)
            target_path.chmod(0o755)
            self._write_component_state(component, target_version, target_path, sha256)
        except (httpx.HTTPError, OSError, zipfile.BadZipFile, tarfile.TarError) as exc:
            self._cleanup_paths(download_path, new_binary_path)
            raise RuntimeError(f"WARP 组件 {component} 安装失败: {exc}") from exc
        except RuntimeError:
            self._cleanup_paths(download_path, new_binary_path)
            raise
        finally:
            self._cleanup_paths(download_path, new_binary_path)

        logger.info("WARP 组件安装完成: component=%s path=%s", component, target_path)
        return {
            "ok": True,
            "component": component,
            "version": target_version,
            "path": str(target_path),
        }

    async def uninstall(self, component: str) -> dict[str, Any]:
        """卸载运行时安装的组件（不影响系统预装）

        Returns: {"ok": True, "component": str}
        """
        self._get_component_spec(component)
        target_path = self._component_path(component)

        try:
            if target_path.exists():
                target_path.unlink()
            state = self._load_state()
            state.pop(component, None)
            self._save_state(state)
        except OSError as exc:
            raise RuntimeError(f"WARP 组件 {component} 卸载失败: {exc}") from exc

        logger.info("WARP 组件已卸载: component=%s", component)
        return {"ok": True, "component": component}

    def get_binary_path(self, component: str) -> str | None:
        """获取组件二进制路径 — 优先返回运行时安装，fallback 到系统 PATH

        WarpManager 在能力检测中应调用此方法。
        """
        spec = self._get_component_spec(component)
        runtime_path = self._component_path(component)
        if self._is_executable_file(runtime_path):
            return str(runtime_path)
        return shutil.which(str(spec["binary_name"]))

    def _get_component_spec(self, component: str) -> dict[str, Any]:
        if component not in COMPONENTS:
            raise ValueError(f"未知 WARP 组件: {component}")
        return COMPONENTS[component]

    def _component_path(self, component: str) -> Path:
        spec = self._get_component_spec(component)
        return self._safe_bin_child(str(spec["binary_name"]))

    def _safe_bin_child(self, filename: str) -> Path:
        path = (self.bin_dir / filename).resolve()
        if path.parent != self.bin_dir:
            raise RuntimeError(f"安装路径非法: {path}")
        return path

    def _load_state(self) -> dict[str, Any]:
        if not self.state_file.is_file():
            return {}
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("读取 WARP 组件状态失败，将忽略状态文件: %s", exc)
            return {}
        return data if isinstance(data, dict) else {}

    def _save_state(self, state: dict[str, Any]) -> None:
        if self.state_file.parent and not self.state_file.parent.exists():
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.state_file.with_name(f".{self.state_file.name}.tmp")
        tmp_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp_path, self.state_file)

    def _write_component_state(
        self,
        component: str,
        version: str,
        target_path: Path,
        sha256: str,
    ) -> None:
        state = self._load_state()
        state[component] = {
            "version": version,
            "path": str(target_path),
            "installed_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "sha256": sha256,
        }
        self._save_state(state)

    async def _download(self, url: str, path: Path) -> None:
        try:
            async with httpx.AsyncClient(
                timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True
            ) as client:
                async with client.stream("GET", url) as response:
                    if response.status_code >= 400:
                        raise RuntimeError(f"下载失败 HTTP {response.status_code}: {url}")
                    with path.open("wb") as file:
                        async for chunk in response.aiter_bytes():
                            if chunk:
                                file.write(chunk)
        except httpx.RequestError as exc:
            raise RuntimeError(f"网络错误，无法下载 WARP 组件: {exc}") from exc

    def _materialize_binary(
        self,
        download_path: Path,
        binary_path: Path,
        binary_name: str,
        extract_type: str,
    ) -> None:
        if extract_type == "binary":
            shutil.copyfile(download_path, binary_path)
        elif extract_type == "zip":
            self._extract_zip_binary(download_path, binary_path, binary_name)
        elif extract_type == "tar.gz":
            self._extract_tar_binary(download_path, binary_path, binary_name)
        else:
            raise RuntimeError(f"不支持的解压类型: {extract_type}")
        binary_path.chmod(0o755)

    def _extract_zip_binary(self, archive_path: Path, binary_path: Path, binary_name: str) -> None:
        with zipfile.ZipFile(archive_path) as archive:
            member = next(
                (
                    info
                    for info in archive.infolist()
                    if not info.is_dir() and Path(info.filename).name == binary_name
                ),
                None,
            )
            if member is None:
                raise RuntimeError(f"压缩包内未找到二进制文件: {binary_name}")
            with archive.open(member) as source, binary_path.open("wb") as target:
                shutil.copyfileobj(source, target)

    def _extract_tar_binary(self, archive_path: Path, binary_path: Path, binary_name: str) -> None:
        with tarfile.open(archive_path, "r:gz") as archive:
            member = next(
                (
                    info
                    for info in archive.getmembers()
                    if info.isfile() and Path(info.name).name == binary_name
                ),
                None,
            )
            if member is None:
                raise RuntimeError(f"压缩包内未找到二进制文件: {binary_name}")
            source = archive.extractfile(member)
            if source is None:
                raise RuntimeError(f"无法读取压缩包内二进制文件: {binary_name}")
            with source, binary_path.open("wb") as target:
                shutil.copyfileobj(source, target)

    def _validate_download(self, path: Path) -> None:
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError("下载文件为空")
        head = path.read_bytes()[:512].lstrip().lower()
        if head.startswith((b"<!doctype html", b"<html")):
            raise RuntimeError("下载结果看起来是 HTML 错误页，而不是组件文件")

    def _validate_binary(self, path: Path) -> None:
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError("二进制文件为空")
        path.chmod(0o755)
        if not os.access(path, os.X_OK):
            raise RuntimeError("二进制文件不可执行")
        head = path.read_bytes()[:512].lstrip().lower()
        if head.startswith((b"<!doctype html", b"<html")):
            raise RuntimeError("二进制文件校验失败，内容疑似 HTML 错误页")

    def _ensure_space(self) -> None:
        probe = (
            self.bin_dir if self.bin_dir.exists() else self._nearest_existing_parent(self.bin_dir)
        )
        usage = shutil.disk_usage(probe)
        if usage.free < _MIN_FREE_BYTES:
            raise RuntimeError("磁盘剩余空间不足，无法安装 WARP 组件")

    def _nearest_existing_parent(self, path: Path) -> Path:
        current = path
        while not current.exists() and current.parent != current:
            current = current.parent
        return current

    def _detect_arch(self) -> str:
        machine = platform.machine().lower()
        arch = ARCH_MAP.get(machine)
        if arch is None:
            raise RuntimeError(f"不支持的 CPU 架构: {machine}")
        return arch

    def _release_url(self, repo: str, version: str, asset: str) -> str:
        url = f"https://github.com/{repo}/releases/download/v{version}/{asset}"
        proxy = os.getenv("GH_PROXY", "").strip()
        if proxy:
            return f"{proxy.rstrip('/')}/{url}"
        return url

    def _validate_version(self, version: str) -> None:
        if not _VERSION_RE.match(version):
            raise ValueError(f"非法版本号: {version}")

    def _sha256_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _cleanup_paths(self, *paths: Path) -> None:
        for path in paths:
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                logger.warning("清理 WARP 组件临时文件失败: %s", path)

    def _is_executable_file(self, path: Path) -> bool:
        return path.is_file() and os.access(path, os.X_OK)
