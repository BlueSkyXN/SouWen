"""会话缓存管理

文件用途：
    基于 aiosqlite 异步持久化存储 OAuth Token、Cookie、JWT 等会话信息，
    避免重复鉴权，降低请求频率。支持全局单例模式。

类清单：
    SessionCache（主类）
        - 功能：异步会话缓存管理
        - 入参：db_path (Path|None) SQLite 数据库路径，默认在 data_dir 下
        - 关键属性：_db_path, _db (aiosqlite.Connection|None), _init_lock
        - 方法：
          * __init__(db_path) — 初始化，同步建表
          * _get_db() → Coroutine[aiosqlite.Connection] — 获取或创建异步连接
          * get_session(site) → Coroutine[dict|None] — 获取有效会话
          * save_session(site, data, ttl_hours) → Coroutine — 保存会话
          * get_oauth_token(provider) → Coroutine[dict|None] — 获取有效 OAuth Token
          * save_oauth_token(provider, access_token, expires_in, token_type, ...) → Coroutine
          * clear_expired() → Coroutine[int] — 清理过期缓存，返回清理数量
          * close() / aclose() → Coroutine — 关闭数据库连接（幂等）

数据库表：
    sessions 表
        - id (INTEGER PRIMARY KEY)
        - site (TEXT UNIQUE) — 站点标识（如 'epo_ops', 'cnipa'）
        - data (TEXT) — JSON 序列化的会话数据
        - expires_at (TEXT) — ISO 8601 过期时间戳
        - created_at (TEXT) — 创建时间
        - updated_at (TEXT) — 最后更新时间
    
    oauth_tokens 表
        - id (INTEGER PRIMARY KEY)
        - provider (TEXT UNIQUE) — OAuth 提供方（如 'epo_ops'）
        - access_token (TEXT) — 访问令牌
        - token_type (TEXT) — 令牌类型（默认 'Bearer'）
        - expires_at (TEXT) — 过期时间
        - refresh_token (TEXT) — 刷新令牌（可选）
        - extra (TEXT) — 额外数据（JSON）
        - created_at (TEXT) — 创建时间
        - updated_at (TEXT) — 更新时间

单例函数：
    get_session_cache() -> SessionCache
        - 功能：获取全局会话缓存实例（线程安全 double-check）

模块依赖：
    - aiosqlite: 异步 SQLite 驱动
    - souwen.config: 获取数据目录配置
    - datetime: 时间戳管理
    - json: 数据序列化
    - threading: 线程安全锁
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

    缓存 OAuth Token、Cookie、API 认证信息等，避免每次请求都重新鉴权。
    支持异步操作和并发安全。
    
    属性：
        _db_path: 数据库文件路径
        _db: 异步数据库连接（懒加载）
        _init_lock: 初始化锁（单例保证）
    
    Args:
        db_path: SQLite 数据库路径；None 则在 config.data_path 下创建 session_cache.db
    """

    def __init__(self, db_path: Path | None = None):
        """初始化会话缓存
        
        Args:
            db_path: 数据库文件路径
        
        说明：
            - 同步创建表结构（通过 sqlite3），仅在首次加载时执行
            - 异步连接采用 double-check lazy loading 避免重复初始化
        """
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
        """同步初始化表结构（仅在模块加载时调用一次）
        
        使用同步 sqlite3 以保证表结构在异步操作前就已准备。
        CREATE TABLE IF NOT EXISTS 保证幂等性。
        """
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
        """获取或创建异步数据库连接（并发安全懒加载）
        
        采用 double-check locking 模式：
        1. 快速路径：_db 已存在则直接返回
        2. 初始化：获取 _init_lock，再检查一次 _db，创建连接
        
        Returns:
            aiosqlite.Connection 实例
        """
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
            会话数据字典（JSON 反序列化），过期或不存在返回 None
        
        说明：
            - 仅返回 expires_at > 当前时间的记录
            - 支持并发查询
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
        
        说明：
            - 使用 INSERT OR REPLACE 避免唯一键冲突
            - 有效期计算为 now + ttl_hours
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
            Token 数据字典（包含 access_token、token_type、extra），
            过期或不存在返回 None
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
            provider: 提供方标识（如 'epo_ops', 'cnipa'）
            access_token: 访问令牌
            expires_in: 有效期（秒），默认 20 分钟（1200s）
            token_type: 令牌类型，默认 'Bearer'
            refresh_token: 刷新令牌（可选）
            extra: 额外数据字典（如 scope 等元数据）
        
        说明：
            - 有效期会提前 60s 过期，避免边界问题（token 在请求途中过期）
            - 使用 INSERT OR REPLACE 处理重复 provider
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
        """清理过期缓存，返回清理数量
        
        Returns:
            删除的记录总数（sessions + oauth_tokens）
        
        说明：
            - 删除所有 expires_at <= 当前时间的记录
            - 通过 cursor.rowcount 获取影响行数
        """
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
    """获取全局会话缓存实例（线程安全 double-check）
    
    Returns:
        全局唯一的 SessionCache 实例
    
    说明：
        - 采用 double-check locking 实现线程安全单例
        - 首次调用时创建实例，后续调用直接返回缓存
    """
    global _global_cache
    if _global_cache is not None:
        return _global_cache
    with _global_cache_lock:
        if _global_cache is None:
            _global_cache = SessionCache()
    return _global_cache
