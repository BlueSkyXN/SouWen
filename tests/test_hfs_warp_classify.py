"""Deterministic tests for the WARP leg verdict (复核 R2).

The workflow keeps the probe's exit code and the report, then classifies the
report content: only the external egress probe failing may read as
"unverified"; implementation errors, required browser/HTTP/MCP failures after
the proxy came up, and missing or corrupt reports must fail the job.
"""

from __future__ import annotations

from scripts.hfs_warp_classify import (
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_UNVERIFIED,
    classify,
)


def _check(name: str, outcome: str, details: dict | None = None) -> dict:
    return {"name": name, "outcome": outcome, "required": True, "details": details or {}}


def _warp_checks(**overrides) -> list[dict]:
    checks = [
        _check("warp.socks_egress", "PASS", {"history": [{"attempt": 1, "warp": "on"}]}),
        _check("warp.exit_differs", "PASS"),
        _check("warp.browser_via_warp", "PASS"),
        _check("warp.mcp_after_warp", "PASS"),
        _check("warp.http_after_warp", "PASS"),
    ]
    for name, outcome, details in overrides.pop("replace", []):
        for index, check in enumerate(checks):
            if check["name"] == name:
                checks[index] = _check(name, outcome, details)
    assert not overrides, overrides
    return checks


def _report(checks: list[dict]) -> dict:
    return {"schema_version": 1, "script": "hfs_image_check:warp", "checks": checks}


class TestWarpLegClassification:
    def test_all_pass_reads_as_pass(self):
        verdict, reason = classify(_report(_warp_checks()), kind="warp")
        assert verdict == VERDICT_PASS
        assert "all WARP checks passed" in reason

    def test_a_browser_failure_after_the_proxy_came_up_fails(self):
        checks = _warp_checks(replace=[("warp.browser_via_warp", "FAIL", {"chars": 0})])
        verdict, reason = classify(_report(checks), kind="warp")
        assert verdict == VERDICT_FAIL
        assert "warp.browser_via_warp" in reason
        assert "after the proxy came up" in reason

    def test_an_empty_search_or_captcha_fetch_fails(self):
        checks = _warp_checks(
            replace=[
                (
                    "warp.http_after_warp",
                    "FAIL",
                    {"search_usable": 0, "fetch_judgement": "interstitial marker: captcha"},
                )
            ]
        )
        verdict, reason = classify(_report(checks), kind="warp")
        assert verdict == VERDICT_FAIL
        assert "warp.http_after_warp" in reason

    def test_external_egress_failure_is_unverified_not_failed(self):
        checks = _warp_checks(
            replace=[
                (
                    "warp.socks_egress",
                    "FAIL",
                    {
                        "history": [{"attempt": n, "error": "ConnectError"} for n in range(1, 19)],
                        "warp_state": {"state_file": "missing"},
                    },
                )
            ]
        )
        verdict, reason = classify(_report(checks), kind="warp")
        assert verdict == VERDICT_UNVERIFIED
        assert "18 recorded attempt(s)" in reason
        assert "unverified, not passed" in reason

    def test_an_implementation_error_is_never_an_environment_problem(self):
        checks = _warp_checks(
            replace=[
                (
                    "warp.socks_egress",
                    "FAIL",
                    {
                        "history": [{"attempt": 1, "error": "ConnectError"}],
                        "warp_state": {
                            "state_file": "/run/souwen-warp.json",
                            "mode": "usque",
                            "status": "error",
                            "last_error": "'WarpManager' object has no attribute '_start_usque'",
                            "implementation_error": True,
                        },
                    },
                )
            ]
        )
        verdict, reason = classify(_report(checks), kind="warp")
        assert verdict == VERDICT_FAIL
        assert "implementation error" in reason
        assert "_start_usque" in reason


class TestUsqueForcedClassification:
    def test_usque_proven_when_the_manager_ran_usque(self):
        checks = [
            _check("usqueforced.mode_requested", "PASS"),
            _check(
                "usqueforced.socks_egress",
                "PASS",
                {
                    "history": [{"attempt": 1, "warp": "on"}],
                    "warp_state": {"mode": "usque", "status": "enabled"},
                },
            ),
            _check("usqueforced.actual_mode", "PASS", {"mode": "usque", "status": "enabled"}),
            _check("usqueforced.browser_via_usque", "PASS"),
        ]
        verdict, _reason = classify(_report(checks), kind="usque-forced")
        assert verdict == VERDICT_PASS

    def test_external_registration_failure_leaves_usque_unproven(self):
        checks = [
            _check("usqueforced.mode_requested", "PASS"),
            _check(
                "usqueforced.socks_egress",
                "FAIL",
                {
                    "history": [{"attempt": n, "error": "ConnectError"} for n in range(1, 13)],
                    "warp_state": {
                        "mode": "usque",
                        "status": "error",
                        "last_error": "usque 注册失败（可能触发速率限制）",
                        "implementation_error": False,
                    },
                },
            ),
            _check("usqueforced.actual_mode", "FAIL", {"mode": "usque", "status": "error"}),
            _check("usqueforced.browser_via_usque", "FAIL"),
        ]
        verdict, reason = classify(_report(checks), kind="usque-forced")
        assert verdict == VERDICT_UNVERIFIED
        assert "usque itself remains unproven" in reason

    def test_a_fallback_mode_is_not_usage_evidence(self):
        checks = [
            _check("usqueforced.mode_requested", "PASS"),
            _check(
                "usqueforced.socks_egress",
                "PASS",
                {"history": [{"attempt": 1, "warp": "on"}]},
            ),
            _check(
                "usqueforced.actual_mode",
                "FAIL",
                {"mode": "wireproxy", "status": "enabled"},
            ),
            _check("usqueforced.browser_via_usque", "PASS"),
        ]
        verdict, reason = classify(_report(checks), kind="usque-forced")
        assert verdict == VERDICT_FAIL
        assert "usqueforced.actual_mode" in reason


class TestReportIntegrity:
    def test_a_missing_report_fails(self):
        verdict, reason = classify(None, kind="warp")
        assert verdict == VERDICT_FAIL
        assert "missing or corrupt" in reason

    def test_a_corrupt_report_fails(self):
        verdict, reason = classify(["not", "a", "mapping"], kind="warp")
        assert verdict == VERDICT_FAIL
        assert "missing or corrupt" in reason

    def test_an_incomplete_report_fails(self):
        checks = [check for check in _warp_checks() if check["name"] != "warp.http_after_warp"]
        verdict, reason = classify(_report(checks), kind="warp")
        assert verdict == VERDICT_FAIL
        assert "missing checks: warp.http_after_warp" in reason

    def test_an_empty_check_list_fails(self):
        verdict, reason = classify(_report([]), kind="usque-forced")
        assert verdict == VERDICT_FAIL
