"""SouWen 会话缓存测试。

覆盖 ``souwen.core.session_cache`` 中异步会话与 OAuth Token 缓存。
验证存取、过期清理、并发初始化、幂等关闭等不变量。

测试清单：
- ``TestSessionCacheRoundtrip``：会话存取、非存在返回 None、过期返回 None、覆盖写
- ``TestOAuthTokenRoundtrip``：Token 存取、过期 Token 返回 None
- ``TestClearExpired``：清理过期、保留未过期
- ``TestClose``：关闭连接、重复关闭幂等
- ``TestConcurrentInit``：10 个并发 _get_db 只建一个连接、aclose 幂等
"""

import asyncio

import pytest

from souwen.core.session_cache import SessionCache


@pytest.fixture
def cache(tmp_path):
    """创建临时数据库的 SessionCache"""
    db_path = tmp_path / "test_cache.db"
    return SessionCache(db_path=db_path)


class TestSessionCacheRoundtrip:
    """会话存取测试"""

    async def test_save_and_get_session(self, cache):
        """保存后可取回"""
        await cache.save_session("epo_ops", {"token": "abc123"}, ttl_hours=1.0)
        result = await cache.get_session("epo_ops")
        assert result is not None
        assert result["token"] == "abc123"
        await cache.close()

    async def test_get_nonexistent_session(self, cache):
        """不存在的站点返回 None"""
        result = await cache.get_session("nonexistent")
        assert result is None
        await cache.close()

    async def test_expired_session_returns_none(self, cache):
        """过期会话返回 None"""
        # ttl_hours=0 → 立即过期（expires_at ≈ now）
        await cache.save_session("test_site", {"key": "val"}, ttl_hours=0)
        # 短暂等待确保过期
        await asyncio.sleep(0.05)
        result = await cache.get_session("test_site")
        assert result is None
        await cache.close()

    async def test_overwrite_session(self, cache):
        """同站点保存两次，第二次覆盖"""
        await cache.save_session("site_a", {"v": 1})
        await cache.save_session("site_a", {"v": 2})
        result = await cache.get_session("site_a")
        assert result["v"] == 2
        await cache.close()


class TestOAuthTokenRoundtrip:
    """OAuth Token 存取测试"""

    async def test_save_and_get_token(self, cache):
        """保存 Token 后可取回"""
        await cache.save_oauth_token(
            provider="epo_ops",
            access_token="tok_abc",
            expires_in=3600,
            token_type="Bearer",
            refresh_token="ref_xyz",
            extra={"scope": "read"},
        )
        result = await cache.get_oauth_token("epo_ops")
        assert result is not None
        assert result["access_token"] == "tok_abc"
        assert result["token_type"] == "Bearer"
        assert result["extra"]["scope"] == "read"
        await cache.close()

    async def test_get_nonexistent_token(self, cache):
        """不存在的 provider 返回 None"""
        result = await cache.get_oauth_token("no_such_provider")
        assert result is None
        await cache.close()

    async def test_expired_token_returns_none(self, cache):
        """过期 Token 返回 None（expires_in=0 → 提前 60s → 已过期）"""
        await cache.save_oauth_token(
            provider="expired_prov",
            access_token="old_tok",
            expires_in=0,
        )
        result = await cache.get_oauth_token("expired_prov")
        assert result is None
        await cache.close()


class TestClearExpired:
    """清理过期缓存"""

    async def test_clear_removes_expired(self, cache):
        """clear_expired 清理过期条目"""
        await cache.save_session("old_site", {"x": 1}, ttl_hours=0)
        await cache.save_oauth_token("old_prov", "tok", expires_in=0)
        await asyncio.sleep(0.05)
        count = await cache.clear_expired()
        assert count >= 1
        await cache.close()

    async def test_clear_keeps_valid(self, cache):
        """clear_expired 保留未过期条目"""
        await cache.save_session("fresh", {"y": 2}, ttl_hours=24)
        await cache.clear_expired()
        result = await cache.get_session("fresh")
        assert result is not None
        await cache.close()


class TestClose:
    """关闭连接"""

    async def test_close_without_error(self, cache):
        """close 不抛异常"""
        await cache.close()

    async def test_double_close(self, cache):
        """重复 close 不抛异常"""
        await cache.close()
        await cache.close()


class TestConcurrentInit:
    """并发初始化安全性"""

    async def test_concurrent_get_db_returns_single_connection(self, tmp_path, monkeypatch):
        """10 个并发 _get_db 只会建立一个 aiosqlite 连接"""
        import aiosqlite

        import souwen.core.session_cache as sc_mod

        real_connect = aiosqlite.connect
        call_count = 0

        def counting_connect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return real_connect(*args, **kwargs)

        monkeypatch.setattr(sc_mod.aiosqlite, "connect", counting_connect)

        cache = sc_mod.SessionCache(db_path=tmp_path / "concurrent.db")
        try:
            conns = await asyncio.gather(*[cache._get_db() for _ in range(10)])
            assert call_count == 1
            first = conns[0]
            assert all(c is first for c in conns)
        finally:
            await cache.aclose()

    async def test_aclose_is_idempotent(self, tmp_path):
        """aclose 可重复调用"""
        from souwen.core.session_cache import SessionCache

        cache = SessionCache(db_path=tmp_path / "aclose.db")
        await cache.save_session("s", {"k": 1})
        await cache.aclose()
        await cache.aclose()
        assert cache._db is None
