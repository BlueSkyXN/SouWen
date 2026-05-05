"""SouWen doctor 模块测试。

覆盖 ``souwen.doctor`` 中 ``check_all()`` 与 ``format_report()`` 的诊断功能。
验证：数据源完整性检查、状态判断（ok/missing_key/limited/unavailable/warning）、
报告格式化与符号呈现、以及集成类型分组显示。

测试清单：
- ``TestCheckAll``：check_all() 返回全部源、必要字段完整性、Key 配置状态检测
- ``TestFormatReport``：format_report() 字符串输出、标题/Tier 分组、状态符号
"""

import pytest

from typing import cast

from souwen.doctor import check_all, format_report, summarize_statuses
from souwen.core.exceptions import ConfigError
from souwen.registry.adapter import MethodSpec, SourceAdapter
from souwen.registry.loader import lazy
from souwen.registry.views import _reg_external
from souwen.registry.meta import get_all_sources


def register_runtime_web_doctor_probe() -> str:
    """注册一个不带内部 v0_category:* tag 的外部 web 插件。"""
    name = "doctor_web_probe"
    adapter = SourceAdapter(
        name=name,
        domain="web",
        integration="scraper",
        description="doctor web probe",
        config_field=None,
        client_loader=lazy("souwen.web.duckduckgo:DuckDuckGoClient"),
        methods={"search": MethodSpec("search")},
        needs_config=False,
    )
    assert _reg_external(adapter) is True
    return name


class TestCheckAll:
    """check_all() 测试"""

    def test_returns_all_sources(self, monkeypatch):
        """返回全部数据源的检查结果"""
        monkeypatch.delenv("SOUWEN_TAVILY_API_KEY", raising=False)
        from souwen.config import get_config

        get_config.cache_clear()
        results = check_all()
        assert len(results) >= 92  # 92 内置 + 可能有外部插件

    def test_result_has_required_keys(self):
        """每条结果包含必要字段"""
        results = check_all()
        required = {
            "name",
            "category",
            "status",
            "integration_type",
            "required_key",
            "message",
            "enabled",
        }
        for r in results:
            assert required.issubset(r.keys()), f"{r['name']} 缺少字段"

    def test_no_config_sources_are_ok(self):
        """稳定的零配置数据源默认显示 ok"""
        results = check_all()
        openalex = next(r for r in results if r["name"] == "openalex")
        crossref = next(r for r in results if r["name"] == "crossref")
        assert openalex["status"] == "ok"
        assert crossref["status"] == "ok"

    def test_categories_are_valid(self):
        """所有 category 值在 8 类中"""
        results = check_all()
        valid_cats = {
            "paper",
            "patent",
            "general",
            "professional",
            "social",
            "developer",
            "wiki",
            "video",
            "fetch",
            "cn_tech",
            "office",
        }
        for r in results:
            assert r["category"] in valid_cats

    def test_integration_type_values(self):
        """integration_type 只有 4 种合法值"""
        results = check_all()
        valid_types = {"open_api", "scraper", "official_api", "self_hosted"}
        for r in results:
            assert r["integration_type"] in valid_types

    def test_configured_key_shows_ok(self, monkeypatch):
        """已配置的 Tier 1/2 Key 显示 ok"""
        monkeypatch.setenv("SOUWEN_TAVILY_API_KEY", "test-key-123")
        from souwen.config import get_config

        get_config.cache_clear()
        try:
            results = check_all()
            tavily = next(r for r in results if r["name"] == "tavily")
            assert tavily["status"] == "ok"
            assert "已配置" in tavily["message"]
        finally:
            get_config.cache_clear()

    def test_missing_key_shows_missing(self, monkeypatch):
        """未配置的 Tier 2 Key 显示 missing_key"""
        monkeypatch.delenv("SOUWEN_TAVILY_API_KEY", raising=False)
        from souwen.config import get_config

        get_config.cache_clear()
        try:
            results = check_all()
            tavily = next(r for r in results if r["name"] == "tavily")
            assert tavily["status"] == "missing_key"
            assert "需要设置" in tavily["message"]
        finally:
            get_config.cache_clear()

    def test_source_config_matches_37(self):
        """source registry 有 92+ 个数据源（内置 + 外部插件）"""
        assert len(get_all_sources()) >= 92

    def test_semantic_scholar_without_key_is_limited(self, monkeypatch):
        """Semantic Scholar 无 Key 时标记为 limited。"""
        monkeypatch.delenv("SOUWEN_SEMANTIC_SCHOLAR_API_KEY", raising=False)
        from souwen.config import get_config

        get_config.cache_clear()
        try:
            results = check_all()
            source = next(r for r in results if r["name"] == "semantic_scholar")
            assert source["status"] == "limited"
            assert "提升限流" in source["message"]
        finally:
            get_config.cache_clear()

    def test_multifield_credentials_are_reported(self, monkeypatch):
        """多字段凭据源缺配置时应列出全部缺失字段。"""
        for key in ("SOUWEN_EPO_CONSUMER_KEY", "SOUWEN_EPO_CONSUMER_SECRET"):
            monkeypatch.delenv(key, raising=False)
        from souwen.config import get_config

        get_config.cache_clear()
        try:
            results = check_all()
            source = next(r for r in results if r["name"] == "epo_ops")
            assert source["status"] == "missing_key"
            assert source["credential_fields"] == ["epo_consumer_key", "epo_consumer_secret"]
            assert "epo_consumer_key / epo_consumer_secret" in source["message"]
        finally:
            get_config.cache_clear()

    @pytest.mark.asyncio
    async def test_multifield_channel_primary_override_matches_client_init(self, monkeypatch):
        """频道 api_key 可覆盖主字段，但第二凭据字段仍来自 flat/env 配置。"""
        for key in (
            "SOUWEN_EPO_CONSUMER_KEY",
            "SOUWEN_EPO_CONSUMER_SECRET",
            "SOUWEN_CNIPA_CLIENT_ID",
            "SOUWEN_CNIPA_CLIENT_SECRET",
            "SOUWEN_FACEBOOK_APP_ID",
            "SOUWEN_FACEBOOK_APP_SECRET",
            "SOUWEN_FEISHU_APP_ID",
            "SOUWEN_FEISHU_APP_SECRET",
        ):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv(
            "SOUWEN_SOURCES",
            (
                '{"epo_ops":{"api_key":"epo-key"},'
                '"cnipa":{"api_key":"cnipa-id"},'
                '"facebook":{"api_key":"fb-app"},'
                '"feishu_drive":{"api_key":"feishu-app"}}'
            ),
        )
        monkeypatch.setenv("SOUWEN_EPO_CONSUMER_SECRET", "epo-secret")
        monkeypatch.setenv("SOUWEN_CNIPA_CLIENT_SECRET", "cnipa-secret")
        monkeypatch.setenv("SOUWEN_FACEBOOK_APP_SECRET", "fb-secret")
        monkeypatch.setenv("SOUWEN_FEISHU_APP_SECRET", "feishu-secret")

        from souwen.config import get_config
        from souwen.patent.cnipa import CnipaClient
        from souwen.patent.epo_ops import EpoOpsClient
        from souwen.web.facebook import FacebookClient
        from souwen.web.feishu_drive import FeishuDriveClient

        get_config.cache_clear()
        clients = []
        try:
            results = check_all()
            for source_name in ("epo_ops", "cnipa", "facebook", "feishu_drive"):
                source = next(r for r in results if r["name"] == source_name)
                assert source["status"] == "ok"

            epo = EpoOpsClient()
            cnipa = CnipaClient()
            facebook = FacebookClient()
            feishu = FeishuDriveClient()
            clients.extend([epo, cnipa, facebook, feishu])

            assert epo._http.client_id == "epo-key"
            assert epo._http.client_secret == "epo-secret"
            assert cnipa._http.client_id == "cnipa-id"
            assert cnipa._http.client_secret == "cnipa-secret"
            assert facebook._access_token == "fb-app|fb-secret"
            assert feishu.app_id == "feishu-app"
            assert feishu.app_secret == "feishu-secret"
        finally:
            for client in clients:
                await client.close()
            get_config.cache_clear()

    def test_multifield_secondary_credentials_do_not_use_channel_api_key(self, monkeypatch):
        """多字段第二字段不能被同一个频道 api_key 误判为已配置。"""
        for key in (
            "SOUWEN_FACEBOOK_APP_ID",
            "SOUWEN_FACEBOOK_APP_SECRET",
            "SOUWEN_FEISHU_APP_ID",
            "SOUWEN_FEISHU_APP_SECRET",
        ):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("SOUWEN_FACEBOOK_APP_SECRET", "")
        monkeypatch.setenv("SOUWEN_FEISHU_APP_SECRET", "")
        monkeypatch.setenv(
            "SOUWEN_SOURCES",
            (
                '{"facebook":{"api_key":"fb-app"},'
                '"feishu_drive":{"api_key":"feishu-app"},'
                '"feishu_drive_secret":{"api_key":"feishu-secret"}}'
            ),
        )

        from souwen.config import get_config
        from souwen.web.facebook import FacebookClient
        from souwen.web.feishu_drive import FeishuDriveClient

        get_config.cache_clear()
        try:
            results = check_all()
            facebook = next(r for r in results if r["name"] == "facebook")
            feishu = next(r for r in results if r["name"] == "feishu_drive")

            assert facebook["status"] == "missing_key"
            assert "facebook_app_secret" in facebook["message"]
            assert feishu["status"] == "missing_key"
            assert "feishu_app_secret" in feishu["message"]
            with pytest.raises(ConfigError):
                FacebookClient()
            with pytest.raises(ConfigError):
                FeishuDriveClient()
        finally:
            get_config.cache_clear()

    def test_known_broken_patent_sources_are_not_ok(self):
        """已知不可用的免费专利源应直接暴露 unavailable。"""
        results = check_all()
        patentsview = next(r for r in results if r["name"] == "patentsview")
        pqai = next(r for r in results if r["name"] == "pqai")
        assert patentsview["status"] == "unavailable"
        assert pqai["status"] == "unavailable"

    def test_google_patents_is_warning(self):
        """Google Patents 作为实验性爬虫显示 warning。"""
        results = check_all()
        source = next(r for r in results if r["name"] == "google_patents")
        assert source["status"] == "warning"
        assert "实验性爬虫" in source["message"]

    def test_status_summary_counts_available_and_degraded(self):
        """doctor 汇总应把 limited/warning 计为可用但降级。"""
        counts = summarize_statuses(
            [
                {"status": "ok"},
                {"status": "limited"},
                {"status": "warning"},
                {"status": "degraded"},
                {"status": "missing_key"},
                {"status": "unavailable"},
            ]
        )
        assert counts["total"] == 6
        assert counts["ok"] == 1
        assert counts["available"] == 4
        assert counts["degraded"] == 3
        assert counts["degraded_total"] == 3
        status_counts = cast(dict[str, int], counts["status_counts"])
        assert status_counts["degraded"] == 1
        assert counts["failed"] == 2

    def test_runtime_web_plugin_without_internal_v0_tag_is_visible(self, clean_registry):
        """外部 web 插件应出现在 doctor 路径，不依赖内部 v0_category:* tag。"""
        name = register_runtime_web_doctor_probe()

        results = check_all()
        source = next(r for r in results if r["name"] == name)
        assert source["category"] == "general"
        assert source["distribution"] == "plugin"
        assert source["status"] in {"ok", "warning"}


class TestFormatReport:
    """format_report() 测试"""

    def test_returns_string(self):
        """返回字符串"""
        results = check_all()
        report = format_report(results)
        assert isinstance(report, str)

    def test_contains_header(self):
        """包含标题"""
        report = format_report(check_all())
        assert "SouWen Doctor" in report

    def test_contains_integration_type_sections(self):
        """包含集成类型分组"""
        report = format_report(check_all())
        assert "公开接口" in report
        assert "爬虫抓取" in report
        assert "官方接口" in report

    def test_contains_all_source_names(self):
        """报告包含所有数据源名称"""
        results = check_all()
        report = format_report(results)
        for r in results:
            assert r["name"] in report

    def test_ok_sources_have_check_icon(self):
        """ok 数据源显示 ✅"""
        report = format_report(check_all())
        assert "✅" in report

    def test_non_ok_sources_have_warning_or_error_icons(self):
        """非 ok 数据源显示醒目标识。"""
        report = format_report(check_all())
        assert "⚠️" in report or "❌" in report

    def test_counts_in_header(self):
        """标题行显示 可用数/总数"""
        results = check_all()
        ok_count = summarize_statuses(results)["available"]
        report = format_report(results)
        assert f"{ok_count}/{len(results)}" in report
