"""SouWen 配置模块测试。

覆盖 ``souwen.config`` 中配置系统的代理、路径、API Key、频道覆盖、代理池解析等功能。
验证 SouWenConfig 的默认值、环境变量覆盖、代理校验、频道级配置优先级等不变量。

测试清单：
- ``TestGetProxy``：单代理/代理池选择逻辑
- ``TestDataPath``：~ 展开与默认路径
- ``TestDefaults``：超时、重试、API Key 默认值
- ``TestEnvOverride``：环境变量覆盖配置
- ``TestSourceChannelConfig``：频道级配置、代理/backend/base_url 解析
- ``TestProxyValidation``：代理 URL 校验与安全性
"""

import pytest

from souwen.config import SouWenConfig, get_config, reload_config


class TestGetProxy:
    """get_proxy() 测试"""

    def test_no_proxy_returns_none(self):
        """无代理配置返回 None"""
        cfg = SouWenConfig()
        assert cfg.get_proxy() is None

    def test_single_proxy(self):
        """只设 proxy 时返回该值"""
        cfg = SouWenConfig(proxy="http://127.0.0.1:7890")
        assert cfg.get_proxy() == "http://127.0.0.1:7890"

    def test_proxy_pool_returns_from_pool(self):
        """设 proxy_pool 时从池中选取"""
        pool = ["http://p1:8080", "http://p2:8080", "http://p3:8080"]
        cfg = SouWenConfig(proxy_pool=pool)
        result = cfg.get_proxy()
        assert result in pool

    def test_proxy_pool_precedence(self):
        """proxy_pool 优先于 proxy"""
        cfg = SouWenConfig(proxy="http://single:1234", proxy_pool=["http://pool:5678"])
        assert cfg.get_proxy() == "http://pool:5678"


class TestDataPath:
    """data_path 测试"""

    def test_expands_tilde(self):
        """~ 正确展开"""
        cfg = SouWenConfig(data_dir="~/souwen_data")
        path = cfg.data_path
        assert "~" not in str(path)
        assert "souwen_data" in str(path)

    def test_default_data_dir(self):
        """默认 data_dir 路径"""
        cfg = SouWenConfig()
        assert cfg.data_dir == "~/.local/share/souwen"


class TestDefaults:
    """默认值测试"""

    def test_timeout_default(self):
        """timeout 默认 30 秒。"""
        cfg = SouWenConfig()
        assert cfg.timeout == 30

    def test_max_retries_default(self):
        """max_retries 默认 3 次。"""
        cfg = SouWenConfig()
        assert cfg.max_retries == 3

    def test_proxy_pool_default_empty(self):
        """proxy_pool 默认空列表（不启用代理池）。"""
        cfg = SouWenConfig()
        assert cfg.proxy_pool == []

    def test_plugin_config_default_empty(self):
        """plugin_config 默认空字典。"""
        cfg = SouWenConfig()
        assert cfg.plugin_config == {}

    def test_plugin_config_field(self):
        """plugin_config 保存按插件名分组的配置。"""
        cfg = SouWenConfig(plugin_config={"demo": {"api_key": "k", "limit": 3}})
        assert cfg.plugin_config["demo"] == {"api_key": "k", "limit": 3}

    def test_all_api_keys_default_none(self):
        """所有 API Key 字段默认 None"""
        cfg = SouWenConfig()
        key_fields = [f for f in SouWenConfig.model_fields if "key" in f or "token" in f]
        for field in key_fields:
            assert getattr(cfg, field) is None, f"{field} 应默认为 None"


class TestEnvOverride:
    """环境变量覆盖测试"""

    def test_env_sets_api_key(self, monkeypatch):
        """环境变量设置 API Key"""
        monkeypatch.setenv("SOUWEN_TAVILY_API_KEY", "env-key")
        cfg = reload_config()
        try:
            assert cfg.tavily_api_key == "env-key"
        finally:
            get_config.cache_clear()

    def test_env_sets_timeout(self, monkeypatch):
        """环境变量设置 timeout"""
        monkeypatch.setenv("SOUWEN_TIMEOUT", "60")
        cfg = reload_config()
        try:
            assert cfg.timeout == 60
        finally:
            get_config.cache_clear()

    def test_env_sets_proxy_pool(self, monkeypatch):
        """环境变量设置 proxy_pool（逗号分隔）"""
        monkeypatch.setenv("SOUWEN_PROXY_POOL", "http://a:1,http://b:2")
        cfg = reload_config()
        try:
            assert cfg.proxy_pool == ["http://a:1", "http://b:2"]
        finally:
            get_config.cache_clear()


class TestSourceChannelConfig:
    """SourceChannelConfig + 解析器测试"""

    def test_default_source_config(self):
        """默认频道配置"""
        from souwen.config import SourceChannelConfig

        sc = SourceChannelConfig()
        assert sc.enabled is True
        assert sc.proxy == "inherit"
        assert sc.http_backend == "auto"
        assert sc.base_url is None
        assert sc.api_key is None
        assert sc.headers == {}
        assert sc.params == {}

    def test_get_source_config_default(self):
        """未配置的源返回默认值"""
        cfg = SouWenConfig()
        sc = cfg.get_source_config("duckduckgo")
        assert sc.enabled is True
        assert sc.proxy == "inherit"

    def test_get_source_config_override(self):
        """配置了的源返回覆盖值"""
        from souwen.config import SourceChannelConfig

        cfg = SouWenConfig(
            sources={
                "duckduckgo": SourceChannelConfig(enabled=False, proxy="warp"),
            }
        )
        sc = cfg.get_source_config("duckduckgo")
        assert sc.enabled is False
        assert sc.proxy == "warp"

    def test_is_source_enabled(self):
        """is_source_enabled 检查"""
        from souwen.config import SourceChannelConfig

        cfg = SouWenConfig(
            sources={
                "google_patents": SourceChannelConfig(enabled=False),
            }
        )
        assert cfg.is_source_enabled("duckduckgo") is True
        assert cfg.is_source_enabled("google_patents") is False

    def test_resolve_proxy_inherit(self):
        """proxy=inherit 继承全局"""
        cfg = SouWenConfig(proxy="http://global:1234")
        assert cfg.resolve_proxy("duckduckgo") == "http://global:1234"

    def test_resolve_proxy_none(self):
        """proxy=none 不使用代理"""
        from souwen.config import SourceChannelConfig

        cfg = SouWenConfig(
            proxy="http://global:1234",
            sources={"duckduckgo": SourceChannelConfig(proxy="none")},
        )
        assert cfg.resolve_proxy("duckduckgo") is None

    def test_resolve_proxy_warp(self):
        """proxy=warp 返回 WARP SOCKS 地址"""
        from souwen.config import SourceChannelConfig

        cfg = SouWenConfig(
            warp_socks_port=9090,
            sources={"duckduckgo": SourceChannelConfig(proxy="warp")},
        )
        assert cfg.resolve_proxy("duckduckgo") == "socks5://localhost:9090"

    def test_resolve_proxy_explicit_url(self):
        """proxy=显式URL"""
        from souwen.config import SourceChannelConfig

        cfg = SouWenConfig(
            sources={"duckduckgo": SourceChannelConfig(proxy="socks5://custom:1080")},
        )
        assert cfg.resolve_proxy("duckduckgo") == "socks5://custom:1080"

    def test_resolve_backend_channel_override(self):
        """频道 http_backend 覆盖全局"""
        from souwen.config import SourceChannelConfig

        cfg = SouWenConfig(
            default_http_backend="httpx",
            sources={"duckduckgo": SourceChannelConfig(http_backend="curl_cffi")},
        )
        assert cfg.resolve_backend("duckduckgo") == "curl_cffi"

    def test_resolve_backend_fallback_to_legacy(self):
        """频道 auto 回退到旧版 http_backend dict"""
        cfg = SouWenConfig(
            default_http_backend="httpx",
            http_backend={"duckduckgo": "curl_cffi"},
        )
        assert cfg.resolve_backend("duckduckgo") == "curl_cffi"

    def test_resolve_api_key_channel_priority(self):
        """频道 api_key 优先于 flat key"""
        from souwen.config import SourceChannelConfig

        cfg = SouWenConfig(
            tavily_api_key="flat-key",
            sources={"tavily": SourceChannelConfig(api_key="channel-key")},
        )
        assert cfg.resolve_api_key("tavily", "tavily_api_key") == "channel-key"

    def test_resolve_api_key_fallback_to_flat(self):
        """无频道 api_key 回退到 flat key"""
        cfg = SouWenConfig(tavily_api_key="flat-key")
        assert cfg.resolve_api_key("tavily", "tavily_api_key") == "flat-key"

    def test_resolve_base_url(self):
        """base_url 覆盖"""
        from souwen.config import SourceChannelConfig

        cfg = SouWenConfig(
            sources={
                "openalex": SourceChannelConfig(base_url="https://proxy.example.com"),
            }
        )
        assert (
            cfg.resolve_base_url("openalex", "https://api.openalex.org")
            == "https://proxy.example.com"
        )
        assert (
            cfg.resolve_base_url("crossref", "https://api.crossref.org")
            == "https://api.crossref.org"
        )

    def test_resolve_headers_and_params(self):
        """headers/params 获取"""
        from souwen.config import SourceChannelConfig

        cfg = SouWenConfig(
            sources={
                "duckduckgo": SourceChannelConfig(
                    headers={"Accept-Language": "zh-CN"},
                    params={"max_results": 20},
                ),
            }
        )
        assert cfg.resolve_headers("duckduckgo") == {"Accept-Language": "zh-CN"}
        assert cfg.resolve_params("duckduckgo") == {"max_results": 20}
        assert cfg.resolve_headers("bing") == {}
        assert cfg.resolve_params("bing") == {}


# ==============================================================================
# P1-3 代理 URL 校验
# ==============================================================================
class TestProxyValidation:
    """验证 _validate_proxy_url 与 SouWenConfig 字段校验"""

    def test_accept_http(self):
        """http:// 代理 URL 应被接受并原样返回。"""
        from souwen.config import _validate_proxy_url

        assert _validate_proxy_url("http://127.0.0.1:8080") == "http://127.0.0.1:8080"

    def test_accept_socks5(self):
        """socks5:// 代理（含用户名密码）应被接受。"""
        from souwen.config import _validate_proxy_url

        assert _validate_proxy_url("socks5://user:pass@host:1080") == "socks5://user:pass@host:1080"

    def test_empty_returns_none(self):
        """None / 空串 / 纯空白都应返回 None（视为未设置代理）。"""
        from souwen.config import _validate_proxy_url

        assert _validate_proxy_url(None) is None
        assert _validate_proxy_url("") is None
        assert _validate_proxy_url("   ") is None

    def test_reject_file_scheme(self):
        """file:// 等本地协议必须被拒绝，防止 SSRF/任意文件读取。"""
        from souwen.config import _validate_proxy_url

        with pytest.raises(ValueError):
            _validate_proxy_url("file:///etc/passwd")

    def test_reject_missing_host(self):
        """缺少主机名的 URL（如 http://）必须被拒绝。"""
        from souwen.config import _validate_proxy_url

        with pytest.raises(ValueError):
            _validate_proxy_url("http://")

    def test_souwen_config_rejects_bad_proxy(self):
        """SouWenConfig 在 proxy 字段非法时通过 Pydantic 抛出校验异常。"""
        from pydantic import ValidationError

        from souwen.config import SouWenConfig

        with pytest.raises((ValueError, ValidationError)):
            SouWenConfig(proxy="ftp://bad.example.com")

    def test_souwen_config_accepts_good_proxy(self):
        """合法 http:// 代理可以正常注入到 SouWenConfig。"""
        from souwen.config import SouWenConfig

        cfg = SouWenConfig(proxy="http://proxy.local:3128")
        assert cfg.proxy == "http://proxy.local:3128"

    def test_proxy_pool_filters_invalid(self):
        """proxy_pool 中混入非法条目（如 javascript:）整体应被拒绝。"""
        from pydantic import ValidationError

        from souwen.config import SouWenConfig

        with pytest.raises((ValueError, ValidationError)):
            SouWenConfig(proxy_pool=["http://ok:8080", "javascript:alert(1)"])
