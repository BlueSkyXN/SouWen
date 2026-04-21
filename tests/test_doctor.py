"""SouWen doctor 模块测试。

覆盖 ``souwen.doctor`` 中 ``check_all()`` 与 ``format_report()`` 的诊断功能。
验证：66 个数据源的完整性检查、状态判断（ok/missing_key/limited/unavailable/warning）、
报告格式化与符号呈现、以及 Tier 分层显示。

测试清单：
- ``TestCheckAll``：check_all() 返回 66 源、必要字段完整性、Key 配置状态检测
- ``TestFormatReport``：format_report() 字符串输出、标题/Tier 分组、状态符号
"""

from souwen.doctor import check_all, format_report
from souwen.source_registry import get_all_sources


class TestCheckAll:
    """check_all() 测试"""

    def test_returns_all_sources(self, monkeypatch):
        """返回全部数据源的检查结果"""
        monkeypatch.delenv("SOUWEN_TAVILY_API_KEY", raising=False)
        from souwen.config import get_config

        get_config.cache_clear()
        results = check_all()
        assert len(results) == 72

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
        """source registry 有 66 个数据源"""
        assert len(get_all_sources()) == 72

    def test_semantic_scholar_without_key_is_limited(self, monkeypatch):
        """Semantic Scholar 无 Key 时标记为 limited。"""
        monkeypatch.delenv("SOUWEN_SEMANTIC_SCHOLAR_API_KEY", raising=False)
        from souwen.config import get_config

        get_config.cache_clear()
        try:
            results = check_all()
            source = next(r for r in results if r["name"] == "semantic_scholar")
            assert source["status"] == "limited"
            assert "易限流" in source["message"]
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
        assert "授权接口" in report

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
        ok_count = sum(1 for r in results if r["status"] == "ok")
        report = format_report(results)
        assert f"{ok_count}/{len(results)}" in report
