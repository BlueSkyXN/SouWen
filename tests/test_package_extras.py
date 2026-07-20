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


def test_edition_extras_define_layered_install_profiles() -> None:
    """Edition extras should expose stable install surfaces without hand-copying deps."""

    assert _extra_dependencies("edition-basic") == ["souwen[tls,web,robots,mcp]"]
    assert _extra_dependencies("edition-pro") == ["souwen[edition-basic,server,scraper]"]
    assert _extra_dependencies("edition-full") == [
        "souwen[edition-pro,newspaper,readability,pdf,web2pdf]"
    ]


def test_full_browser_variants_keep_crawl4ai_and_scrapling_mutually_exclusive() -> None:
    """Full browser extras must not ask one resolver to install both conflicting stacks."""

    assert _extra_dependencies("edition-full-crawl4ai") == ["souwen[edition-full,crawl4ai]"]
    assert _extra_dependencies("edition-full-scrapling") == ["souwen[edition-full,scrapling]"]

    for extra in (
        "edition-full",
        "edition-full-crawl4ai",
        "edition-full-scrapling",
    ):
        deps = ",".join(_extra_dependencies(extra))
        assert not ("crawl4ai" in deps and "scrapling" in deps)
