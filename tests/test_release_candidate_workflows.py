from __future__ import annotations

import ast
import hashlib
import json
import re
import textwrap
from pathlib import Path
from typing import TypedDict

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"


def _workflow(name: str) -> str:
    return (WORKFLOW_DIR / name).read_text(encoding="utf-8")


def _workflow_trigger(text: str, name: str) -> str:
    on_block = text.split("\non:\n", maxsplit=1)[1].split("\nconcurrency:", maxsplit=1)[0]
    trigger = on_block.split(f"  {name}:", maxsplit=1)[1]
    next_trigger = re.search(r"\n  [a-z][a-z0-9_-]*:", trigger)
    return trigger[: next_trigger.start()] if next_trigger else trigger


def _job(text: str, name: str, next_name: str) -> str:
    return text.split(f"  {name}:", maxsplit=1)[1].split(f"  {next_name}:", maxsplit=1)[0]


def _python_heredoc(block: str, index: int = 0) -> str:
    source = block.split("python3 - <<'PY'")[index + 1].split("\n          PY", maxsplit=1)[0]
    return textwrap.dedent(source).lstrip()


class WorkflowJob(TypedDict):
    needs: list[str]
    condition: str


def _release_candidate_job_graph(text: str) -> dict[str, WorkflowJob]:
    """Parse the workflow's top-level job dependencies and conditions.

    The release candidate keeps ``needs`` inline today, but this intentionally
    handles both inline and block lists so the downstream-gate contract follows
    the graph rather than a hand-maintained job list.
    """

    jobs_text = text.split("\njobs:\n", maxsplit=1)[1]
    jobs: dict[str, WorkflowJob] = {}
    current: WorkflowJob | None = None
    collecting_needs = False
    job_pattern = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
    inline_needs_pattern = re.compile(r"^    needs:\s*\[([^]]*)\]\s*$")

    for line in jobs_text.splitlines():
        job_match = job_pattern.match(line)
        if job_match:
            current = {"needs": [], "condition": ""}
            jobs[job_match.group(1)] = current
            collecting_needs = False
            continue
        if current is None:
            continue

        inline_needs = inline_needs_pattern.match(line)
        if inline_needs:
            current["needs"] = [
                job_id.strip() for job_id in inline_needs.group(1).split(",") if job_id.strip()
            ]
            collecting_needs = False
            continue
        if line == "    needs:":
            current["needs"] = []
            collecting_needs = True
            continue
        if collecting_needs and line.startswith("      - "):
            current["needs"].append(line.removeprefix("      - ").strip())
            continue
        collecting_needs = False
        if line.startswith("    if:"):
            current["condition"] = line.split(":", maxsplit=1)[1].strip()

    return jobs


def _downstream_jobs(graph: dict[str, WorkflowJob], root: str) -> set[str]:
    reverse: dict[str, set[str]] = {job_id: set() for job_id in graph}
    for job_id, job in graph.items():
        for dependency in job["needs"]:
            reverse.setdefault(dependency, set()).add(job_id)

    discovered: set[str] = set()
    pending = list(reverse.get(root, set()))
    while pending:
        job_id = pending.pop()
        if job_id in discovered:
            continue
        discovered.add(job_id)
        pending.extend(reverse.get(job_id, set()))
    return discovered


def test_workflow_embedded_python_blocks_compile() -> None:
    paths = list(WORKFLOW_DIR.glob("*.yml"))
    paths.extend((REPO_ROOT / ".github" / "actions").glob("*/action.yml"))
    compiled = 0

    for path in paths:
        lines = path.read_text(encoding="utf-8").splitlines()
        index = 0
        while index < len(lines):
            if "<<'PY'" not in lines[index] or "python" not in lines[index]:
                index += 1
                continue
            end = index + 1
            while end < len(lines) and lines[end].strip() != "PY":
                end += 1
            assert end < len(lines), f"unclosed Python heredoc: {path}:{index + 1}"
            source = textwrap.dedent("\n".join(lines[index + 1 : end])) + "\n"
            compile(source, f"{path}:{index + 2}", "exec")
            compiled += 1
            index = end + 1

    assert compiled >= 19


@pytest.mark.parametrize(
    "workflow_name",
    ("ci.yml", "v2-ci.yml", "deploy-hf-space.yml", "external-smoke-gate.yml"),
)
def test_main_pr_gates_run_when_a_retargeted_stack_layer_becomes_ready(
    workflow_name: str,
) -> None:
    trigger = _workflow_trigger(_workflow(workflow_name), "pull_request")

    assert "branches: [main]" in trigger
    assert "types: [opened, synchronize, reopened, ready_for_review]" in trigger


def test_release_candidate_is_the_only_release_publisher() -> None:
    candidate = _workflow("release-candidate.yml")
    assert "workflow_dispatch:" in candidate
    assert "push:" not in candidate.split("jobs:", maxsplit=1)[0]
    assert "environment:\n      name: release" in candidate
    assert "gh release create" in candidate
    assert 'git tag -a "$TAG" "$CANDIDATE_SHA"' in candidate
    assert 'git push origin "refs/tags/$TAG"' in candidate
    assert "--draft" in candidate
    assert 'gh release edit "$TAG" --draft=false' in candidate
    assert "report_partial_release" in candidate
    assert "Do not move or overwrite this tag" in candidate
    assert "remote_tag_state=unknown" in candidate
    assert "release_state=unknown" in candidate
    assert 'git ls-remote --tags origin "refs/tags/$TAG" || true' not in candidate

    for path in WORKFLOW_DIR.glob("*.yml"):
        if path.name == "release-candidate.yml":
            continue
        text = path.read_text(encoding="utf-8")
        assert "softprops/action-gh-release" not in text
        assert "gh release create" not in text


def test_release_candidate_strictly_validates_promotion_inputs() -> None:
    text = _workflow("release-candidate.yml")
    trust_step = text.split(
        "- name: Validate candidate trust, SHA, version, and promotion controls",
        maxsplit=1,
    )[1].split("- uses: actions/setup-python@v6", maxsplit=1)[0]
    assert "python3 -I - <<'PY'" in trust_step
    assert "python3 - <<'PY'" not in trust_step
    assert "re.fullmatch(r'[0-9a-f]{40}', candidate)" in text
    assert "project_version != version" in text
    assert "publish == 'true' and deploy_hfs != 'true'" in text
    assert "publish and deploy_hfs must be typed booleans" in text
    assert "refusing to overwrite existing tag" in text
    assert "runtime_version != version" in text
    assert "openapi_version != version" in text
    assert "panel_lock['version'] != panel['version']" in text
    assert "for readme_name in ('README.md', 'README.en.md')" in text
    assert "r'(?:a|b|rc)[0-9]+'" in text
    assert "accepted prerelease candidate" in text
    assert "current release surface only accepts version 2.0.0rc2" in text
    assert "product_name = 'Souwen v2rc2'" in text
    assert "api_major = 2" in text
    assert "RC2 publication remains disabled until Phase 8" in text
    assert '--title "$PRODUCT_NAME"' in text
    assert text.index("git', 'merge-base', '--is-ancestor'") < text.index(
        'pip install -e ".[server,tls,web,robots,scraper]"'
    )
    assert "release-candidate must run from the current origin/main control plane" in text
    assert "candidate_sha to equal the current origin/main" in text
    assert "verifier_sha" in text
    assert text.count("secrets: inherit") == 1
    hfs_call = _job(text, "hfs", "assemble-deployment")
    assert "uses: ./.github/workflows/deploy-hf-space.yml" in hfs_call
    assert "secrets: inherit" in hfs_call


def test_rc2_release_version_surfaces_are_consistent() -> None:
    from souwen import __version__

    version = "2.0.0rc2"
    panel_version = "2.0.0-rc2"
    product_name = "Souwen v2rc2"

    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    panel = json.loads((REPO_ROOT / "panel/package.json").read_text(encoding="utf-8"))
    panel_lock = json.loads((REPO_ROOT / "panel/package-lock.json").read_text(encoding="utf-8"))
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    workflow = _workflow("release-candidate.yml")

    assert __version__ == version
    assert f'version = "{version}"' in pyproject
    assert panel["version"] == panel_version
    assert panel_lock["version"] == panel_version
    assert panel_lock["packages"][""]["version"] == panel_version
    assert f"## v{version}" in changelog
    assert f"product_name = '{product_name}'" in workflow
    assert f"current release surface only accepts version {version}" in workflow


def test_release_candidate_requires_an_explicit_evidence_profile() -> None:
    text = _workflow("release-candidate.yml")
    dispatch = text.split("  workflow_dispatch:", maxsplit=1)[1].split("concurrency:", maxsplit=1)[
        0
    ]
    profile = dispatch.split("      evidence_profile:", maxsplit=1)[1].split(
        "      publish:", maxsplit=1
    )[0]

    assert "required: true" in profile
    assert "type: choice" in profile
    assert "default: select" in profile
    for option in ("select", "deployment", "release"):
        assert f"- {option}" in profile

    trust_step = text.split(
        "- name: Validate candidate trust, SHA, version, and promotion controls",
        maxsplit=1,
    )[1].split("- uses: actions/setup-python@v6", maxsplit=1)[0]
    assert "EVIDENCE_PROFILE: ${{ inputs.evidence_profile }}" in trust_step
    assert "evidence_profile not in {'deployment', 'release'}" in trust_step
    assert "deployment profile requires deploy_hfs=true" in trust_step
    assert "deployment profile requires publish=false" in trust_step
    assert "publish=true requires evidence_profile=release" in trust_step
    assert "evidence_profile=${{ inputs.evidence_profile }}" in text.splitlines()[2]


def test_deployment_profile_skips_release_server_bundles_and_gates_hfs() -> None:
    text = _workflow("release-candidate.yml")
    server_bundles = _job(text, "server-bundles", "package")
    promotion_gate = _job(text, "promotion-gate", "hfs")
    hfs = _job(text, "hfs", "assemble-deployment")

    release_only = "if: ${{ inputs.evidence_profile == 'release' }}"
    assert release_only in server_bundles
    assert "if: ${{ always() && inputs.deploy_hfs }}" in promotion_gate
    assert "PROFILE: ${{ inputs.evidence_profile }}" in promotion_gate
    assert "deployment requires the server-bundle release matrix to be skipped" in promotion_gate
    assert "release requires the four-server-bundle matrix to succeed" in promotion_gate
    for gate in (
        "validate",
        "ci",
        "source",
        "external",
        "package",
        "clean-install",
        "container",
        "server-bundles",
    ):
        assert gate in promotion_gate
    assert "needs: [validate, promotion-gate]" in hfs
    assert "if: ${{ always() && inputs.deploy_hfs" in hfs
    assert "needs.promotion-gate.result == 'success'" in hfs
    assert "secrets: inherit" in hfs


def test_promotion_gate_descendants_always_run_to_observe_skipped_parents() -> None:
    graph = _release_candidate_job_graph(_workflow("release-candidate.yml"))

    assert graph["promotion-gate"]["needs"] == [
        "validate",
        "ci",
        "source",
        "external",
        "server-bundles",
        "package",
        "clean-install",
        "container",
    ]
    # Deployment deliberately skips the release Server bundle matrix. It must stay an
    # ordinary parents so promotion-gate can explicitly verify that contract.
    assert graph["server-bundles"]["condition"] == "${{ inputs.evidence_profile == 'release' }}"

    downstream = _downstream_jobs(graph, "promotion-gate")
    assert downstream == {"hfs", "assemble-deployment", "assemble", "publish"}
    for job_id in downstream:
        assert "always()" in graph[job_id]["condition"], (
            f"{job_id} must use always() so it can observe skipped/failing promotion parents"
        )


def test_deployment_evidence_is_non_publishable_and_contains_no_release_binaries() -> None:
    text = _workflow("release-candidate.yml")
    deployment = _job(text, "assemble-deployment", "assemble")
    release = _job(text, "assemble", "publish")
    publish = text.split("\n  publish:\n", maxsplit=1)[1]

    assert "inputs.evidence_profile == 'deployment'" in deployment
    assert "deployment-manifest.json" in deployment
    assert "deployment-evidence.tar.gz" in deployment
    assert "deployment-evidence-${{ needs.validate.outputs.version }}" in deployment
    assert "'evidence_profile': 'deployment'" in deployment
    assert "'publishable': False" in deployment
    assert "'binary_count': 0" in deployment
    assert "'status': 'NOT_RUN'" in deployment
    assert "server-bundle release matrix skipped" in deployment
    assert "deployment evidence is missing required reports" in deployment
    assert "actions/attest-build-provenance@v4" in deployment
    assert "pattern: hf-space-local-*-report" in deployment
    assert "name: hfs-delivery-contracts-report" in deployment
    assert "name: provider-runtime-report" in text
    assert "runtime-profile-full-report" not in text
    assert "souwen-local-pyinstaller-cli" not in deployment
    for release_binary_pattern in (
        "pattern: souwen-linux-*",
        "pattern: souwen-macos-*",
        "pattern: souwen-windows-*",
        "pattern: souwen-nuitka-*",
        "pattern: binary-smoke-*",
    ):
        assert release_binary_pattern not in deployment

    assert "inputs.evidence_profile == 'release'" in release
    assert "if len(actual) != 4:" in release
    assert "'evidence_profile': 'release'" in release
    assert "'publishable': os.environ['PUBLISH'] == 'true'" in release
    assert "release-manifest.json" in release
    assert "'sdk_contract'" in release
    assert "mcp_edition" not in text
    assert "'product_name': os.environ['PRODUCT_NAME']" in release
    assert "'version': os.environ['VERSION']" in release
    assert "'api_major': int(os.environ['API_MAJOR'])" in release
    assert "name: release-candidate-${{ needs.validate.outputs.version }}" in release
    assert "needs: [validate, assemble]" in publish
    assert "RC2 publication remains disabled until Phase 8" in text
    assert "deployment-evidence-" not in publish
    assert "deployment-manifest.json" not in publish


def test_deployment_manifest_builder_emits_bounded_non_release_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    text = _workflow("release-candidate.yml")
    deployment = _job(text, "assemble-deployment", "assemble")
    manifest_step = deployment.split("- name: Write deployment manifest and checksums", maxsplit=1)[
        1
    ]
    manifest_source = _python_heredoc(manifest_step)
    checksum_source = _python_heredoc(manifest_step, 1)

    candidate = "a" * 40
    verifier = "b" * 40
    promoted = "c" * 40
    prior_wrapper = "d" * 40
    prior_source = "e" * 40
    evidence_root = tmp_path / "deployment-evidence"
    container_root = evidence_root / "container"
    container_root.mkdir(parents=True)
    for kind in ("root", "hfs", "modelscope"):
        (container_root / f"container-{kind}.json").write_text(
            json.dumps(
                {
                    "kind": kind,
                    "candidate_sha": candidate,
                    "image_digest": f"sha256:{kind}",
                }
            ),
            encoding="utf-8",
        )
    hfs_local = evidence_root / "hfs-local"
    hfs_local.mkdir()
    for name in (
        "hfs-delivery-contracts.json",
        "hf-space-local-pyinstaller.json",
        "hf-space-local-surface-report.json",
    ):
        (hfs_local / name).write_text("{}\n", encoding="utf-8")
    hfs_live = evidence_root / "hfs"
    hfs_live.mkdir()
    report_environment = {
        "expected_source_sha": candidate,
        "expected_wrapper_sha": promoted,
        "require_target_runtime": True,
    }
    (hfs_live / "hf-space-cd-surface-report.json").write_text(
        json.dumps({"overall": "PASS", "environment": report_environment, "checks": []}),
        encoding="utf-8",
    )
    target_checks = [
        "basic/health",
        "basic/readiness",
        "target-m1/openalex-search",
        "target-m1/builtin-fetch",
        "target-m1/browser-fetch",
    ]
    capability_payload = {
        "overall": "PASS",
        "environment": report_environment,
        "checks": [{"name": name, "outcome": "PASS"} for name in target_checks],
    }
    capability_path = hfs_live / "hf-space-cd-capability-report.json"
    capability_path.write_text(
        json.dumps(capability_payload),
        encoding="utf-8",
    )
    deployment_assets = tmp_path / "deployment-assets"
    deployment_assets.mkdir()
    (deployment_assets / "deployment-evidence.tar.gz").write_bytes(b"fixture archive")

    needs = {
        job_id: {"result": "success"}
        for job_id in (
            "validate",
            "ci",
            "source",
            "external",
            "package",
            "clean-install",
            "container",
            "hfs",
        )
    }
    needs.update(
        {
            "server-bundles": {"result": "skipped"},
        }
    )
    environment = {
        "CANDIDATE_SHA": candidate,
        "VERSION": "2.0.0rc2",
        "PRODUCT_NAME": "Souwen v2rc2",
        "API_MAJOR": "2",
        "EVIDENCE_PROFILE": "deployment",
        "NEEDS_JSON": json.dumps(needs),
        "VERIFIER_SHA": verifier,
        "RUN_URL": "https://github.example/actions/runs/1",
        "HFS_SPACE_COMMIT_SHA": promoted,
        "HFS_PROMOTION_CHANGED": "true",
        "HFS_PRIOR_SPACE_COMMIT_SHA": prior_wrapper,
        "HFS_PRIOR_RUNTIME_COMMIT_SHA": prior_wrapper,
        "HFS_PRIOR_SOUWEN_REF": prior_source,
        "HFS_PRIOR_RUNTIME_STAGE": "RUNNING",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.chdir(tmp_path)

    exec(compile(manifest_source, "release-candidate.yml:deployment-manifest", "exec"), {})
    exec(compile(checksum_source, "release-candidate.yml:deployment-checksums", "exec"), {})

    manifest = json.loads(
        (deployment_assets / "deployment-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["evidence_profile"] == "deployment"
    assert manifest["publishable"] is False
    assert manifest["product_name"] == "Souwen v2rc2"
    assert manifest["version"] == "2.0.0rc2"
    assert manifest["api_major"] == 2
    assert any(gate["id"] == "hfs_target_m1" for gate in manifest["gates"])
    assert manifest["binary_count"] == 0
    binary_gates = {
        item["id"]: item for item in manifest["gates"] if item["id"] == "server-bundles"
    }
    assert set(binary_gates) == {"server-bundles"}
    assert all(item["status"] == "NOT_RUN" for item in binary_gates.values())
    assert all(item["required"] is False for item in binary_gates.values())
    assert manifest["candidate_sha"] == candidate
    assert manifest["verifier_sha"] == verifier
    assert manifest["hfs"]["repo_sha"] == promoted
    assert manifest["hfs"]["runtime_sha"] == promoted
    assert {item["surface"] for item in manifest["containers"]} == {
        "root",
        "hfs",
        "modelscope",
    }
    assert not any(
        item["path"].startswith(
            (
                "souwen-server-",
                "souwen-linux-",
                "souwen-macos-",
                "souwen-windows-",
                "souwen-nuitka-",
            )
        )
        for item in manifest["evidence_files"]
    )
    assert {path.name for path in deployment_assets.iterdir()} == {
        "deployment-manifest.json",
        "deployment-evidence.tar.gz",
        "SHA256SUMS",
    }

    capability_payload["checks"][-1]["outcome"] = "FAIL"
    capability_path.write_text(json.dumps(capability_payload), encoding="utf-8")
    with pytest.raises(SystemExit, match="target M1 checks"):
        exec(compile(manifest_source, "release-candidate.yml:m1-failed", "exec"), {})
    capability_payload["checks"][-1]["outcome"] = "PASS"
    capability_path.write_text(json.dumps(capability_payload), encoding="utf-8")

    capability_path.unlink()
    with pytest.raises(SystemExit, match="missing required reports"):
        exec(compile(manifest_source, "release-candidate.yml:missing-report", "exec"), {})


def test_release_manifest_builder_accepts_only_exact_four_server_bundle_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    text = _workflow("release-candidate.yml")
    release = _job(text, "assemble", "publish")
    manifest_step = release.split(
        "- name: Verify four Server bundles and write release manifest", maxsplit=1
    )[1]
    manifest_source = _python_heredoc(manifest_step)
    checksum_source = _python_heredoc(manifest_step, 1)

    candidate = "a" * 40
    verifier = "b" * 40
    assets = tmp_path / "release-assets"
    evidence = tmp_path / "release-evidence"
    bundle_evidence = evidence / "server-bundles"
    bundle_evidence.mkdir(parents=True)
    assets.mkdir()
    expected = {
        "linux-amd64": "souwen-server-2.0.0rc2-linux-amd64.tar.gz",
        "linux-arm64": "souwen-server-2.0.0rc2-linux-arm64.tar.gz",
        "macos-arm64": "souwen-server-2.0.0rc2-macos-arm64.tar.gz",
        "windows-amd64": "souwen-server-2.0.0rc2-windows-amd64.zip",
    }
    required_checks = (
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
    )
    openapi = assets / "souwen-openapi-2.0.0rc2.json"
    openapi.write_bytes(b'{"info":{"version":"2.0.0rc2"}}')
    openapi_sha256 = hashlib.sha256(openapi.read_bytes()).hexdigest()
    bundles = []
    for platform, name in expected.items():
        path = assets / name
        path.write_bytes(f"bundle:{platform}".encode())
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        report_name = f"server-bundle-smoke-{platform}.json"
        (bundle_evidence / report_name).write_text(
            json.dumps(
                {
                    "overall": "PASS",
                    "target_native": True,
                    "archive": name,
                    "archive_sha256": digest,
                    "candidate_sha": candidate,
                    "checks": [{"name": check, "status": "PASS"} for check in required_checks],
                }
            ),
            encoding="utf-8",
        )
        bundles.append(
            {
                "name": name,
                "platform": platform,
                "size": path.stat().st_size,
                "sha256": digest,
                "candidate_sha": candidate,
                "api_major": 2,
                "openapi_sha256": openapi_sha256,
                "target_native": True,
                "smoke_overall": "PASS",
                "smoke_report": report_name,
            }
        )
    (bundle_evidence / "server-bundle-inventory.json").write_text(
        json.dumps(
            {
                "version": "2.0.0rc2",
                "candidate_sha": candidate,
                "verifier_sha": verifier,
                "workflow_identity": ".github/workflows/build-pyinstaller-server.yml",
                "api_major": 2,
                "openapi_sha256": openapi_sha256,
                "binary_count": 4,
                "bundles": bundles,
            }
        ),
        encoding="utf-8",
    )
    for name, payload in (
        ("souwen-2.0.0rc2-py3-none-any.whl", b"wheel"),
        ("souwen-2.0.0rc2.tar.gz", b"sdist"),
        ("python-sbom.cdx.json", b"{}"),
        ("panel-sbom.cdx.json", b"{}"),
        ("release-evidence.tar.gz", b"evidence"),
    ):
        (assets / name).write_bytes(payload)
    for kind in ("root", "hfs", "modelscope"):
        (evidence / f"container-{kind}.json").write_text(
            json.dumps(
                {
                    "kind": kind,
                    "candidate_sha": candidate,
                    "image_digest": f"sha256:{kind}",
                }
            ),
            encoding="utf-8",
        )

    needs = {
        job_id: {"result": "success"}
        for job_id in (
            "validate",
            "ci",
            "source",
            "external",
            "server-bundles",
            "package",
            "clean-install",
            "container",
        )
    }
    needs["hfs"] = {"result": "skipped"}
    environment = {
        "CANDIDATE_SHA": candidate,
        "VERSION": "2.0.0rc2",
        "PRODUCT_NAME": "Souwen v2rc2",
        "API_MAJOR": "2",
        "TAG": "v2.0.0rc2",
        "PUBLISH": "false",
        "DEPLOY_HFS": "false",
        "NEEDS_JSON": json.dumps(needs),
        "VERIFIER_SHA": verifier,
        "RUN_URL": "https://github.example/actions/runs/2",
        "HFS_SPACE_COMMIT_SHA": "",
        "HFS_PROMOTION_CHANGED": "",
        "HFS_PRIOR_SPACE_COMMIT_SHA": "",
        "HFS_PRIOR_RUNTIME_COMMIT_SHA": "",
        "HFS_PRIOR_SOUWEN_REF": "",
        "HFS_PRIOR_RUNTIME_STAGE": "",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.chdir(tmp_path)

    exec(compile(manifest_source, "release-candidate.yml:release-manifest", "exec"), {})
    exec(compile(checksum_source, "release-candidate.yml:release-checksums", "exec"), {})

    manifest = json.loads((assets / "release-manifest.json").read_text(encoding="utf-8"))
    assert manifest["evidence_profile"] == "release"
    assert manifest["publishable"] is False
    assert manifest["binary_count"] == 4
    server_assets = [item for item in manifest["artifacts"] if item["kind"] == "server_bundle"]
    assert {item["name"] for item in server_assets} == set(expected.values())
    assert all(item["target_native_smoke"] for item in server_assets)
    assert {path.name for path in assets.iterdir()} == {
        *(item["name"] for item in manifest["artifacts"]),
        "release-manifest.json",
        "SHA256SUMS",
    }

    failed_report = bundle_evidence / "server-bundle-smoke-windows-amd64.json"
    failed_payload = json.loads(failed_report.read_text(encoding="utf-8"))
    failed_payload["checks"][-1]["status"] = "FAIL"
    failed_report.write_text(json.dumps(failed_payload), encoding="utf-8")
    with pytest.raises(SystemExit, match="smoke evidence mismatch"):
        exec(compile(manifest_source, "release-candidate.yml:failed-smoke", "exec"), {})

    failed_payload["checks"][-1]["status"] = "PASS"
    failed_payload["checks"].append(dict(failed_payload["checks"][-1]))
    failed_report.write_text(json.dumps(failed_payload), encoding="utf-8")
    with pytest.raises(SystemExit, match="smoke evidence mismatch"):
        exec(compile(manifest_source, "release-candidate.yml:duplicate-smoke", "exec"), {})


def test_hfs_deployment_does_not_keep_a_retired_cli_binary_smoke() -> None:
    text = _workflow("deploy-hf-space.yml")
    assert "pyinstaller-cli" not in text
    assert "souwen-local-pyinstaller" not in text
    assert '- ".github/workflows/build-pyinstaller-server.yml"' in text
    assert '- ".github/workflows/build-pyinstaller.yml"' not in text
    assert "needs: [detect-changes, delivery-contracts, docker-hfs]" in text


def test_hfs_required_fetch_fixture_change_triggers_workflow() -> None:
    text = _workflow("deploy-hf-space.yml")

    assert '- "scripts/hf_space_smoke.py"' in text
    assert '- "scripts/fixtures/hf-space-fetch-probe.html"' in text
    assert '- "scripts/fixtures/hf-space-browser-probe.html"' in text


def test_hfs_m1_requires_target_supervisor_and_internal_worker_evidence() -> None:
    text = _workflow("deploy-hf-space.yml")

    assert "exec python /app/deploy/process/supervisor.py" in (
        REPO_ROOT / "cloud/hfs/entrypoint.sh"
    ).read_text(encoding="utf-8")
    assert "--require-target-runtime" in text
    assert "--expected-wrapper-sha" in text
    assert "SOUWEN_WRAPPER_SHA" in text
    assert 'key="SOUWEN_WRAPPER_SHA"' in text
    assert "curl -fsS http://127.0.0.1:49265/readyz" in text
    assert "docker port souwen-hfs-local 49266/tcp" in text
    sync = text.split("- name: Sync changed HFS wrapper files", maxsplit=1)[1].split(
        "  rebuild-space:", maxsplit=1
    )[0]
    assert sync.index('output.write(f"space_commit_sha={space_commit_sha}') < sync.index(
        "api.add_space_variable("
    )


def test_only_hfs_reusable_call_inherits_secrets() -> None:
    inherited = {
        path.name: path.read_text(encoding="utf-8").count("secrets: inherit")
        for path in WORKFLOW_DIR.glob("*.yml")
        if "secrets: inherit" in path.read_text(encoding="utf-8")
    }
    assert inherited == {"release-candidate.yml": 1}


def test_release_candidate_aggregates_all_release_gates() -> None:
    text = _workflow("release-candidate.yml")
    for call in (
        "uses: ./.github/workflows/v2-ci.yml",
        "uses: ./.github/workflows/external-smoke-gate.yml",
        "uses: ./.github/workflows/build-pyinstaller-server.yml",
        "uses: ./.github/workflows/deploy-hf-space.yml",
    ):
        assert call in text

    for gate in ("source", "external", "server-bundles", "clean-install", "container"):
        assert f"  {gate}:" in text
    assert "name: V2 source and Panel gates" in text
    assert "name: Broad CI, coverage, performance, audit, and container gates" in text
    assert "suite: release" in text

    external = text.split("  external:", maxsplit=1)[1].split("  server-bundles:", maxsplit=1)[0]
    assert "permissions:\n      contents: read\n      issues: write" in external

    container = text.split("  container:", maxsplit=1)[1].split("  hfs:", maxsplit=1)[0]
    assert "ref: ${{ needs.validate.outputs.candidate_sha }}\n          fetch-depth: 0" in container


def test_release_bundle_has_four_servers_openapi_supply_chain_assets_and_attestation() -> None:
    text = _workflow("release-candidate.yml")
    source = text.split("  source:", maxsplit=1)[1].split("  clean-install:", maxsplit=1)[0]
    assert "if len(actual) != 4:" in text
    assert "expected exactly four Server bundles" in text
    assert "souwen-openapi-2.0.0rc2.json" in text
    assert "Install built candidate for canonical OpenAPI verification" in source
    assert 'python -m pip install "${wheel}[server]"' in text
    assert "python tools/gen_openapi.py --check" in source
    assert "cp contracts/openapi/souwen-openapi-2.0.0rc2.json" in source
    assert "from souwen.server.app import app" not in source
    assert "app.openapi()" not in source
    assert "immutable OpenAPI checksum differs from Server bundle smoke" in text
    assert "release assets contain retired binary artifacts" in text
    assert "python-sbom.cdx.json" in text
    assert "panel-sbom.cdx.json" in text
    assert "release-manifest.json" in text
    assert "SHA256SUMS" in text
    assert "actions/attest-build-provenance@v4" in text
    assert "attestations: write" in text
    assert "id-token: write" in text
    assert "name: release-candidate-${{ needs.validate.outputs.version }}" in text
    assert "'bundle_envelope'" in text
    assert "SHA256SUMS must cover every asset except itself" in text
    assert "sha256sum -c SHA256SUMS" in text
    for manifest_field in (
        "'candidate_ref'",
        "'verifier_sha'",
        "'created_at'",
        "'remote_runs'",
        "'containers'",
        "'hfs'",
        "'exceptions'",
    ):
        assert manifest_field in text
    for hfs_evidence_field in (
        "'prior_repo_sha'",
        "'prior_runtime_sha'",
        "'prior_source_sha'",
        "'prior_runtime_stage'",
        "'promotion_changed'",
    ):
        assert hfs_evidence_field in text


def test_ci_has_stable_aggregate_and_required_readiness_gates() -> None:
    text = _workflow("ci.yml")
    assert "name: CI / aggregate" in text
    assert "name: V2 CI / v2 release readiness summary" in _workflow("v2-ci.yml")
    assert "--cov-fail-under=67" in text
    assert "--cov-fail-under=90" in text
    assert "name: Clean wheel (${{ matrix.profile }})" in text
    for profile in (
        "sdk-default",
        "server-runtime",
        "provider-newspaper",
        "provider-readability",
        "provider-crawl4ai",
        "provider-scrapling",
    ):
        assert f"profile: {profile}" in text
    assert "samples = []" in text
    assert "for _ in range(7):" in text
    assert "pip-audit --local" in text
    assert '"setuptools>=83"' in text
    assert "npm audit --omit=dev --audit-level=high --json" in text
    assert "pip-audit.json" in text
    assert "npm-audit.json" in text
    assert "--mode fixture" in text
    for threshold in ("1.50", "2.50"):
        assert threshold in text
    for dockerfile in ("Dockerfile", "cloud/hfs/Dockerfile", "cloud/modelscope/Dockerfile"):
        assert f"dockerfile: {dockerfile}" in text

    container = text.split("  container-surface:", maxsplit=1)[1].split("  aggregate:", maxsplit=1)[
        0
    ]
    candidate_expression = (
        "${{ inputs.candidate_sha || github.event.pull_request.head.sha || github.sha }}"
    )
    assert f"SOURCE_SHA: {candidate_expression}" in container
    assert f"ref: {candidate_expression}" in container
    assert "fetch-depth: 0" in container
    assert 'git push "$bare" HEAD:refs/heads/ci-candidate' in container


def test_ci_fast_lane_is_single_py313_ubuntu2404_and_full_lane_covers_release_and_tags() -> None:
    ci = _workflow("ci.yml")
    lane = _job(ci, "lane", "architecture")
    assert "full: ${{ steps.lane.outputs.full }}" in lane
    assert "test_matrix: ${{ steps.lane.outputs.test_matrix }}" in lane
    assert '"workflow_call"' in lane
    assert '"workflow_dispatch"' in lane
    assert "github.ref_type" in lane
    assert '{"include":[{"os":"ubuntu-24.04","python":"3.13"}]}' in lane
    assert '{"os":"macos-latest","python":"3.11"}' in lane
    assert '{"os":"windows-latest","python":"3.11"}' in lane

    test_job = _job(ci, "test", "server-test")
    assert "needs: [lane, lint]" in test_job
    assert "matrix: ${{ fromJSON(needs.lane.outputs.test_matrix) }}" in test_job

    gate = "if: needs.lane.outputs.full == 'true'"
    assert ci.count(gate) == 10
    for fast_job in ("architecture", "lint", "docs-check", "panel-build"):
        block = ci.split(f"  {fast_job}:", maxsplit=1)[1]
        assert gate not in block.split("\n  ", maxsplit=1)[0]

    aggregate = ci.split("  aggregate:", maxsplit=1)[1]
    assert "- lane" in aggregate.split("if: always()", maxsplit=1)[0]
    assert "FULL_LANE" in aggregate
    assert '. == "skipped"' in aggregate

    v2 = _workflow("v2-ci.yml")
    v2_lane = _job(v2, "lane", "bootstrap")
    assert "full: ${{ steps.lane.outputs.full }}" in v2_lane
    assert v2.count(gate) == 4
    for fast_job, next_job in (
        ("bootstrap", "matrix_tests"),
        ("provider_v2_conformance", "delivery_contracts"),
    ):
        assert gate not in _job(v2, fast_job, next_job)
    summary = v2.split("  release_readiness_summary:", maxsplit=1)[1]
    assert "FULL_LANE" in summary
    assert '"skipped"' in summary

    for name in ("ci.yml", "v2-ci.yml"):
        push = _workflow_trigger(_workflow(name), "push")
        assert "tags: ['v*']" in push


def test_architecture_dependency_gate_is_required_in_ci_and_release_paths() -> None:
    command = "python scripts/ci/check_architecture_dependencies.py"
    ci = _workflow("ci.yml")
    graph = _release_candidate_job_graph(ci)

    assert "architecture" in graph
    assert "architecture" in graph["aggregate"]["needs"]
    assert command in _job(ci, "architecture", "lint")
    ci_push = _workflow_trigger(ci, "push")
    assert "branches: [main]" in ci_push
    assert "tags: ['v*']" in ci_push
    assert "paths:" not in ci_push

    v2 = _workflow("v2-ci.yml")
    assert command in _job(v2, "bootstrap", "matrix_tests")

    release_candidate = _workflow("release-candidate.yml")
    assert "uses: ./.github/workflows/ci.yml" in release_candidate
    assert "uses: ./.github/workflows/v2-ci.yml" in release_candidate


def test_ruff_toolchain_version_is_pinned_consistently() -> None:
    version = "0.15.22"
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'"ruff=={version}"' in pyproject

    for workflow_name in ("ci.yml", "auto-format.yml"):
        workflow = _workflow(workflow_name)
        assert f'pip install "ruff=={version}"' in workflow
        assert "pip install ruff\n" not in workflow


def test_hfs_reusable_promotion_is_candidate_pinned_and_live_verified() -> None:
    text = _workflow("deploy-hf-space.yml")
    candidate_expression = (
        "${{ inputs.candidate_sha || github.event.pull_request.head.sha || github.sha }}"
    )
    contract_step = text.split("- name: Validate reusable candidate contract", maxsplit=1)[1].split(
        "- name: Detect deploy-related path changes", maxsplit=1
    )[0]
    assert "python3 -I - <<'PY'" in contract_step
    assert "python3 - <<'PY'" not in contract_step
    assert "workflow_call:" in text
    assert "candidate_sha:" in text
    assert "verifier_sha:" in text
    workflow_call = text.split("  workflow_call:", maxsplit=1)[1].split(
        "  pull_request:", maxsplit=1
    )[0]
    for secret_name in (
        "HF_TOKEN",
        "HF_SPACE_READ_TOKEN",
        "SOUWEN_SMOKE_BEARER_TOKEN",
    ):
        assert f"      {secret_name}:" not in workflow_call
    assert "    secrets:" not in workflow_call
    assert workflow_call.count("required: true") == 4
    assert text.count(candidate_expression) >= 10
    assert "${{ inputs.candidate_sha || github.sha }}" not in text
    assert 'expected_pin = f"ARG SOUWEN_REF={candidate_sha}"' in text
    assert 'last_runtime_sha = str(runtime.raw.get("sha") or "unknown")' in text
    assert "last_runtime_sha == expected_sha" in text
    assert "SOUWEN_SMOKE_BEARER_TOKEN is required for candidate promotion" in text
    assert "EXPECTED_SOUWEN_SOURCE_SHA" in text
    assert "'.role == \"admin\" and .admin_open == false'" in text
    assert "name: hf" in text
    assert "  push:" not in text.split("jobs:", maxsplit=1)[0]
    assert "target_info.private is not True" in text
    assert "unauth_status" in text
    assert "github.event_name == 'workflow_call'" not in text
    assert "if: ${{ inputs.deploy_hfs }}" in text
    assert 'write_output(True, "release-candidate")' in text
    assert "inputs.deploy_hfs && 'promotion'" in text
    assert "cancel-in-progress: ${{ !inputs.deploy_hfs }}" in text
    assert "prior_space_commit_sha" in text
    assert "prior_runtime_commit_sha" in text
    assert "prior_souwen_ref" in text
    assert "prior_runtime_stage" in text
    assert "parent_commit=prior_space_sha" in text
    assert "revision=prior_space_sha" in text
    assert "  rollback-space:" in text
    assert "needs.post-deploy-smoke.result != 'success'" in text
    assert "CommitOperationDelete" in text
    assert "rollback_space_commit_sha" in text
    assert "  pause-space:" in text
    assert "api.pause_space" in text
    assert "needs.rollback-space.result == 'cancelled'" in text
    assert "HF_SPACE_READ_TOKEN" in text
    assert '"X-SouWen-Token: $SOUWEN_SMOKE_BEARER_TOKEN"' in text

    secret_gate = text.split("- name: Require HFS deployment secrets", maxsplit=1)[1].split(
        "- uses: actions/checkout@v6", maxsplit=1
    )[0]
    for secret_name in (
        "HF_TOKEN",
        "HF_SPACE_READ_TOKEN",
        "SOUWEN_SMOKE_BEARER_TOKEN",
    ):
        assert f"{secret_name}: ${{{{ secrets.{secret_name} }}}}" in secret_gate
    assert "Required HFS environment secret is not configured: $name" in secret_gate
    assert "${!name}" in secret_gate

    prior = text.split("- name: Capture immutable rollback point", maxsplit=1)[1].split(
        "- name: Sync changed HFS wrapper files", maxsplit=1
    )[0]
    assert 'stage_upper.endswith("SLEEPING")' in prior
    assert '"PAUSED"' in prior
    assert "api.restart_space" not in prior

    rollback = text.split("  rollback-space:", maxsplit=1)[1].split("  pause-space:", maxsplit=1)[0]
    assert "rollback_sha = prior_sha" in rollback
    assert "Space head still matches the rollback point" in rollback
    assert "no distinct forward rollback commit" not in rollback
    assert 'if "wrapper_sha" in payload and payload["wrapper_sha"] != expected_wrapper:' in rollback

    post_deploy = text.split("  post-deploy-smoke:", maxsplit=1)[1].split(
        "  rollback-space:", maxsplit=1
    )[0]
    assert "ref: ${{ inputs.verifier_sha }}" in post_deploy
    assert "cd trusted-verifier" in post_deploy
    assert "ref: ${{ inputs.candidate_sha || github.sha }}" not in post_deploy


def test_hfs_rollback_probe_distinguishes_legacy_absent_wrapper_from_rc2_null_or_drift() -> None:
    text = _workflow("deploy-hf-space.yml")
    rollback = _job(text, "rollback-space", "pause-space")
    source = textwrap.dedent(
        rollback.split("<<'PY'", maxsplit=1)[1].split("\n          PY", maxsplit=1)[0]
    ).lstrip()
    module = ast.parse(source)
    function = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "validate_rollback_probe"
    )
    namespace: dict[str, object] = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "rollback-probe", "exec"), namespace)
    validate = namespace["validate_rollback_probe"]
    source_sha = "a" * 40
    wrapper_sha = "b" * 40

    validate({"source_sha": source_sha}, "/health", source_sha, wrapper_sha)
    validate(
        {"source_sha": source_sha, "wrapper_sha": wrapper_sha},
        "/health",
        source_sha,
        wrapper_sha,
    )
    with pytest.raises(SystemExit, match="wrapper mismatch"):
        validate(
            {"source_sha": source_sha, "wrapper_sha": None}, "/health", source_sha, wrapper_sha
        )
    with pytest.raises(SystemExit, match="wrapper mismatch"):
        validate(
            {"source_sha": source_sha, "wrapper_sha": "c" * 40},
            "/health",
            source_sha,
            wrapper_sha,
        )
    with pytest.raises(SystemExit, match="source mismatch"):
        validate({"source_sha": "c" * 40}, "/health", source_sha, wrapper_sha)


def test_hfs_rebuild_job_avoids_checkout_and_dependency_cache() -> None:
    text = _workflow("deploy-hf-space.yml")
    rebuild = text.split("  rebuild-space:", maxsplit=1)[1].split(
        "  post-deploy-smoke:", maxsplit=1
    )[0]

    assert "actions/setup-python@v6" in rebuild
    assert "actions/checkout@" not in rebuild
    assert "cache: pip" not in rebuild


def test_external_release_gate_no_longer_contains_plugin_runtime_fixture() -> None:
    text = _workflow("external-smoke-gate.yml")
    assert "Plugin and SuperWeb2PDF release/nightly gate" not in text
    assert "plugin_functional_check.py" not in text
    assert "examples/minimal-plugin" not in text
    assert "--timeout 45" in text
    assert "external-gate-plugin-report" not in text


def test_clean_wheel_composite_enforces_runtime_and_package_boundaries() -> None:
    text = (REPO_ROOT / ".github/actions/clean-wheel-smoke/action.yml").read_text(encoding="utf-8")
    for contract in (
        "package/panel",
        "package/no-retired-imports",
        "sdk/sync-client",
        "sdk/async-client",
        "sdk/api-major",
        "sdk/openapi-sha256",
        "sdk/no-fastapi",
        "server/import",
        "server/import-{module}",
        "variant/crawl4ai-only",
        "variant/scrapling-only",
    ):
        assert contract in text
    assert "souwen.editions" not in text
    assert "CLEAN_WHEEL_PROFILE" in text
    assert "from souwen import AsyncSouWenClient, SouWenClient" in text
    assert "from souwen.delivery.client_sdk import OPENAPI_SHA256, SUPPORTED_API_MAJOR" in text
