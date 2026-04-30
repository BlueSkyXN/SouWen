"""配置加载器（``souwen.config.loader``）测试。

覆盖 V1 配置加载链路：YAML 文件解析、环境变量覆盖、优先级、缓存清理、
默认配置文件生成等行为。所有用例通过 ``monkeypatch.chdir`` + ``tmp_path``
隔离工作目录与 ``HOME``，避免读到仓库根目录或用户目录里真实的
``souwen.yaml`` / ``~/.config/souwen/config.yaml``。

测试清单：
- ``TestYamlLoading``：YAML 文件加载（合法 / 缺失 / 格式错误）
- ``TestEnvOverride``：环境变量覆盖与类型转换
- ``TestPrecedence``：环境变量 > YAML > 默认值
- ``TestReloadConfig``：``reload_config()`` 清理 LRU 缓存
- ``TestEnsureConfigFile``：``ensure_config_file()`` 在缺失时生成模板
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from souwen.config import SouWenConfig, get_config
from souwen.config.loader import ensure_config_file, reload_config


@pytest.fixture(autouse=True)
def _isolate_filesystem(monkeypatch, tmp_path):
    """每个用例切到独立 tmp_path 工作目录并重写 HOME，避免误读真实配置文件。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    get_config.cache_clear()
    yield
    get_config.cache_clear()


class TestYamlLoading:
    """YAML 配置文件加载行为。"""

    def test_loads_flat_yaml(self, tmp_path):
        """扁平结构 YAML 中的字段应进入 SouWenConfig。"""
        (tmp_path / "souwen.yaml").write_text(
            textwrap.dedent(
                """
                timeout: 77
                max_retries: 9
                """
            ).strip(),
            encoding="utf-8",
        )
        cfg = reload_config()
        assert cfg.timeout == 77
        assert cfg.max_retries == 9

    def test_loads_nested_yaml(self, tmp_path):
        """嵌套分组 YAML（如 ``paper:`` 下的字段）应被展平合并。"""
        (tmp_path / "souwen.yaml").write_text(
            textwrap.dedent(
                """
                paper:
                  openalex_email: user@example.com
                http:
                  timeout: 42
                """
            ).strip(),
            encoding="utf-8",
        )
        cfg = reload_config()
        assert cfg.openalex_email == "user@example.com"
        assert cfg.timeout == 42

    def test_missing_file_uses_defaults(self):
        """无任何 YAML 时，配置应回落到 SouWenConfig 默认值。"""
        cfg = reload_config()
        defaults = SouWenConfig()
        assert cfg.timeout == defaults.timeout
        assert cfg.max_retries == defaults.max_retries

    def test_malformed_yaml_falls_back_to_defaults(self, tmp_path):
        """YAML 解析失败时不抛异常，使用默认值（warning 由 loader 自行打日志）。"""
        (tmp_path / "souwen.yaml").write_text("timeout: [unterminated\n", encoding="utf-8")
        # 不应抛异常
        cfg = reload_config()
        assert cfg.timeout == SouWenConfig().timeout

    def test_unknown_yaml_keys_are_ignored(self, tmp_path):
        """YAML 中无效字段名应被静默忽略，不污染配置或抛错。"""
        (tmp_path / "souwen.yaml").write_text(
            "totally_unknown_field: 1\ntimeout: 12\n", encoding="utf-8"
        )
        cfg = reload_config()
        assert cfg.timeout == 12


class TestEnvOverride:
    """环境变量解析与类型转换。"""

    def test_env_overrides_string_field(self, monkeypatch):
        """``SOUWEN_<FIELD>`` 直接覆盖字符串字段。"""
        monkeypatch.setenv("SOUWEN_OPENALEX_EMAIL", "envuser@example.com")
        cfg = reload_config()
        assert cfg.openalex_email == "envuser@example.com"

    def test_env_int_conversion(self, monkeypatch):
        """整数字段从字符串自动转换。"""
        monkeypatch.setenv("SOUWEN_TIMEOUT", "55")
        cfg = reload_config()
        assert cfg.timeout == 55

    def test_env_bad_int_is_ignored(self, monkeypatch):
        """无效整数值应保留默认值，不抛异常（loader 自行打 warning）。"""
        monkeypatch.setenv("SOUWEN_TIMEOUT", "not-a-number")
        cfg = reload_config()
        assert cfg.timeout == SouWenConfig().timeout

    def test_env_bool_truthy(self, monkeypatch):
        """布尔字段：1/true/yes/on → True。"""
        monkeypatch.setenv("SOUWEN_WARP_ENABLED", "true")
        cfg = reload_config()
        assert cfg.warp_enabled is True

    def test_env_bool_falsy(self, monkeypatch):
        """布尔字段：0/false/no/off → False。"""
        monkeypatch.setenv("SOUWEN_WARP_ENABLED", "false")
        cfg = reload_config()
        assert cfg.warp_enabled is False

    def test_env_list_csv(self, monkeypatch):
        """proxy_pool / cors_origins 等列表字段使用逗号分隔。"""
        monkeypatch.setenv("SOUWEN_CORS_ORIGINS", "https://a.example, https://b.example")
        cfg = reload_config()
        assert cfg.cors_origins == ["https://a.example", "https://b.example"]

    def test_warp_alias_without_prefix(self, monkeypatch):
        """``WARP_ENABLED`` 不带 SOUWEN_ 前缀也应生效（Docker entrypoint 兼容）。"""
        monkeypatch.delenv("SOUWEN_WARP_ENABLED", raising=False)
        monkeypatch.setenv("WARP_ENABLED", "1")
        cfg = reload_config()
        assert cfg.warp_enabled is True


class TestPrecedence:
    """优先级：env var > YAML > 默认值。"""

    def test_env_beats_yaml(self, monkeypatch, tmp_path):
        """同一字段同时存在于 YAML 与环境变量时，环境变量胜出。"""
        (tmp_path / "souwen.yaml").write_text("timeout: 11\n", encoding="utf-8")
        monkeypatch.setenv("SOUWEN_TIMEOUT", "99")
        cfg = reload_config()
        assert cfg.timeout == 99

    def test_yaml_beats_default(self, tmp_path):
        """无环境变量时，YAML 值覆盖默认值。"""
        (tmp_path / "souwen.yaml").write_text("timeout: 13\n", encoding="utf-8")
        cfg = reload_config()
        assert cfg.timeout == 13
        assert cfg.timeout != SouWenConfig().timeout

    def test_yaml_beats_dotenv(self, monkeypatch, tmp_path):
        """.env 低于 YAML，不能悄悄覆盖 souwen.yaml。"""
        monkeypatch.delenv("SOUWEN_TIMEOUT", raising=False)
        (tmp_path / ".env").write_text("SOUWEN_TIMEOUT=99\n", encoding="utf-8")
        (tmp_path / "souwen.yaml").write_text("timeout: 13\n", encoding="utf-8")
        cfg = reload_config()
        assert cfg.timeout == 13

    def test_env_beats_dotenv_and_yaml(self, monkeypatch, tmp_path):
        """真实环境变量仍高于 YAML 和 .env。"""
        (tmp_path / ".env").write_text("SOUWEN_TIMEOUT=22\n", encoding="utf-8")
        (tmp_path / "souwen.yaml").write_text("timeout: 33\n", encoding="utf-8")
        monkeypatch.setenv("SOUWEN_TIMEOUT", "44")
        cfg = reload_config()
        assert cfg.timeout == 44

    def test_default_when_neither_set(self):
        """既无 YAML 也无环境变量时，使用 SouWenConfig 默认值。"""
        cfg = reload_config()
        assert cfg.timeout == SouWenConfig().timeout


class TestReloadConfig:
    """``reload_config()`` 的缓存清理行为。"""

    def test_reload_clears_lru_cache(self, monkeypatch):
        """先读到默认值，改环境变量后 reload 应反映新值。"""
        cfg1 = get_config()
        first_timeout = cfg1.timeout
        monkeypatch.setenv("SOUWEN_TIMEOUT", str(first_timeout + 7))
        # 不调 reload 时，由于 lru_cache，仍然是旧值
        cfg_cached = get_config()
        assert cfg_cached.timeout == first_timeout
        # reload 后应反映新值
        cfg2 = reload_config()
        assert cfg2.timeout == first_timeout + 7

    def test_get_config_returns_singleton(self):
        """连续两次 get_config 应返回同一对象（缓存命中）。"""
        a = get_config()
        b = get_config()
        assert a is b


class TestEnsureConfigFile:
    """``ensure_config_file()`` 行为。"""

    def test_creates_file_when_missing(self, tmp_path):
        """无任何配置文件时，应在 ``~/.config/souwen/config.yaml`` 生成模板。"""
        target = tmp_path / ".config" / "souwen" / "config.yaml"
        assert not target.exists()
        result = ensure_config_file()
        assert result == target
        assert target.is_file()
        assert target.read_text(encoding="utf-8").strip() != ""

    def test_returns_existing_file_without_overwrite(self, tmp_path):
        """已存在 ``./souwen.yaml`` 时直接返回，不覆盖内容。"""
        existing = tmp_path / "souwen.yaml"
        existing.write_text("timeout: 88\n", encoding="utf-8")
        result = ensure_config_file()
        assert result == Path("souwen.yaml")
        # 确认未被覆盖
        assert "timeout: 88" in existing.read_text(encoding="utf-8")
