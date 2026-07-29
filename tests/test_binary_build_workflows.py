from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _workflow_text(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_rc4_server_bundle_workflow_is_a_read_only_reusable_proof_builder() -> None:
    text = _workflow_text(".github/workflows/build-pyinstaller-server.yml")
    trigger = text.split("\non:\n", maxsplit=1)[1].split("\nconcurrency:", maxsplit=1)[0]

    assert "workflow_call:" in trigger
    assert "workflow_dispatch:" in trigger
    assert "push:" not in trigger
    assert "candidate_sha:" in trigger
    for output in (
        "bundle_artifact_pattern:",
        "smoke_artifact_pattern:",
        "inventory_artifact:",
        "binary_count:",
    ):
        assert output in trigger
    assert "permissions:\n  contents: read" in text
    assert "persist-credentials: false" in text
    assert "contents: write" not in text
    assert "gh release" not in text
    assert "git tag" not in text
    assert "deploy-hf-space" not in text
    assert "release-candidate.yml" not in text


def test_rc4_server_bundle_workflow_has_exact_native_four_archive_matrix() -> None:
    text = _workflow_text(".github/workflows/build-pyinstaller-server.yml")
    expected = {
        "ubuntu-24.04": "souwen-server-2.0.0rc4-linux-amd64.tar.gz",
        "ubuntu-24.04-arm": "souwen-server-2.0.0rc4-linux-arm64.tar.gz",
        "macos-15": "souwen-server-2.0.0rc4-macos-arm64.tar.gz",
        "windows-2025": "souwen-server-2.0.0rc4-windows-amd64.zip",
    }

    assert text.count("archive: souwen-server-2.0.0rc4-") == 4
    for runner, archive in expected.items():
        assert f"os: {runner}" in text
        assert f"archive: {archive}" in text
        assert f"'{archive}'" in text
    assert "if actual != expected_names:" in text
    assert "'binary_count': 4" in text
    assert "output.write('binary_count=4\\n')" in text
    assert "bundle_digests[expected[platform]]" in text
    assert "payload.get('target_native') is not True" in text
    assert "payload.get('api_major') != 2" in text
    assert "payload.get('archive') != expected[platform]" in text
    assert "len(openapi_checksums) != 1" in text
    assert "set(checks_by_name) != required_checks" in text
    assert "status != 'PASS' for status in checks_by_name.values()" in text
    assert "VERIFIER_SHA: ${{ github.workflow_sha }}" in text
    assert "'verifier_sha': verifier" in text
    assert "'workflow_identity': '.github/workflows/build-pyinstaller-server.yml'" in text


def test_rc4_server_bundle_builds_tracked_target_onedir_with_bundled_chromium() -> None:
    text = _workflow_text(".github/workflows/build-pyinstaller-server.yml")

    assert 'pip install -e ".[server,tls,web,robots,scraper]"' in text
    assert 'pip install "playwright>=1.40" "setuptools<82" pyinstaller' in text
    assert "python -m playwright install --with-deps chromium" in text
    assert "python -m playwright install chromium" in text
    assert "pyinstaller --onedir" in text
    assert "deploy/process/server_main.py" in text
    assert "--paths src --paths deploy/process" in text
    assert "--hidden-import=supervisor" in text
    assert "--collect-all=playwright" in text
    assert "bundle_name = 'souwen-server'" in text
    assert "Path(produced).resolve() != output.resolve()" in text
    assert "shutil.copy2('runtime.source.sha', stage / 'runtime.source.sha')" in text
    assert "stage / 'ms-playwright'" in text
    assert "ref: ${{ github.workflow_sha }}" in text
    assert "path: .trusted-verifier" in text
    assert "uses: ./.trusted-verifier/.github/actions/server-bundle-smoke" in text
    assert 'PYTHON_OPTIONS+=(--python-option "X utf8=1")' in text
    assert text.index("Stage Chromium and create the final archive") < text.index(
        "Unpack final archive and run target-native server smoke"
    )
    for retired_surface in (
        ".[server,tls,web,robots,scraper,newspaper,readability]",
        "server_bundle_entry.py",
        '"--worker"',
        '"--api"',
    ):
        assert retired_surface not in text


def test_server_bundle_openapi_checksum_uses_the_verified_canonical_artifact() -> None:
    text = _workflow_text(".github/workflows/build-pyinstaller-server.yml")
    checksum_step = text.split("      - name: Compute target OpenAPI checksum", maxsplit=1)[
        1
    ].split("      - name: Build target server with PyInstaller onedir", maxsplit=1)[0]

    assert "python tools/gen_openapi.py --check" in checksum_step
    assert "python tools/gen_client_sdk.py --check" in checksum_step
    assert "python tools/gen_typescript_sdk.py --check" in checksum_step
    assert "contracts/openapi/souwen-openapi-2.0.0rc4.json" in checksum_step
    assert "artifact.read_bytes()" in checksum_step
    assert "from souwen.server.app import app" not in checksum_step
    assert "app.openapi()" not in checksum_step


def test_server_bundle_smoke_covers_target_release_contract() -> None:
    text = (REPO_ROOT / ".github/actions/server-bundle-smoke/action.yml").read_text(
        encoding="utf-8"
    )

    for check in (
        "archive/inventory",
        "archive/playwright-chromium",
        "archive/source-provenance",
        "runner/target-native",
        "server/health",
        "server/readiness-browser-worker",
        "server/canonical-provider-api",
        "server/api-major-fail-closed",
        "server/admin-fail-closed",
        "server/openapi-checksum",
        "server/clean-termination",
    ):
        assert check in text
    assert "bundle_root = root / 'souwen-server'" in text
    assert "top_level != {'souwen-server'}" in text
    assert "bundle_root / 'ms-playwright'" in text
    assert "target_native_machine()" in text
    assert "platform_info.machine().strip().lower()" in text
    assert "payload.extractall(root, filter='data')" in text
    assert "archive contains a link" in text
    assert "SOUWEN_SOURCE_SHA_FILE" in text
    assert "health.get('source_sha') != candidate_sha" in text
    assert "readiness.get('worker_source_sha') != candidate_sha" in text
    assert "readiness.get('components', {}).get('browser_worker') != 'ready'" in text
    assert "'/api/v1/providers'" in text
    assert "'SOUWEN_USER_PASSWORD': user_fixture" in text
    assert "'X-SouWen-Token': user_fixture" in text
    assert "mismatch.get('error', {}).get('code') != 'api_major_mismatch'" in text
    assert "'/api/v1/admin/ping', expected=(401,)" in text
    assert "request(base_url, '/openapi.json')" in text
    assert "canonical_openapi = json.dumps(" in text
    assert "actual_openapi_sha256 = hashlib.sha256(canonical_openapi).hexdigest()" in text
    assert "actual_openapi_sha256 != expected_openapi_sha256" in text
    assert "server bundle required a forced kill during termination" in text
    assert "server bundle left API or Browser Worker port open" in text
    assert "'target_native': failure is None" in text
    assert "'api_major': 2" in text
