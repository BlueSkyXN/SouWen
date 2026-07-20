from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_public_readmes_and_getting_started_use_edition_install_profiles() -> None:
    docs = (
        REPO_ROOT / "README.md",
        REPO_ROOT / "README.en.md",
        REPO_ROOT / "docs/getting-started.md",
    )

    for path in docs:
        text = path.read_text(encoding="utf-8")

        assert 'pip install -e ".[edition-pro]"' in text
        assert 'pip install -e ".[edition-full-crawl4ai]"' in text
        assert 'pip install -e ".[edition-full-scrapling]"' in text
        assert 'pip install -e ".[server,tls,web,scraper]"' not in text
        assert 'pip install -e ".[server,tls,web,scraper,pdf,crawl4ai' not in text
        assert 'pip install -e ".[server,tls,web,scraper,pdf,scrapling' not in text


def test_plugin_spec_documents_docker_edition_pro_install() -> None:
    text = (REPO_ROOT / "docs/plugin-integration-spec.md").read_text(encoding="utf-8")

    assert "`.[edition-pro]`" in text
    assert "`.[server,tls]`" not in text
