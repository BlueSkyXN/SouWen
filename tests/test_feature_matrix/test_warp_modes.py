from __future__ import annotations

import pytest

from souwen.editions import (
    EDITIONS,
    WARP_MODE_MIN_EDITIONS,
    allowed_warp_modes,
    warp_mode_policy,
)
from souwen.server.warp import WarpMode


def test_warp_mode_policy_covers_all_runtime_modes() -> None:
    """Feature matrix WARP policy should stay aligned with the runtime enum."""

    enum_modes = {mode.value for mode in WarpMode}

    assert set(WARP_MODE_MIN_EDITIONS) == enum_modes
    for edition in EDITIONS:
        assert set(allowed_warp_modes(edition)) <= enum_modes


def test_basic_warp_modes_are_low_privilege_subset() -> None:
    assert allowed_warp_modes("basic") == ("auto", "wireproxy", "external")

    denied = {mode for mode in WarpMode if mode.value not in allowed_warp_modes("basic")}
    assert {mode.value for mode in denied} == {"kernel", "usque", "warp-cli"}
    for mode in denied:
        policy = warp_mode_policy(mode.value, "basic")
        assert policy.min_edition == "pro"
        assert policy.available is False


def test_admin_warp_modes_route_lists_physical_modes_with_edition_metadata(monkeypatch) -> None:
    """The admin modes endpoint omits auto but should cover all physical modes."""

    pytest.importorskip("fastapi", reason="server extras not installed")

    from souwen.config import get_config
    from souwen.server.routes.admin import warp as warp_routes

    class FakeWarpManager:
        def _has_wireproxy(self) -> bool:
            return True

        def _has_kernel_wg(self) -> bool:
            return True

        def _has_usque(self) -> bool:
            return True

        def _has_warp_cli(self) -> bool:
            return True

        @classmethod
        def get_instance(cls):
            return cls()

    monkeypatch.setenv("SOUWEN_EDITION", "basic")
    get_config.cache_clear()
    monkeypatch.setattr("souwen.server.warp.WarpManager", FakeWarpManager)

    import anyio

    response = anyio.run(warp_routes.warp_modes)
    route_modes = {item["id"]: item for item in response["modes"]}

    assert set(route_modes) == {mode.value for mode in WarpMode if mode is not WarpMode.AUTO}
    assert route_modes["wireproxy"]["edition_available"] is True
    assert route_modes["external"]["edition_available"] is True
    assert route_modes["kernel"]["edition_available"] is False
    assert route_modes["usque"]["edition_reason"] == (
        "WARP mode 'usque' requires edition=pro, current edition=basic"
    )
