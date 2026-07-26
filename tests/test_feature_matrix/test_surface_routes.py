from __future__ import annotations

import importlib

import pytest

pytest.importorskip("fastapi")

from souwen.server.app import app


@pytest.mark.parametrize("path", ["/api/v1/summarize", "/api/v1/fetch/summarize"])
def test_removed_summary_routes_are_not_exposed(path: str) -> None:
    assert path not in app.openapi()["paths"]


@pytest.mark.parametrize(
    "module_name",
    [
        "souwen.server.routes.summarize",
        "souwen.server.routes.fetch_summarize",
        "souwen.llm.summarize",
        "souwen.llm.fetch_summarize",
        "souwen.llm.prompts",
    ],
)
def test_removed_summary_modules_are_not_importable(module_name: str) -> None:
    assert importlib.util.find_spec(module_name) is None
