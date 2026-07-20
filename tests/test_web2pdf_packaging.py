from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SUPERWEB2PDF_ARCHIVE = (
    "https://github.com/BlueSkyXN/SuperWeb2PDF/archive/d1e1da59d739ad46222b5e726bd6f28b0d0453fa.zip"
    "#sha256=f56a380aa3f06d169d3fcc723d5525779519afaff159b37e8a789e50b797c76b"
)


def test_web2pdf_extra_uses_resolvable_direct_reference() -> None:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "web2pdf = [" in text
    assert "allow-direct-references = true" in text
    assert '"playwright>=1.40"' in text
    assert SUPERWEB2PDF_ARCHIVE in text
    assert "superweb2pdf" + "[capture]>=0.2.0" not in text


def test_docker_web2pdf_paths_do_not_use_broken_extra() -> None:
    for relative in [
        "Dockerfile",
        "cloud/hfs/Dockerfile",
        "cloud/modelscope/Dockerfile",
    ]:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert ".[server,tls," + "web2pdf]" not in text
        assert 'pip install ".[server,tls]"' not in text
        assert 'pip install ".[edition-pro]"' in text
        assert "WEB2PDF_PACKAGE" in text
        assert SUPERWEB2PDF_ARCHIVE in text


def test_ci_web2pdf_optional_install_uses_resolvable_direct_reference() -> None:
    text = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "superweb2pdf" + "[capture]>=0.2.0" not in text
    assert '"playwright>=1.40"' in text
    assert f'"superweb2pdf @ {SUPERWEB2PDF_ARCHIVE}"' in text
