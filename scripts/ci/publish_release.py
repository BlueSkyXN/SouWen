"""发布携带已验证 Python 分发包的 GitHub Release。"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import quote


def _gh(*args: str) -> str:
    return subprocess.check_output(["gh", *args], text=True).strip()


def _api(path: str) -> dict:
    return json.loads(_gh("api", path))


def _verify_tag(repo: str, tag: str, commit: str) -> None:
    obj = _api(f"repos/{repo}/git/ref/tags/{quote(tag, safe='')}")["object"]
    while obj["type"] == "tag":
        obj = _api(f"repos/{repo}/git/tags/{obj['sha']}")["object"]
    if obj["type"] != "commit" or obj["sha"] != commit:
        raise RuntimeError(f"标签 {tag} 应指向已验证的提交 {commit}")


def _find_release(repo: str, tag: str) -> dict | None:
    pages = json.loads(_gh("api", "--paginate", "--slurp", f"repos/{repo}/releases?per_page=100"))
    releases = [release for page in pages for release in page if release["tag_name"] == tag]
    if len(releases) > 1:
        raise RuntimeError(f"标签 {tag} 有多个 Release，请检查 GitHub 上的发布记录")
    return releases[0] if releases else None


def _missing_assets(release: dict, files: list[Path], prerelease: bool) -> list[Path]:
    if release["prerelease"] != prerelease:
        raise RuntimeError("GitHub Release 的预发行状态与包版本不匹配")
    missing = {file.name: file for file in files}
    for asset in release["assets"]:
        name = asset["name"]
        file = missing.pop(name, None)
        if file is None:
            raise RuntimeError(f"GitHub Release 存在意外的附件 {name}")
        digest = "sha256:" + hashlib.sha256(file.read_bytes()).hexdigest()
        if (
            asset["state"] != "uploaded"
            or asset["size"] != file.stat().st_size
            or asset.get("digest") != digest
        ):
            raise RuntimeError(f"GitHub Release 的附件 {name} 与已验证的构建产物不一致")
    return list(missing.values())


def publish(repo: str, tag: str, commit: str, prerelease: bool, directory: Path) -> str:
    _verify_tag(repo, tag, commit)
    version = tag.removeprefix("v")
    files = [
        directory / f"souwen-{version}-py3-none-any.whl",
        directory / f"souwen-{version}.tar.gz",
        directory / "SHA256SUMS",
    ]
    for file in files:
        if not file.is_file() or file.stat().st_size == 0:
            raise RuntimeError(f"缺少发布附件 {file.name}，请检查打包任务")

    flags = ["--prerelease", "--latest=false"] if prerelease else []
    release = _find_release(repo, tag)
    if release is None:
        _gh(
            "release",
            "create",
            tag,
            *map(str, files),
            "--repo",
            repo,
            "--verify-tag",
            "--target",
            commit,
            "--draft",
            "--title",
            f"SouWen {tag}",
            "--notes-from-tag",
            *flags,
        )
        release_id = _gh(
            "release", "view", tag, "--repo", repo, "--json", "databaseId", "--jq", ".databaseId"
        )
        release = _api(f"repos/{repo}/releases/{release_id}")

    path = f"repos/{repo}/releases/{release['id']}"
    missing = _missing_assets(release, files, prerelease)
    if release["draft"]:
        if missing:
            _gh("release", "upload", tag, *map(str, missing), "--repo", repo)
            release = _api(path)
        if _missing_assets(release, files, prerelease):
            raise RuntimeError("发布草稿的附件不完整，请重跑发布任务")
        _verify_tag(repo, tag, commit)
        _gh("release", "edit", tag, "--repo", repo, "--verify-tag", "--draft=false", *flags)
        release = _api(path)

    if (
        release["tag_name"] != tag
        or release["draft"]
        or _missing_assets(release, files, prerelease)
    ):
        raise RuntimeError(f"GitHub Release {tag} 的发布状态或附件不完整")
    return release["html_url"]


if __name__ == "__main__":
    print(
        publish(
            os.environ["GH_REPO"],
            os.environ["GITHUB_REF_NAME"],
            os.environ["RELEASE_SHA"],
            os.environ["RELEASE_PRERELEASE"] == "true",
            Path("dist"),
        )
    )
