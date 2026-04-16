"""SouWen 配置模块测试"""

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
        cfg = SouWenConfig()
        assert cfg.timeout == 30

    def test_max_retries_default(self):
        cfg = SouWenConfig()
        assert cfg.max_retries == 3

    def test_proxy_pool_default_empty(self):
        cfg = SouWenConfig()
        assert cfg.proxy_pool == []

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
