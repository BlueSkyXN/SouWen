"""SouWen doctor 模块测试。

覆盖 ``souwen.doctor`` 中 ``check_all()`` 与 ``format_report()`` 的诊断功能。
验证：数据源完整性检查、状态判断（ok/missing_key/limited/unavailable/warning）、
报告格式化与符号呈现、以及集成类型分组显示。

测试清单：
- ``TestCheckAll``：check_all() 返回全部源、必要字段完整性、Key 配置状态检测
- ``TestFormatReport``：format_report() 字符串输出、标题/Tier 分组、状态符号
"""

import importlib

import pytest

from typing import cast

from souwen.doctor import (
    check_all,
    check_all_live,
    check_edition,
    format_edition_report,
    format_report,
    summarize_live_probes,
    summarize_statuses,
)
from souwen.core.exceptions import ConfigError
from souwen.feature_matrix import RuntimeProbe
from souwen.registry.adapter import MethodSpec, SourceAdapter
from souwen.registry.catalog import source_catalog
from souwen.registry.loader import lazy
from souwen.registry.views import _reg_external


def register_runtime_web_doctor_probe() -> str:
    """注册一个不声明 category 的外部 web 插件。"""
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
            "min_edition",
            "edition",
            "edition_available",
            "edition_reason",
            "runtime_available",
            "runtime_reason",
            "credentials_satisfied",
            "config_available",
            "config_reason",
            "available",
        }
        for r in results:
            assert required.issubset(r.keys()), f"{r['name']} 缺少字段"

    def test_no_config_sources_report_optional_quota_limits(self):
        """零配置源保持可用；缺少可选配额 Key 时明确显示 limited。"""
        results = check_all()
        openalex = next(r for r in results if r["name"] == "openalex")
        crossref = next(r for r in results if r["name"] == "crossref")
        assert openalex["status"] == "limited"
        assert "openalex_api_key" in openalex["message"]
        assert openalex["available"] is True
        assert crossref["status"] == "ok"

    def test_openalex_api_key_clears_optional_quota_warning(self, monkeypatch):
        """配置 OpenAlex Key 后 doctor 应回到 ok，且不泄漏 Key。"""
        monkeypatch.setenv("SOUWEN_OPENALEX_API_KEY", "openalex-doctor-secret")
        from souwen.config import get_config

        get_config.cache_clear()
        openalex = next(r for r in check_all() if r["name"] == "openalex")

        assert openalex["status"] == "ok"
        assert openalex["available"] is True
        assert "openalex_api_key 已配置" in openalex["message"]
        assert "openalex-doctor-secret" not in str(openalex)

    def test_categories_are_valid(self):
        """所有 category 值在正式 catalog 分类中"""
        results = check_all()
        valid_cats = {
            "book",
            "paper",
            "patent",
            "web_general",
            "web_professional",
            "social",
            "office",
            "developer",
            "knowledge",
            "video",
            "archive",
            "fetch",
            "cn_tech",
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

    def test_basic_edition_marks_pro_sources_upgrade_required(self, monkeypatch):
        """basic edition 下 pro 源应报告需升级，不 probe loader，也不计为可用。"""
        import souwen.doctor as doctor_module

        probed: list[str] = []
        original_probe = doctor_module.probe_adapter_runtime

        def recording_probe(adapter):
            probed.append(adapter.name)
            return original_probe(adapter)

        monkeypatch.setenv("SOUWEN_EDITION", "basic")
        monkeypatch.setattr(doctor_module, "probe_adapter_runtime", recording_probe)
        from souwen.config import get_config

        get_config.cache_clear()
        try:
            results = check_all()
            openalex = next(r for r in results if r["name"] == "openalex")
            crossref = next(r for r in results if r["name"] == "crossref")

            assert openalex["status"] == "unavailable"
            assert openalex["min_edition"] == "pro"
            assert openalex["edition"] == "basic"
            assert openalex["edition_available"] is False
            assert "source 'openalex' requires edition=pro" in openalex["edition_reason"]
            assert openalex["runtime_available"] is False
            assert openalex["runtime_reason"] == (
                "runtime not probed because " + openalex["edition_reason"]
            )
            assert openalex["message"] == openalex["edition_reason"]
            assert openalex["available"] is False
            assert "openalex" not in probed

            assert crossref["min_edition"] == "basic"
            assert crossref["edition_available"] is True
            assert crossref["edition_reason"] == ""
            assert crossref["available"] is True
            assert "crossref" in probed
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

    def test_runtime_failure_is_distinct_from_edition_and_configuration(self, monkeypatch):
        """doctor 应分别报告 edition、runtime 与配置状态。"""

        import souwen.doctor as doctor_module
        from souwen.config import get_config
        from souwen.feature_matrix import RuntimeProbe

        original_probe = doctor_module.probe_adapter_runtime

        def fake_probe(adapter):
            if adapter.name == "mcp":
                return RuntimeProbe(False, "mcp: missing modules: mcp")
            return original_probe(adapter)

        monkeypatch.setenv("SOUWEN_EDITION", "basic")
        monkeypatch.delenv("SOUWEN_MCP_SERVER_URL", raising=False)
        monkeypatch.setattr(doctor_module, "probe_adapter_runtime", fake_probe)
        get_config.cache_clear()
        try:
            mcp = next(item for item in check_all() if item["name"] == "mcp")
            assert mcp["edition_available"] is True
            assert mcp["runtime_available"] is False
            assert mcp["runtime_reason"] == "mcp: missing modules: mcp"
            assert mcp["credentials_satisfied"] is False
            assert mcp["config_available"] is False
            assert mcp["available"] is False
            assert mcp["status"] == "unavailable"
            assert mcp["message"] == mcp["runtime_reason"]
        finally:
            get_config.cache_clear()

    def test_source_config_matches_37(self):
        """source registry 有 92+ 个数据源（内置 + 外部插件）"""
        assert len(source_catalog()) >= 94

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

    def test_credentialed_patent_sources_require_keys(self):
        """PatentsView/PQAI 是凭据源，未配置时应提示 missing_key。"""
        results = check_all()
        patentsview = next(r for r in results if r["name"] == "patentsview")
        pqai = next(r for r in results if r["name"] == "pqai")
        assert patentsview["status"] == "missing_key"
        assert "patentsview_api_key" in patentsview["message"]
        assert pqai["status"] == "missing_key"
        assert "pqai_api_token" in pqai["message"]

    def test_google_patents_is_warning(self, monkeypatch):
        """Google Patents 作为实验性爬虫显示 warning。"""
        monkeypatch.setattr(
            "souwen.doctor.probe_adapter_runtime",
            lambda _adapter: RuntimeProbe(True, ""),
        )
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

    def test_runtime_web_plugin_without_explicit_category_is_visible(self, clean_registry):
        """外部 web 插件应出现在 doctor 路径。"""
        name = register_runtime_web_doctor_probe()

        results = check_all()
        source = next(r for r in results if r["name"] == name)
        assert source["category"] == "web_general"
        assert source["distribution"] == "plugin"
        assert source["min_edition"] == "full"
        assert source["edition_available"] is False
        assert source["status"] == "unavailable"
        assert "source 'doctor_web_probe' requires edition=full" in source["edition_reason"]

    def test_llm_search_channel_hides_private_base_url(
        self,
        clean_registry,
        monkeypatch,
    ):
        from souwen.config import LLMSearchGatewayConfig, SouWenConfig, SourceChannelConfig
        from souwen.web.llm_search import ConcreteSearchSourceSpec, SearchSchemeSpec
        from souwen.web.llm_search.registry import SearchSchemeRegistry

        scheme = SearchSchemeSpec(
            scheme_id="doctor_probe_v1",
            gateway_id="uniapi",
            upstream_channel="fixture",
            protocol="responses",
            endpoint_kind="responses",
            tool_schema="fixture",
            candidate_contract="structured_result_list",
            default_timeout_seconds=45,
            source_grade=True,
            request_builder=lambda **kwargs: kwargs,
            response_parser=lambda payload, **_kwargs: payload,
        )
        source = ConcreteSearchSourceSpec(
            source_id="llm_search_doctor_probe",
            scheme_id=scheme.scheme_id,
            model_id="fixture-model",
        )
        registry = SearchSchemeRegistry()
        registry.register_scheme(scheme)
        registry.register_source(source)
        adapter = registry.project_source_adapter(
            source.source_id,
            description="doctor LLM-search probe",
            client_loader=lambda: object,
        )
        assert _reg_external(adapter) is True

        private_url = "https://private.internal.example/v1"
        config = SouWenConfig(
            edition="full",
            llm_search_gateways={
                "uniapi": LLMSearchGatewayConfig(
                    api_key="shared-secret",
                    base_url="https://shared.example.com/v1",
                )
            },
            sources={
                source.source_id: SourceChannelConfig(
                    enabled=True,
                    base_url=private_url,
                    timeout=45,
                )
            },
        )
        monkeypatch.setattr("souwen.doctor.get_config", lambda: config)
        monkeypatch.setattr(
            "souwen.doctor.probe_adapter_runtime",
            lambda _adapter: RuntimeProbe(True, ""),
        )

        result = next(item for item in check_all() if item["name"] == source.source_id)

        assert result["channel"] == {"timeout": "45.0"}
        assert private_url not in str(result)

    @pytest.mark.asyncio
    async def test_check_all_live_attaches_success_probe(self, monkeypatch):
        """live doctor 应只在显式入口执行真实探测并附加 live_probe。"""

        async def fake_run_via_adapter(adapter, capability, **kwargs):
            assert adapter.name == "openalex"
            assert capability == "search"
            assert kwargs["query"] == "probe"
            assert kwargs["limit"] == 1

            class Response:
                results = [object()]

            return Response()

        search_mod = importlib.import_module("souwen.search")
        monkeypatch.setattr(search_mod, "_run_via_adapter", fake_run_via_adapter)

        results = await check_all_live(sources=["openalex"], query="probe", timeout=1.0)
        openalex = next(r for r in results if r["name"] == "openalex")
        crossref = next(r for r in results if r["name"] == "crossref")

        assert openalex["live_probe"]["status"] == "ok"
        assert "1 result" in openalex["live_probe"]["message"]
        assert "live_probe" not in crossref
        assert summarize_live_probes(results)["ok"] == 1

    @pytest.mark.asyncio
    async def test_check_all_live_reports_failures_without_raising(self, monkeypatch):
        """live 探测异常应写入 failed probe，不应拖垮 doctor。"""

        async def fake_run_via_adapter(adapter, capability, **kwargs):
            del adapter, capability, kwargs
            raise RuntimeError("network down")

        search_mod = importlib.import_module("souwen.search")
        monkeypatch.setattr(search_mod, "_run_via_adapter", fake_run_via_adapter)

        results = await check_all_live(sources=["openalex"], query="probe", timeout=1.0)
        openalex = next(r for r in results if r["name"] == "openalex")

        assert openalex["live_probe"]["status"] == "failed"
        assert "network down" in openalex["live_probe"]["message"]
        assert summarize_live_probes(results)["failed"] == 1

    @pytest.mark.asyncio
    async def test_check_all_live_skips_static_unavailable_source(self, monkeypatch):
        """静态已不可用的源不应触发联网调用。"""

        async def fake_run_via_adapter(adapter, capability, **kwargs):
            del adapter, capability, kwargs
            raise AssertionError("static unavailable source should not be probed")

        search_mod = importlib.import_module("souwen.search")
        monkeypatch.setattr(search_mod, "_run_via_adapter", fake_run_via_adapter)

        results = await check_all_live(sources=["patentsview"], query="probe", timeout=1.0)
        patentsview = next(r for r in results if r["name"] == "patentsview")

        assert patentsview["live_probe"]["status"] == "skipped"
        assert "static status" in patentsview["live_probe"]["message"]


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
        assert "edition=pro" in report

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

    def test_basic_report_mentions_upgrade_required(self, monkeypatch):
        """basic edition report 应显式显示当前 edition 与需升级原因。"""
        monkeypatch.setenv("SOUWEN_EDITION", "basic")
        from souwen.config import get_config

        get_config.cache_clear()
        try:
            report = format_report(check_all())
            assert "edition=basic" in report
            assert "source 'openalex' requires edition=pro" in report
        finally:
            get_config.cache_clear()


class TestEditionReport:
    """edition 自检报告测试"""

    def test_check_edition_marks_basic_upgrade_paths(self, monkeypatch):
        """basic edition 自检应汇总 source/provider/WARP/LLM 的升级项。"""
        monkeypatch.setenv("SOUWEN_EDITION", "basic")
        from souwen.config import get_config

        get_config.cache_clear()
        try:
            report = check_edition()
            assert report["edition"] == "basic"
            assert "source_sha" in report

            source_upgrade_names = {item["name"] for item in report["sources"]["upgrade_required"]}
            assert "openalex" in source_upgrade_names
            assert report["sources"]["by_min_edition"]["pro"]["edition_available"] == 0

            provider_upgrade_names = {
                item["name"] for item in report["fetch_providers"]["upgrade_required"]
            }
            assert "jina_reader" in provider_upgrade_names
            assert report["fetch_providers"]["by_min_edition"]["basic"]["edition_available"] > 0
            mcp = next(item for item in report["fetch_providers"]["items"] if item["name"] == "mcp")
            assert mcp["edition_available"] is True
            assert isinstance(mcp["runtime_available"], bool)
            assert isinstance(mcp["runtime_reason"], str)
            assert mcp["config_available"] is False
            assert mcp["available"] is False

            assert report["warp"]["available_modes"] == ["auto", "wireproxy", "external"]
            assert {item["name"] for item in report["warp"]["upgrade_required"]} == {
                "kernel",
                "usque",
                "warp-cli",
            }
            assert report["llm"]["edition_available"] is False
            assert isinstance(report["llm"]["runtime_available"], bool)
            assert isinstance(report["llm"]["runtime_reason"], str)
            assert "LLM requires edition=pro" in report["llm"]["edition_reason"]
            assert report["probe"]["sources"]["declared"]
            assert set(report["probe"]["mcp"]) == {"declared", "available", "reason"}
            package_extras = report["probe"]["package_extras"]
            assert set(package_extras) == {"declared", "available", "reason"}
            assert package_extras["declared"]["mcp"] == ("mcp",)
            assert package_extras["declared"]["scraper"] == ("curl_cffi",)
            assert package_extras["declared"]["web"] == ("trafilatura",)
            assert isinstance(package_extras["available"], tuple)
            assert isinstance(package_extras["reason"], str)
        finally:
            get_config.cache_clear()

    def test_format_edition_report_mentions_key_sections(self, monkeypatch):
        """edition 自检文本应包含当前档位、需升级项和跨域能力。"""
        monkeypatch.setenv("SOUWEN_EDITION", "basic")
        from souwen.config import get_config

        get_config.cache_clear()
        try:
            report = format_edition_report(check_edition())
            assert "Edition 自检 (edition=basic)" in report
            assert "── Sources ──" in report
            assert "需升级 source" in report
            assert "openalex" in report
            assert "── Fetch Providers ──" in report
            assert "jina_reader" in report
            assert "WARP 可用模式: auto, wireproxy, external" in report
            assert "LLM requires edition=pro" in report
            assert "Package extras:" in report
        finally:
            get_config.cache_clear()

    def test_format_edition_report_mentions_package_extra_probe_reason(self, monkeypatch):
        """edition 自检文本应暴露 package extra importability probe 的缺失原因。"""
        monkeypatch.setenv("SOUWEN_EDITION", "full")
        from souwen.config import get_config

        get_config.cache_clear()
        try:
            data = check_edition()
            data["probe"]["package_extras"] = {
                "declared": {
                    "scraper": ("curl_cffi",),
                    "custom_extra": (),
                },
                "available": ("scraper",),
                "reason": "custom_extra: no optional module probe is declared",
            }

            report = format_edition_report(data)

            assert "Package extras: 1/2 可导入" in report
            assert "已声明: custom_extra, scraper" in report
            assert (
                "Package extra 缺失: custom_extra: no optional module probe is declared" in report
            )
        finally:
            get_config.cache_clear()
