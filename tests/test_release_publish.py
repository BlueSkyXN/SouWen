"""验证发布任务对标签和已有附件的处理。"""

from __future__ import annotations

import hashlib
from unittest.mock import Mock, call

import pytest

from scripts.ci import publish_release


REPO = "example/SouWen"
TAG = "v3.0.0a3"
COMMIT = "1" * 40
RELEASE_URL = f"https://github.com/{REPO}/releases/tag/{TAG}"


@pytest.fixture
def files(tmp_path):
    names = ["souwen-3.0.0a3-py3-none-any.whl", "souwen-3.0.0a3.tar.gz", "SHA256SUMS"]
    paths = [tmp_path / name for name in names]
    for path in paths:
        path.write_text(path.name, encoding="utf-8")
    return paths


def _release(files, *, draft):
    return {
        "id": 123,
        "tag_name": TAG,
        "draft": draft,
        "prerelease": True,
        "html_url": RELEASE_URL,
        "assets": [
            {
                "name": path.name,
                "state": "uploaded",
                "size": path.stat().st_size,
                "digest": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in files
        ],
    }


def test_tag_must_point_to_the_built_commit(monkeypatch, files):
    tag_object = {"object": {"type": "tag", "sha": "2" * 40}}
    other_commit = {"object": {"type": "commit", "sha": "3" * 40}}
    api = Mock(side_effect=[tag_object, other_commit])
    gh = Mock()
    monkeypatch.setattr(publish_release, "_api", api)
    monkeypatch.setattr(publish_release, "_gh", gh)

    with pytest.raises(RuntimeError, match="应指向已验证的提交"):
        publish_release.publish(REPO, TAG, COMMIT, True, files[0].parent)

    assert api.call_args_list == [
        call(f"repos/{REPO}/git/ref/tags/{TAG}"),
        call(f"repos/{REPO}/git/tags/{'2' * 40}"),
    ]
    gh.assert_not_called()


def test_draft_resume_uploads_missing_asset_before_publication(monkeypatch, files):
    gh = Mock()
    verify_tag = Mock()
    api = Mock(side_effect=[_release(files, draft=True), _release(files, draft=False)])
    monkeypatch.setattr(publish_release, "_gh", gh)
    monkeypatch.setattr(publish_release, "_api", api)
    monkeypatch.setattr(publish_release, "_verify_tag", verify_tag)
    monkeypatch.setattr(
        publish_release, "_find_release", lambda *_: _release(files[:2], draft=True)
    )

    assert publish_release.publish(REPO, TAG, COMMIT, True, files[0].parent) == RELEASE_URL

    assert gh.call_args_list == [
        call("release", "upload", TAG, str(files[2]), "--repo", REPO),
        call(
            "release",
            "edit",
            TAG,
            "--repo",
            REPO,
            "--verify-tag",
            "--draft=false",
            "--prerelease",
            "--latest=false",
        ),
    ]
    assert verify_tag.call_args_list == [call(REPO, TAG, COMMIT)] * 2


@pytest.mark.parametrize("status", ["complete", "missing", "wrong-digest"])
def test_existing_published_release_is_read_only(monkeypatch, files, status):
    release = _release(files, draft=False)
    if status == "missing":
        release["assets"].pop()
    if status == "wrong-digest":
        release["assets"][0]["digest"] = "sha256:" + "0" * 64
    gh = Mock()
    monkeypatch.setattr(publish_release, "_gh", gh)
    monkeypatch.setattr(publish_release, "_verify_tag", Mock())
    monkeypatch.setattr(publish_release, "_find_release", lambda *_: release)

    if status == "complete":
        assert publish_release.publish(REPO, TAG, COMMIT, True, files[0].parent) == RELEASE_URL
    else:
        with pytest.raises(RuntimeError, match="附件"):
            publish_release.publish(REPO, TAG, COMMIT, True, files[0].parent)
    gh.assert_not_called()
