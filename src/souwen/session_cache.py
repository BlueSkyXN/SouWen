"""会话缓存管理

基于 aiosqlite 异步持久化存储 OAuth Token、Cookie、JWT 等会话信息，
避免重复鉴权，降低请求频率。
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from souwen.config import get_config

logger = logging.getLogger("souwen.session_cache")


class SessionCache:
    """会话缓存（aiosqlite 异步持久化）

    缓存 OAuth Token、Cookie、API 认证信息等，
    避免每次请求都重新鉴权。

    Args:
        db_path: SQLite 数据库路径，默认在 data_dir 下
    """

    def __init__(self, db_path: Path | None = None):
        if db_path is None:
            config = get_config()
            cache_dir = config.data_path
            cache_dir.mkdir(parents=True, exist_ok=True)
            db_path = cache_dir / "session_cache.db"

        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None
        self._init_lock: asyncio.Lock | None = None
        # 同步初始化表结构（仅在首次创建时执行）
        self._ensure_tables_sync()

    def _ensure_tables_sync(self) -> None:
        """同步初始化表结构（仅在模块加载时调用一次）"""
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site TEXT NOT NULL UNIQUE,
                    data TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS oauth_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL UNIQUE,
                    access_token TEXT NOT NULL,
                    token_type TEXT DEFAULT 'Bearer',
                    expires_at TEXT NOT NULL,
                    refresh_token TEXT,
                    extra TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()
        finally:
            conn.close()

    async def _get_db(self) -> aiosqlite.Connection:
        """获取或创建异步数据库连接（并发安全懒加载）"""
        if self._db is not None:
            return self._db
        if self._init_lock is None:
            self._init_lock = asyncio.Lock()
        async with self._init_lock:
            if self._db is None:
                self._db = await aiosqlite.connect(str(self._db_path))
        return self._db

    async def get_session(self, site: str) -> dict[str, Any] | None:
        """获取有效的会话数据

        Args:
            site: 站点标识（如 'epo_ops', 'cnipa', 'google_patents'）

        Returns:
            会话数据字典，过期或不存在返回 None
        """
        db = await self._get_db()
        now = datetime.now(timezone.utc).isoformat()
        async with db.execute(
            "SELECT data FROM sessions WHERE site = ? AND expires_at > ?",
            (site, now),
        ) as cursor:
            row = await cursor.fetchone()
        if row:
            logger.debug("会话缓存命中: %s", site)
            return json.loads(row[0])
        return None

    async def save_session(
        self,
        site: str,
        data: dict[str, Any],
        ttl_hours: float = 24.0,
    ) -> None:
        """保存会话数据

        Args:
            site: 站点标识
            data: 会话数据（Cookie、Header 等）
            ttl_hours: 有效期（小时），默认 24h
        """
        db = await self._get_db()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=ttl_hours)
        now_str = now.isoformat()
        expires_str = expires_at.isoformat()

        await db.execute(
            """INSERT OR REPLACE INTO sessions
               (site, data, expires_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (site, json.dumps(data), expires_str, now_str, now_str),
        )
        await db.commit()
        logger.debug("会话已缓存: %s (有效期 %.1fh)", site, ttl_hours)

    async def get_oauth_token(self, provider: str) -> dict[str, Any] | None:
        """获取有效的 OAuth Token

        Args:
            provider: 提供方标识（如 'epo_ops', 'cnipa'）

        Returns:
            Token 数据字典，过期或不存在返回 None
        """
        db = await self._get_db()
        now = datetime.now(timezone.utc).isoformat()
        async with db.execute(
            "SELECT access_token, token_type, extra FROM oauth_tokens "
            "WHERE provider = ? AND expires_at > ?",
            (provider, now),
        ) as cursor:
            row = await cursor.fetchone()
        if row:
            logger.debug("OAuth Token 缓存命中: %s", provider)
            return {
                "access_token": row[0],
                "token_type": row[1],
                "extra": json.loads(row[2]) if row[2] else {},
            }
        return None

    async def save_oauth_token(
        self,
        provider: str,
        access_token: str,
        expires_in: int = 1200,
        token_type: str = "Bearer",
        refresh_token: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """保存 OAuth Token

        Args:
            provider: 提供方标识
            access_token: 访问令牌
            expires_in: 有效期（秒），默认 20 分钟
            token_type: 令牌类型
            refresh_token: 刷新令牌（可选）
            extra: 额外数据
        """
        db = await self._get_db()
        now = datetime.now(timezone.utc)
        # 提前 60s 过期，避免边界问题
        expires_at = now + timedelta(seconds=max(0, expires_in - 60))
        now_str = now.isoformat()

        await db.execute(
            """INSERT OR REPLACE INTO oauth_tokens
               (provider, access_token, token_type, expires_at,
                refresh_token, extra, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                provider,
                access_token,
                token_type,
                expires_at.isoformat(),
                refresh_token,
                json.dumps(extra or {}),
                now_str,
                now_str,
            ),
        )
        await db.commit()
        logger.debug("OAuth Token 已缓存: %s (有效期 %ds)", provider, expires_in)

    async def clear_expired(self) -> int:
        """清理过期缓存，返回清理数量"""
        db = await self._get_db()
        now = datetime.now(timezone.utc).isoformat()
        cursor = await db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        count = cursor.rowcount
        cursor = await db.execute("DELETE FROM oauth_tokens WHERE expires_at <= ?", (now,))
        count += cursor.rowcount
        await db.commit()
        if count:
            logger.debug("清理过期缓存: %d 条", count)
        return count

    async def close(self) -> None:
        """关闭数据库连接"""
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def aclose(self) -> None:
        """异步关闭（幂等），供 FastAPI lifespan 调用"""
        await self.close()


# 全局单例（惰性初始化）
_global_cache: SessionCache | None = None
_global_cache_lock = threading.Lock()


def get_session_cache() -> SessionCache:
    """获取全局会话缓存实例（线程安全 double-check）"""
    global _global_cache
    if _global_cache is not None:
        return _global_cache
    with _global_cache_lock:
        if _global_cache is None:
            _global_cache = SessionCache()
    return _global_cache
