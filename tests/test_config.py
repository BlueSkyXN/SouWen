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
