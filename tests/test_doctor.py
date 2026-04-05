"""SouWen doctor 模块测试"""

from souwen.doctor import check_all, format_report, _SOURCE_CONFIG


class TestCheckAll:
    """check_all() 测试"""

    def test_returns_all_sources(self, monkeypatch):
        """返回全部 37 个数据源的检查结果"""
        monkeypatch.delenv("SOUWEN_TAVILY_API_KEY", raising=False)
        from souwen.config import get_config

        get_config.cache_clear()
        results = check_all()
        assert len(results) == 37

    def test_result_has_required_keys(self):
        """每条结果包含必要字段"""
        results = check_all()
        required = {"name", "category", "status", "tier", "required_key", "message"}
        for r in results:
            assert required.issubset(r.keys()), f"{r['name']} 缺少字段"

    def test_no_config_sources_are_ok(self):
        """无需配置的数据源（required_key=None）状态为 ok"""
        results = check_all()
        no_config = [r for r in results if r["required_key"] is None]
        assert len(no_config) > 0
        for r in no_config:
            assert r["status"] == "ok", f"{r['name']} 应该是 ok"

    def test_categories_are_valid(self):
        """所有 category 值在 paper/patent/web 中"""
        results = check_all()
        valid_cats = {"paper", "patent", "web"}
        for r in results:
            assert r["category"] in valid_cats

    def test_tier_values(self):
        """tier 只有 0, 1, 2"""
        results = check_all()
        for r in results:
            assert r["tier"] in (0, 1, 2)

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
        """_SOURCE_CONFIG 有 37 个数据源"""
        assert len(_SOURCE_CONFIG) == 37


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

    def test_contains_tier_sections(self):
        """包含三个 Tier 分组"""
        report = format_report(check_all())
        assert "Tier 0" in report
        assert "Tier 1" in report
        assert "Tier 2" in report

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

    def test_counts_in_header(self):
        """标题行显示 可用数/总数"""
        results = check_all()
        ok_count = sum(1 for r in results if r["status"] == "ok")
        report = format_report(results)
        assert f"{ok_count}/{len(results)}" in report
