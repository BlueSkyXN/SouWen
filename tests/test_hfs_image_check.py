"""Deterministic tests for the HFS image deploy-time check.

Only the judgment helpers and the pass/fail semantics are covered here; every
network path belongs to the workflow that runs the script inside the container.
"""

from __future__ import annotations

import asyncio

import pytest

from scripts import hfs_image_check as check
from scripts._functional_common import Outcome, ResultRecorder, run_check


def _search_payload(items: list[dict]) -> dict:
    return {"results": items, "sources": ["openalex"], "partial": False}


def _item(title: str = "A result", url: str = "https://example.com/a") -> dict:
    return {"title": title, "url": url}


class TestSearchJudgement:
    def test_three_usable_results(self):
        payload = _search_payload([_item(), _item(), _item()])
        assert check.usable_search_results(payload) == (3, 3)

    def test_blank_title_is_not_usable(self):
        payload = _search_payload([_item(), _item(title="   "), _item()])
        assert check.usable_search_results(payload) == (2, 3)

    def test_non_http_url_is_not_usable(self):
        payload = _search_payload([_item(), _item(url="ftp://example.com/a"), _item()])
        assert check.usable_search_results(payload) == (2, 3)

    def test_missing_results_field_is_zero(self):
        assert check.usable_search_results({"sources": []}) == (0, 0)
        assert check.usable_search_results(None) == (0, 0)

    def test_total_counts_every_item_even_when_unusable(self):
        payload = _search_payload([_item(), {"title": "", "url": "nope"}, {"nope": 1}])
        assert check.usable_search_results(payload) == (1, 3)


class TestFetchJudgement:
    def test_long_body_is_accepted(self):
        ok, reason = check.usable_fetch_body({"title": "T", "content": "x" * 600})
        assert ok
        assert "600 chars" in reason

    def test_short_body_is_rejected(self):
        ok, reason = check.usable_fetch_body({"content": "x" * 499})
        assert not ok
        assert "too short" in reason

    @pytest.mark.parametrize(
        "marker",
        ["Just a moment...", "Please verify you are human", "Checking your browser before"],
    )
    def test_interstitial_is_rejected(self, marker: str):
        body = marker + " " + "x" * 600
        ok, reason = check.usable_fetch_body({"title": "T", "content": body})
        assert not ok
        assert "interstitial" in reason

    def test_title_marker_also_rejects(self):
        ok, reason = check.usable_fetch_body({"title": "Access Denied", "content": "x" * 600})
        assert not ok
        assert "interstitial" in reason

    def test_non_string_content_is_rejected(self):
        ok, reason = check.usable_fetch_body({"content": None})
        assert not ok
        assert "not a string" in reason

    def test_non_mapping_payload_is_rejected(self):
        ok, _reason = check.usable_fetch_body(["not", "a", "mapping"])
        assert not ok


class TestToolTextParsing:
    def test_numbered_lines_are_detected(self):
        text = "1. First\n   https://a.example/x\n2. Second\n   https://b.example/y"
        numbered = [line for line in text.splitlines() if check._is_numbered_result(line)]
        assert numbered == ["1. First", "2. Second"]

    def test_url_lines_and_blanks_are_not_numbered_results(self):
        for line in ("   https://a.example/x", "", "sources: openalex", "1.", "a. b"):
            assert not check._is_numbered_result(line)


class TestTraceParsing:
    def test_trace_fields_are_parsed(self):
        text = "fl=1f2\nh=www.cloudflare.com\nip=203.0.113.7\nts=1\nwarp=on\n"
        fields = check._trace_fields(text)
        assert fields["warp"] == "on"
        assert fields["ip"] == "203.0.113.7"

    def test_lines_without_equals_are_skipped(self):
        assert check._trace_fields("garbage\nwarp=off\n") == {"warp": "off"}


class TestAuthMatrix:
    def _recorder(self) -> ResultRecorder:
        return ResultRecorder(script="demo", mode="auth")

    def _patch_statuses(self, monkeypatch, statuses: dict[str, int]) -> None:
        def fake(base, entry, headers, timeout=180.0):
            for name, case_headers, _expected in _CASES:
                if case_headers == headers:
                    return statuses[name]
            raise AssertionError(f"unexpected headers {headers!r}")

        monkeypatch.setattr(check, "_entry_status", fake)

    def test_matrix_passes_when_every_status_matches(self, monkeypatch):
        self._patch_statuses(
            monkeypatch,
            {"no_credential": 401, "wrong_bearer": 401, "correct": 200},
        )
        message, details = check._auth_matrix("http://x", entry="search", cases=_CASES)
        assert "3 credential cases" in message
        assert details["observed"] == {"no_credential": 401, "wrong_bearer": 401, "correct": 200}

    def test_matrix_fails_when_an_open_request_is_not_401(self, monkeypatch):
        self._patch_statuses(
            monkeypatch,
            {"no_credential": 200, "wrong_bearer": 401, "correct": 200},
        )
        with pytest.raises(check.ProbeError, match="no_credential: 200"):
            check._auth_matrix("http://x", entry="search", cases=_CASES)

    def test_matrix_fails_when_the_right_password_is_rejected(self, monkeypatch):
        self._patch_statuses(
            monkeypatch,
            {"no_credential": 401, "wrong_bearer": 401, "correct": 401},
        )
        with pytest.raises(check.ProbeError, match="correct: 401"):
            check._auth_matrix("http://x", entry="search", cases=_CASES)

    def test_accepted_status_allows_upstream_failure_after_auth(self, monkeypatch):
        """A 502 after the credential check passed is a source failure, not auth."""

        self._patch_statuses(
            monkeypatch,
            {"no_credential": 401, "wrong_bearer": 401, "correct": 502},
        )
        message, details = check._auth_matrix("http://x", entry="search", cases=_ACCEPTED_CASES)
        assert "3 credential cases" in message
        assert details["observed"]["correct"] == 502

    def test_accepted_status_still_rejects_403(self, monkeypatch):
        self._patch_statuses(
            monkeypatch,
            {"no_credential": 401, "wrong_bearer": 401, "correct": 403},
        )
        with pytest.raises(check.ProbeError, match="correct: 403"):
            check._auth_matrix("http://x", entry="search", cases=_ACCEPTED_CASES)


_CASES = [
    ("no_credential", {}, 401),
    ("wrong_bearer", check._auth_headers("wrong"), 401),
    ("correct", check._auth_headers("right"), 200),
]

_ACCEPTED_CASES = [
    ("no_credential", {}, 401),
    ("wrong_bearer", check._auth_headers("wrong"), 401),
    ("correct", check._auth_headers("right"), check.ACCEPTED),
]


class TestStatusSemantics:
    def test_expected_int_is_exact(self):
        assert check.status_ok(401, 401)
        assert not check.status_ok(403, 401)
        assert not check.status_ok(200, 401)

    def test_accepted_means_not_rejected(self):
        assert check.status_ok(200, check.ACCEPTED)
        assert check.status_ok(502, check.ACCEPTED)
        assert check.status_ok(504, check.ACCEPTED)
        assert not check.status_ok(401, check.ACCEPTED)
        assert not check.status_ok(403, check.ACCEPTED)


class TestOneRetry:
    def test_success_on_first_attempt_is_not_retried(self):
        calls = []

        def probe() -> str:
            calls.append(1)
            return "ok"

        value, retry = check.with_one_retry(probe)
        assert value == "ok"
        assert len(calls) == 1
        assert retry == {"attempts": 1, "first_failure": []}

    def test_a_failed_attempt_is_kept_when_the_retry_succeeds(self):
        calls = []

        def probe() -> str:
            calls.append(1)
            if len(calls) == 1:
                raise check.ProbeError("first attempt timed out")
            return "ok"

        value, retry = check.with_one_retry(probe)
        assert value == "ok"
        assert retry["attempts"] == 2
        assert retry["first_failure"] == ["attempt 1: first attempt timed out"]

    def test_only_one_retry_then_failure(self):
        calls = []

        def probe() -> str:
            calls.append(1)
            raise check.ProbeError("still down")

        with pytest.raises(check.ProbeError) as excinfo:
            check.with_one_retry(probe)
        assert len(calls) == 2
        assert "attempt 1" in str(excinfo.value)
        assert "attempt 2" in str(excinfo.value)


class TestBrowserProbe:
    def test_a_short_browser_body_fails(self, monkeypatch):
        class _Outcome:
            content = "   tiny   "
            final_url = "https://example.com/"
            title = "Example"

        async def fake_fetch(url, *, proxy):
            return _Outcome()

        monkeypatch.setattr(check, "_browser_fetch", fake_fetch)
        with pytest.raises(check.ProbeError, match="too short"):
            check.browser_probe(check.BROWSER_PROBE_URL, proxy=None)

    def test_a_real_body_passes_and_reports_the_exit(self, monkeypatch):
        class _Outcome:
            content = "x" * 200
            final_url = "https://example.com/"
            title = "Example"

        async def fake_fetch(url, *, proxy):
            return _Outcome()

        monkeypatch.setattr(check, "_browser_fetch", fake_fetch)
        details = check.browser_probe(check.BROWSER_PROBE_URL, proxy="socks5://127.0.0.1:1080")
        assert details["chars"] == 200
        assert details["proxy"] == "socks5://127.0.0.1:1080"
        assert details["final_url"] == "https://example.com/"


class TestFailureSemantics:
    """A required check must fail the run, unlike the data-collecting census."""

    def test_required_failure_exits_non_zero(self):
        recorder = ResultRecorder(script="demo", mode="authopen")

        def boom() -> None:
            raise check.ProbeError("open endpoint answered 200")

        asyncio.run(run_check(recorder, "authopen.search", boom, timeout=5))

        assert recorder.overall == Outcome.FAIL
        assert recorder.exit_code() == 1

    def test_skipped_revision_label_does_not_fail_the_run(self):
        recorder = ResultRecorder(script="demo", mode="image")

        def skip() -> None:
            raise check.CheckSkipped("label not supplied")

        asyncio.run(run_check(recorder, "image.revision_label", skip, timeout=5))

        assert recorder.checks[0].outcome == Outcome.SKIP
        assert recorder.exit_code() == 0


class TestCliSurface:
    def test_all_required_modes_are_available(self):
        assert set(check.MODES) == {
            "image",
            "http",
            "mcp",
            "auth",
            "authopen",
            "browser",
            "warp",
        }

    def test_image_mode_requires_an_expected_sha(self):
        args = check.parse_args(["--mode", "image"])
        with pytest.raises(SystemExit):
            check.check_image(ResultRecorder(script="s", mode="image"), args)

    def test_auth_mode_requires_a_password(self):
        args = check.parse_args(["--mode", "auth"])
        with pytest.raises(SystemExit):
            check.check_auth(ResultRecorder(script="s", mode="auth"), args)

    def test_frozen_smoke_inputs_match_the_census_set(self):
        import json
        from pathlib import Path

        queries = json.loads(Path("scripts/census/queries.json").read_text(encoding="utf-8"))
        assert check.SMOKE_SEARCH_QUERY in queries["domains"][check.SMOKE_SEARCH_DOMAIN]
        assert check.MIN_FETCH_CHARS == queries["min_fetch_chars"]
        assert check.SMOKE_SEARCH_LIMIT <= queries["search_page_limit"]
        assert check.SMOKE_FETCH_URL in queries["fetch_urls"]["static"]
