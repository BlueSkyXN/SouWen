from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _optional_dependency_block() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(
        r"^\[project\.optional-dependencies\]\n(?P<body>.*?)(?=^\[)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, "missing [project.optional-dependencies]"
    return match.group("body")


def _extra_dependencies(name: str) -> list[str]:
    block = _optional_dependency_block()
    match = re.search(
        rf"^{re.escape(name)} = \[(?P<body>.*?)\]\n",
        block,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"missing optional dependency extra: {name}"
    return re.findall(r'"([^"]+)"', match.group("body"))


def test_distributions_exclude_local_agent_metadata() -> None:
    """sdist must not package local Codex/Claude metadata or absolute symlinks."""

    text = PYPROJECT.read_text(encoding="utf-8")
    build_section = re.search(
        r"^\[tool\.hatch\.build\]\n(?P<body>.*?)(?=^\[)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert build_section is not None, "missing [tool.hatch.build]"
    exclude_line = re.search(
        r"^exclude = \[(?P<body>[^\]]*)\]$", build_section["body"], re.MULTILINE
    )
    assert exclude_line is not None, "missing Hatch build excludes"
    excluded = set(re.findall(r'"([^"]+)"', exclude_line["body"]))

    assert {"/.codex", "/.claude"} <= excluded


def test_leaf_extras_define_explicit_install_surfaces() -> None:
    """Install surfaces use leaf extras rather than edition aggregates."""

    extras = _optional_dependency_block()
    assert not re.search(r"^edition-", extras, flags=re.MULTILINE)
    assert _extra_dependencies("server") == ["fastapi>=0.111", "uvicorn[standard]>=0.29"]
    assert _extra_dependencies("tls") == ["curl-cffi>=0.14.0"]
    assert _extra_dependencies("web") == ["trafilatura>=1.0"]
    assert _extra_dependencies("robots") == ["protego>=0.3.0"]
    assert _extra_dependencies("scraper") == ["curl-cffi>=0.14.0"]


def test_pdf_capture_extras_and_direct_references_are_removed() -> None:
    extras = _optional_dependency_block()

    assert not re.search(r"^pdf =", extras, flags=re.MULTILINE)
    assert not re.search(r"^web2pdf =", extras, flags=re.MULTILINE)
    assert "pymupdf4llm" not in extras
    assert "superweb2pdf" not in extras
    assert "allow-direct-references" not in PYPROJECT.read_text(encoding="utf-8")


def test_retired_browser_extras_are_absent() -> None:
    extras = _optional_dependency_block()

    assert not re.search(r"^(?:crawl4ai|scrapling) =", extras, flags=re.MULTILINE)
