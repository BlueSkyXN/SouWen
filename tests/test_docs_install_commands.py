from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_public_readmes_and_getting_started_use_leaf_install_profiles() -> None:
    public_docs = (
        REPO_ROOT / "README.md",
        REPO_ROOT / "README.en.md",
        REPO_ROOT / "docs/getting-started.md",
    )

    for path in public_docs:
        text = path.read_text(encoding="utf-8")

        assert 'pip install -e ".[server,tls,web,robots,scraper]"' in text
        assert 'pip install -e ".[server,tls,web,robots,scraper,crawl4ai]"' in text
        assert 'pip install -e ".[server,tls,web,robots,scraper,scrapling]"' in text
        assert "edition-" not in text

    contributing = (REPO_ROOT / "docs/contributing.md").read_text(encoding="utf-8")
    assert 'pip install -e ".[dev,server,tls,web,robots,scraper]"' in contributing
    assert "edition-" not in contributing
