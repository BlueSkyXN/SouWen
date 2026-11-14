"""build_target_runtime 必须把 manifest 的阶梯声明推进 egress 注册表。

回归：此前只有 `agent.py` 门面在构建 runtime 前调用
`register_manifest_egress_bounds`；`serve` 与 `doctor` 直接调用
`build_target_runtime`，于是所有源回退到默认上限（proxy），
声明 `max_egress=browser` 的源在权威体检里永远拿不到 browser 级证据。
"""

from __future__ import annotations

import pytest

from souwen.common_runtime.egress import EgressBounds, egress_bounds_for
from souwen.common_runtime.egress.levels import EgressLevel


@pytest.fixture
def _clean_bounds(monkeypatch):
    """清空注册表，确保断言来自 build_target_runtime 而不是测试前置。"""

    from souwen.common_runtime.egress import levels

    monkeypatch.setattr(levels, "_DECLARED_BOUNDS", {})


def test_build_target_runtime_publishes_declared_bounds(monkeypatch, _clean_bounds) -> None:
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    from souwen.config import SouWenConfig
    from souwen.server.v2_runtime import build_target_runtime

    # 注册前：默认边界（不含 browser）
    assert egress_bounds_for("baidu") == egress_bounds_for("__unknown__")

    runtime = build_target_runtime(SouWenConfig())
    try:
        baidu = egress_bounds_for("baidu")
        assert baidu.max_level is EgressLevel.BROWSER, "baidu declares max_egress=browser"
        brave = egress_bounds_for("brave")
        assert brave.max_level is EgressLevel.BROWSER
        juejin = egress_bounds_for("juejin")
        assert juejin.max_level is EgressLevel.PROXY, "juejin declares max_egress=proxy"
        arxiv = egress_bounds_for("arxiv")
        assert arxiv.max_level is EgressLevel.IMPERSONATE
        # 未声明的内部 id 仍回退默认边界
        assert egress_bounds_for("__unknown__") == EgressBounds()
    finally:
        import asyncio

        asyncio.run(runtime.close())


def test_pinned_planner_reaches_browser_when_bounds_allow(monkeypatch, _clean_bounds) -> None:
    """注册生效后，请求 browser 的源在 planner 里真的拿到 browser。"""

    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    from souwen.config import SouWenConfig
    from souwen.server.doctor import _PinnedPlanner
    from souwen.server.v2_runtime import build_target_runtime

    runtime = build_target_runtime(SouWenConfig())
    try:
        planner = _PinnedPlanner("browser", lambda: None)
        decision = planner.plan("www.baidu.com", egress_bounds_for("baidu"))
        assert decision.level is EgressLevel.BROWSER
        yahoo = planner.plan("search.yahoo.com", egress_bounds_for("yahoo"))
        assert yahoo.level is EgressLevel.PROXY, "max=proxy sources still clamp to proxy"
    finally:
        import asyncio

        asyncio.run(runtime.close())
