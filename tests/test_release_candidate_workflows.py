from __future__ import annotations

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
    assert text.index("git', 'merge-base', '--is-ancestor'") < text.index(
        'pip install -e ".[edition-pro]"'
    )
    assert "release-candidate must run from the current origin/main control plane" in text
    assert "candidate_sha to equal the current origin/main" in text
    assert "verifier_sha" in text
    assert text.count("secrets: inherit") == 1
    hfs_call = _job(text, "hfs", "assemble-deployment")
    assert "uses: ./.github/workflows/deploy-hf-space.yml" in hfs_call
    assert "secrets: inherit" in hfs_call


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


def test_deployment_profile_skips_release_binary_matrices_and_gates_hfs() -> None:
    text = _workflow("release-candidate.yml")
    pyinstaller = _job(text, "pyinstaller", "nuitka")
    nuitka = _job(text, "nuitka", "package")
    promotion_gate = _job(text, "promotion-gate", "hfs")
    hfs = _job(text, "hfs", "assemble-deployment")

    release_only = "if: ${{ inputs.evidence_profile == 'release' }}"
    assert release_only in pyinstaller
    assert release_only in nuitka
    assert "if: ${{ always() && inputs.deploy_hfs }}" in promotion_gate
    assert "PROFILE: ${{ inputs.evidence_profile }}" in promotion_gate
    assert "deployment requires skipped binary release matrices" in promotion_gate
    assert "release requires successful binary release matrices" in promotion_gate
    for gate in (
        "validate",
        "ci",
        "source",
        "external",
        "package",
        "clean-install",
        "container",
        "pyinstaller",
        "nuitka",
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
        "pyinstaller",
        "nuitka",
        "package",
        "clean-install",
        "container",
    ]
    # Deployment deliberately skips both release binary matrices. They must stay
    # ordinary parents so promotion-gate can explicitly verify that contract.
    for binary_job in ("pyinstaller", "nuitka"):
        assert graph[binary_job]["condition"] == "${{ inputs.evidence_profile == 'release' }}"

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
    assert "release binary matrix skipped" in deployment
    assert "deployment evidence is missing required reports" in deployment
    assert "actions/attest-build-provenance@v4" in deployment
    assert "pattern: hf-space-local-*-report" in deployment
    assert "name: api-source-cli-profile-report" in deployment
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
    assert "if len(actual) != 24:" in release
    assert "release-manifest.json" in release
    assert "name: release-candidate-${{ needs.validate.outputs.version }}" in release
    assert "needs: [validate, assemble]" in publish
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
        "api-source-cli-profile.json",
        "hf-space-local-pyinstaller.json",
        "hf-space-local-surface-report.json",
    ):
        (hfs_local / name).write_text("{}\n", encoding="utf-8")
    hfs_live = evidence_root / "hfs"
    hfs_live.mkdir()
    for name in (
        "hf-space-cd-surface-report.json",
        "hf-space-cd-capability-report.json",
    ):
        (hfs_live / name).write_text("{}\n", encoding="utf-8")
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
            "pyinstaller": {"result": "skipped"},
            "nuitka": {"result": "skipped"},
        }
    )
    environment = {
        "CANDIDATE_SHA": candidate,
        "VERSION": "2.0.0rc1",
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
    assert manifest["binary_count"] == 0
    binary_gates = {
        item["id"]: item for item in manifest["gates"] if item["id"] in {"pyinstaller", "nuitka"}
    }
    assert set(binary_gates) == {"pyinstaller", "nuitka"}
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
            ("souwen-linux-", "souwen-macos-", "souwen-windows-", "souwen-nuitka-")
        )
        for item in manifest["evidence_files"]
    )
    assert {path.name for path in deployment_assets.iterdir()} == {
        "deployment-manifest.json",
        "deployment-evidence.tar.gz",
        "SHA256SUMS",
    }

    (hfs_live / "hf-space-cd-capability-report.json").unlink()
    with pytest.raises(SystemExit, match="missing required reports"):
        exec(compile(manifest_source, "release-candidate.yml:missing-report", "exec"), {})


def test_hfs_deployment_keeps_one_basic_pyinstaller_smoke() -> None:
    text = _workflow("deploy-hf-space.yml")
    pyinstaller = _job(text, "pyinstaller-cli", "docker-hfs")

    assert "name: PyInstaller CLI smoke" in pyinstaller
    assert 'pip install -e ".[edition-basic]"' in pyinstaller
    assert "profile: basic-cli" in pyinstaller
    assert "builder: pyinstaller" in pyinstaller


def test_hfs_required_fetch_fixture_change_triggers_workflow() -> None:
    text = _workflow("deploy-hf-space.yml")

    assert '- "scripts/hf_space_smoke.py"' in text
    assert '- "scripts/fixtures/hf-space-fetch-probe.html"' in text


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
        "uses: ./.github/workflows/build-pyinstaller.yml",
        "uses: ./.github/workflows/build-nuitka.yml",
        "uses: ./.github/workflows/deploy-hf-space.yml",
    ):
        assert call in text

    for gate in ("source", "external", "pyinstaller", "nuitka", "clean-install", "container"):
        assert f"  {gate}:" in text
    assert "name: V2 source and Panel gates" in text
    assert "name: Broad CI, coverage, performance, audit, and container gates" in text
    assert "suite: release" in text

    external = text.split("  external:", maxsplit=1)[1].split("  pyinstaller:", maxsplit=1)[0]
    assert "permissions:\n      contents: read\n      issues: write" in external

    container = text.split("  container:", maxsplit=1)[1].split("  hfs:", maxsplit=1)[0]
    assert "ref: ${{ needs.validate.outputs.candidate_sha }}\n          fetch-depth: 0" in container


def test_release_bundle_has_24_binaries_supply_chain_assets_and_attestation() -> None:
    text = _workflow("release-candidate.yml")
    assert "if len(actual) != 24:" in text
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


def test_binary_smoke_preserves_help_tracebacks_for_cross_platform_diagnostics() -> None:
    text = (REPO_ROOT / ".github/actions/binary-smoke/action.yml").read_text(encoding="utf-8")
    assert 'if name == "cli/help" and len(detail) > 4000:' in text
    assert "... traceback middle omitted ..." in text
    assert 'detail = f"{detail[:750]}\\n' in text
    assert '{detail[-3200:]}"' in text


def test_ci_has_stable_aggregate_and_required_readiness_gates() -> None:
    text = _workflow("ci.yml")
    assert "name: CI / aggregate" in text
    assert "name: V2 CI / v2 release readiness summary" in _workflow("v2-ci.yml")
    assert "--cov-fail-under=67" in text
    assert "--cov-fail-under=90" in text
    assert "name: Clean wheel (${{ matrix.extra }})" in text
    for extra in (
        "edition-basic",
        "edition-pro",
        "edition-full",
        "edition-full-crawl4ai",
        "edition-full-scrapling",
    ):
        assert f"extra: {extra}" in text
    assert "samples = []" in text
    assert "for _ in range(7):" in text
    assert "pip-audit --local" in text
    assert '"setuptools>=83"' in text
    assert "npm audit --omit=dev --audit-level=high --json" in text
    assert "pip-audit.json" in text
    assert "npm-audit.json" in text
    assert "--mode fixture" in text
    for threshold in ("1.50", "2.00", "2.50"):
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

    post_deploy = text.split("  post-deploy-smoke:", maxsplit=1)[1].split(
        "  rollback-space:", maxsplit=1
    )[0]
    assert "ref: ${{ inputs.verifier_sha }}" in post_deploy
    assert "cd trusted-verifier" in post_deploy
    assert "ref: ${{ inputs.candidate_sha || github.sha }}" not in post_deploy


def test_hfs_rebuild_job_avoids_checkout_and_dependency_cache() -> None:
    text = _workflow("deploy-hf-space.yml")
    rebuild = text.split("  rebuild-space:", maxsplit=1)[1].split(
        "  post-deploy-smoke:", maxsplit=1
    )[0]

    assert "actions/setup-python@v6" in rebuild
    assert "actions/checkout@" not in rebuild
    assert "cache: pip" not in rebuild


def test_external_release_gate_requires_superweb2pdf_runtime_fixture() -> None:
    text = _workflow("external-smoke-gate.yml")
    assert "Plugin and SuperWeb2PDF release/nightly gate" in text
    assert 'pip install -e ".[dev,edition-full]"' in text
    assert "python -m playwright install --with-deps chromium" in text
    assert "--require-web2pdf-runtime" in text
    assert "--timeout 45" in text
    assert "external-gate-plugin-report" in text


def test_superweb2pdf_workflow_install_is_commit_and_hash_pinned() -> None:
    text = _workflow("ci.yml")
    assert (
        "d1e1da59d739ad46222b5e726bd6f28b0d0453fa.zip"
        "#sha256=f56a380aa3f06d169d3fcc723d5525779519afaff159b37e8a789e50b797c76b"
    ) in text
    assert 'd1e1da59d739ad46222b5e726bd6f28b0d0453fa.zip"' not in text


def test_clean_wheel_composite_enforces_edition_and_package_boundaries() -> None:
    text = (REPO_ROOT / ".github/actions/clean-wheel-smoke/action.yml").read_text(encoding="utf-8")
    for contract in (
        "package/panel",
        "package/no-retired-imports",
        "runtime/mcp-stdio-server",
        "basic/no-fastapi",
        "basic/three-fetch-providers",
        "basic/llm-gated",
        "pro/server-import",
        "full/import-pymupdf4llm",
        "full/import-superweb2pdf",
        "variant/crawl4ai-only",
        "variant/scrapling-only",
        "expected_missing_fetch_providers",
    ):
        assert contract in text
