from __future__ import annotations

import argparse
import asyncio

import pytest

from scripts import taiwan_new_books_functional_check as check
from scripts._functional_common import Outcome, ResultRecorder


def test_offline_mode_does_not_make_requests() -> None:
    recorder = ResultRecorder(script="test", mode="offline")
    asyncio.run(
        check.run_selected_checks(
            argparse.Namespace(mode="offline", required=False, timeout=1), recorder
        )
    )
    assert recorder.overall == Outcome.SKIP


def test_live_mode_requires_explicit_execute_flag() -> None:
    with pytest.raises(SystemExit, match="2"):
        asyncio.run(check.main(["--mode", "live"]))


@pytest.mark.asyncio
async def test_live_failure_is_warn_unless_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check, "verify_taiwan_new_books_registered", lambda: ("ok", {}))
    monkeypatch.setattr(
        check,
        "run_taiwan_new_books_local_catalog_smoke",
        lambda: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    recorder = ResultRecorder(script="test", mode="live")
    await check.run_selected_checks(
        argparse.Namespace(mode="live", required=False, timeout=1), recorder
    )
    assert recorder.checks[-1].outcome == Outcome.WARN
