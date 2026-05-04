import argparse
import asyncio
import json

from scripts._functional_common import (
    CheckSkipped,
    CheckWarning,
    Outcome,
    ResultRecorder,
    add_common_args,
    parse_common_args,
    run_check,
)


def test_recorder_overall_fails_only_on_required_failures():
    recorder = ResultRecorder(script="demo", mode="fixture")

    recorder.record("required", Outcome.PASS, required=True)
    recorder.record("optional", Outcome.FAIL, required=False)

    assert recorder.overall == Outcome.PASS
    assert recorder.exit_code() == 0

    recorder.record("required_failure", Outcome.FAIL, required=True)

    assert recorder.overall == Outcome.FAIL
    assert recorder.exit_code() == 1


def test_recorder_overall_warn_when_warn_exists_without_required_failure():
    recorder = ResultRecorder(script="demo", mode="live")

    recorder.record("required", Outcome.PASS, required=True)
    recorder.record("optional", Outcome.WARN, required=False, message="flaky")

    assert recorder.overall == Outcome.WARN
    assert recorder.exit_code() == 0


def test_recorder_overall_skip_when_all_checks_skip():
    recorder = ResultRecorder(script="demo", mode="offline")

    recorder.record("offline", Outcome.SKIP, required=False, message="disabled")

    assert recorder.overall == Outcome.SKIP
    assert recorder.exit_code() == 0


def test_write_reports_uses_json_as_source_of_truth(tmp_path):
    recorder = ResultRecorder(script="demo_check", mode="fixture")
    recorder.record("import", Outcome.PASS, required=True, message="ok", details={"version": "1"})

    json_report = tmp_path / "nested" / "report.json"
    markdown_report = tmp_path / "nested" / "report.md"
    recorder.write_reports(json_report=json_report, markdown_report=markdown_report)

    payload = json.loads(json_report.read_text(encoding="utf-8"))
    markdown = markdown_report.read_text(encoding="utf-8")
    assert payload["schema_version"] == 1
    assert payload["overall"] == "PASS"
    assert payload["checks"][0]["name"] == "import"
    assert "# Demo Check" in markdown
    assert '"overall": "PASS"' in markdown


def test_parse_common_args_returns_common_namespace():
    args = parse_common_args(
        "demo",
        [
            "--mode",
            "live",
            "--timeout",
            "12.5",
            "--json-report",
            "out.json",
            "--markdown-report",
            "out.md",
        ],
    )

    assert args.mode == "live"
    assert args.timeout == 12.5
    assert str(args.json_report) == "out.json"
    assert str(args.markdown_report) == "out.md"


def test_add_common_args_rejects_invalid_timeout():
    parser = argparse.ArgumentParser()
    add_common_args(parser)

    try:
        parser.parse_args(["--timeout", "0"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("invalid timeout should fail argument parsing")


def test_run_check_records_sync_success():
    recorder = ResultRecorder(script="demo", mode="fixture")

    result = asyncio.run(
        run_check(
            recorder,
            "sync",
            lambda: ("ok", {"count": 1}),
            required=True,
        )
    )

    assert result.outcome == Outcome.PASS
    assert result.message == "ok"
    assert result.details == {"count": 1}


def test_run_check_records_async_success():
    recorder = ResultRecorder(script="demo", mode="fixture")

    async def check():
        return {"async": True}

    result = asyncio.run(run_check(recorder, "async", check, required=True))

    assert result.outcome == Outcome.PASS
    assert result.details == {"async": True}


def test_run_check_records_required_exception_as_fail():
    recorder = ResultRecorder(script="demo", mode="fixture")

    def check():
        raise RuntimeError("boom")

    result = asyncio.run(run_check(recorder, "required", check, required=True))

    assert result.outcome == Outcome.FAIL
    assert result.required is True
    assert result.message == "boom"
    assert result.details["exception_type"] == "RuntimeError"


def test_run_check_records_optional_exception_as_warn():
    recorder = ResultRecorder(script="demo", mode="fixture")

    def check():
        raise RuntimeError("flaky")

    result = asyncio.run(run_check(recorder, "optional", check, required=False))

    assert result.outcome == Outcome.WARN
    assert result.required is False


def test_run_check_supports_skip_and_warning_exceptions():
    recorder = ResultRecorder(script="demo", mode="fixture")

    skipped = asyncio.run(
        run_check(
            recorder,
            "skip",
            lambda: (_ for _ in ()).throw(CheckSkipped("missing", details={"env": "TOKEN"})),
        )
    )
    warning = asyncio.run(
        run_check(
            recorder,
            "warn",
            lambda: (_ for _ in ()).throw(CheckWarning("slow", details={"seconds": 10})),
        )
    )

    assert skipped.outcome == Outcome.SKIP
    assert skipped.details == {"env": "TOKEN"}
    assert warning.outcome == Outcome.WARN
    assert warning.details == {"seconds": 10}


def test_run_check_enforces_async_timeout():
    recorder = ResultRecorder(script="demo", mode="fixture")

    async def check():
        await asyncio.sleep(0.05)

    result = asyncio.run(run_check(recorder, "slow", check, required=True, timeout=0.001))

    assert result.outcome == Outcome.FAIL
    assert result.details["exception_type"] == "TimeoutError"
