"""Deterministic tests for the census judgment logic and frozen input file."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import census


def _search_payload(items: list[dict]) -> dict:
    return {
        "items": items,
        "page": {"next_cursor": None},
        "meta": {"partial": False, "requested": (), "succeeded": (), "failed": ()},
        "context": {"request_id": "test"},
    }


def _item(title: str = "A result", url: str = "https://example.com/a") -> dict:
    return {"id": "x", "title": title, "url": url, "provenance": []}


class TestSearchJudgment:
    def test_three_valid_items_pass(self):
        payload = _search_payload([_item(), _item(), _item()])
        assert census.search_query_valid(payload, min_results=3)
        assert census.count_valid_search_items(payload) == (3, 3)

    def test_two_valid_items_fail_threshold(self):
        payload = _search_payload([_item(), _item()])
        assert not census.search_query_valid(payload, min_results=3)

    def test_blank_title_is_invalid(self):
        payload = _search_payload([_item(), _item(title="  "), _item()])
        assert census.count_valid_search_items(payload) == (2, 3)

    def test_non_http_url_is_invalid(self):
        payload = _search_payload([_item(), _item(url="ftp://example.com/a"), _item()])
        assert census.count_valid_search_items(payload) == (2, 3)

    def test_missing_url_is_invalid(self):
        item = _item()
        item.pop("url")
        payload = _search_payload([_item(), item, _item()])
        assert census.count_valid_search_items(payload) == (2, 3)

    def test_non_payload_shapes_return_zero(self):
        assert census.count_valid_search_items(None) == (0, 0)
        assert census.count_valid_search_items({"items": "nope"}) == (0, 0)


class TestFetchJudgment:
    def _fetch_payload(self, content: str, *, status: str = "success", title: str = "Page") -> dict:
        return {
            "items": [
                {
                    "target": "https://example.com/",
                    "status": status,
                    "title": title,
                    "content": content,
                }
            ],
            "meta": {"partial": False},
        }

    def test_long_content_passes(self):
        payload = self._fetch_payload("word " * 200)
        assert census.fetch_content_success(payload, min_chars=500)

    def test_short_content_fails(self):
        payload = self._fetch_payload("short")
        assert not census.fetch_content_success(payload, min_chars=500)

    def test_verification_page_fails(self):
        payload = self._fetch_payload("word " * 200, title="Just a moment...")
        assert not census.fetch_content_success(payload, min_chars=500)

    def test_captcha_body_fails(self):
        payload = self._fetch_payload("please complete the captcha to continue " * 30)
        assert not census.fetch_content_success(payload, min_chars=500)

    def test_failed_status_fails(self):
        payload = self._fetch_payload("word " * 200, status="failed")
        assert not census.fetch_content_success(payload, min_chars=500)

    def test_marker_check_is_case_insensitive_and_bounded(self):
        payload = self._fetch_payload("word " * 200, title="ACCESS DENIED")
        assert not census.fetch_content_success(payload, min_chars=500)


class TestVerdictAggregation:
    def test_two_of_three_passes(self):
        verdict = census.verdict_from_counts("src", 2, 3, detail="")
        assert verdict.outcome == "PASS"

    def test_one_of_three_warns(self):
        verdict = census.verdict_from_counts("src", 1, 3, detail="")
        assert verdict.outcome == "WARN"

    def test_zero_fails(self):
        verdict = census.verdict_from_counts("src", 0, 3, detail="")
        assert verdict.outcome == "FAIL"

    def test_zero_probes_skips(self):
        verdict = census.verdict_from_counts("src", 0, 0, detail="")
        assert verdict.outcome == "SKIP"

    def test_aggregate_groups_by_label(self):
        outcomes = [
            census.ProbeOutcome(label="a", query="q1", valid=True),
            census.ProbeOutcome(label="a", query="q2", valid=False, error="x"),
            census.ProbeOutcome(label="a", query="q3", valid=True),
            census.ProbeOutcome(label="b", query="q1", valid=False, error="y"),
        ]
        verdicts = {item.label: item for item in census.aggregate(outcomes)}
        assert verdicts["a"].outcome == "PASS"
        assert verdicts["b"].outcome == "FAIL"
        assert "x" in verdicts["a"].detail

    def test_report_overall_and_sort_order(self):
        outcomes = [
            census.ProbeOutcome(label="fail-src", query="q", valid=False, error="boom"),
            census.ProbeOutcome(label="warn-src", query="q", valid=True),
            census.ProbeOutcome(label="warn-src", query="q2", valid=False),
            census.ProbeOutcome(label="warn-src", query="q3", valid=False),
        ]
        report = census.build_report(
            mode="sources", label="test", base_url="http://x/", outcomes=outcomes
        )
        assert report["overall"] == "FAIL"
        labels = [item["label"] for item in report["verdicts"]]
        assert labels[0] == "fail-src"
        by_label = {item["label"]: item for item in report["verdicts"]}
        assert by_label["warn-src"]["outcome"] == "WARN"


class TestPlanSelection:
    @pytest.fixture()
    def queries(self) -> dict:
        return json.loads(
            (Path(__file__).resolve().parents[1] / "scripts/census/queries.json").read_text(
                encoding="utf-8"
            )
        )

    def test_queries_file_shape(self, queries):
        assert queries["schema_version"] == 1
        assert len(queries["census_domains"]) == 10
        for domain, domain_queries in queries["domains"].items():
            assert len(domain_queries) == 10, domain
            assert len(set(domain_queries)) == 10, domain
        assert set(queries["domains"]) == set(queries["census_domains"])
        for category in ("static", "js", "anticrawl"):
            assert len(queries["fetch_urls"][category]) == 10
            assert len(set(queries["fetch_urls"][category])) == 10
        fetch_sources = {
            source for source, meta in queries["sources"].items() if meta["kind"] == "fetch"
        }
        assert set(queries["fetch_source_probes"]) == fetch_sources
        for source, meta in queries["sources"].items():
            if meta["kind"] == "search":
                assert meta["domain"] in queries["domains"], source

    def test_sources_mode_plan_covers_all_sources(self, queries):
        plan = census.select_queries(queries, "sources", None)
        targets = {entry["target"] for entry in plan}
        assert targets == set(queries["sources"])
        search_entries = [entry for entry in plan if entry["kind"] == "search"]
        assert len(search_entries) == 3 * sum(
            1 for meta in queries["sources"].values() if meta["kind"] == "search"
        )

    def test_only_filter_limits_plan(self, queries):
        plan = census.select_queries(queries, "sources", ["duckduckgo", "wayback"])
        targets = {entry["target"] for entry in plan}
        assert targets == {"duckduckgo", "wayback"}

    def test_domains_mode_plan(self, queries):
        plan = census.select_queries(queries, "domains", None)
        assert len(plan) == 100
        assert all(entry["provider"] is None for entry in plan)

    def test_fetch_mode_plan(self, queries):
        plan = census.select_queries(queries, "fetch", None)
        assert len(plan) == 30
        assert {entry["category"] for entry in plan} == {"static", "js", "anticrawl"}


class TestRender:
    def test_markdown_report_has_no_credentials(self):
        outcomes = [
            census.ProbeOutcome(label="src", query="q", valid=True, result_count=5),
            census.ProbeOutcome(label="src", query="q2", valid=True),
            census.ProbeOutcome(label="src", query="q3", valid=True),
            census.ProbeOutcome(label="src2", query="q", valid=False, error="secret-token-leak"),
        ]
        report = census.build_report(
            mode="sources", label="warp-on", base_url="http://127.0.0.1:49265", outcomes=outcomes
        )
        markdown = census.render_markdown(report)
        assert "Bearer" not in markdown
        assert "warp-on" in markdown
        assert "| `src` | PASS |" in markdown
