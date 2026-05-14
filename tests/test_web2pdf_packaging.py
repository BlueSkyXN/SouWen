from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SUPERWEB2PDF_ARCHIVE = (
    "https://github.com/BlueSkyXN/SuperWeb2PDF/archive/"
    "d1e1da59d739ad46222b5e726bd6f28b0d0453fa.zip"
)


def test_web2pdf_extra_uses_resolvable_direct_reference() -> None:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'web2pdf = [' in text
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
        assert "WEB2PDF_PACKAGE" in text
        assert SUPERWEB2PDF_ARCHIVE in text
