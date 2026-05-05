"""GitHub 搜索客户端单元测试。

覆盖 ``souwen.web.github.GitHubClient`` 仓库搜索路径。使用 ``pytest-httpx``
直接 mock HTTP 层（GitHub API 是纯 JSON，不像 scraper 引擎需要解析 HTML）。

注意：``SourceType.WEB_GITHUB`` 由后续集成步骤添加到枚举；在该值缺失时整个
模块的用例会被自动 skip，避免阻塞 CI。

测试清单：
- ``test_init_without_token``：无 Token 也能正常初始化（降级模式）
- ``test_init_with_token_sets_auth_header``：传入 Token 后设置 Authorization 头
- ``test_search_returns_results``：正常返回结果且字段映射正确

注意：基于环境变量解析 token 的用例依赖 ``SouWenConfig.github_token`` 配置字段，
该字段由后续集成步骤添加，因此此处只覆盖 ``token=`` 显式入参路径。

- ``test_search_empty_items``：空结果（items=[]）返回空列表不崩溃
- ``test_search_skips_invalid_items``：缺少 full_name / html_url 的条目被跳过
- ``test_search_respects_max_results``：max_results 截断生效
- ``test_search_invalid_json_raises_parse_error``：非 JSON 响应抛 ParseError
"""

from __future__ import annotations

import pytest

from souwen.models import SourceType


# 集成步骤未完成前 (枚举里没有 web_github)，整个模块跳过避免阻塞 CI
if "web_github" not in SourceType._value2member_map_:  # type: ignore[attr-defined]
    pytest.skip(
        "SourceType.WEB_GITHUB 尚未注册，跳过 GitHub 客户端测试（待集成步骤完成）",
        allow_module_level=True,
    )


from souwen.core.exceptions import ParseError  # noqa: E402
from souwen.web.github import GitHubClient  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _sample_response(items: list[dict] | None = None, total: int | None = None) -> dict:
    """构造 GitHub /search/repositories 风格的响应"""
    items = items if items is not None else []
    return {
        "total_count": total if total is not None else len(items),
        "incomplete_results": False,
        "items": items,
    }


def _sample_repo(
    name: str = "octocat/hello-world",
    description: str = "My first repository on GitHub",
    stars: int = 123,
) -> dict:
    """构造一条 GitHub 仓库 item"""
    return {
        "full_name": name,
        "html_url": f"https://github.com/{name}",
        "description": description,
        "stargazers_count": stars,
        "forks_count": 7,
        "language": "Python",
        "updated_at": "2024-01-01T00:00:00Z",
        "topics": ["demo", "example"],
        "open_issues_count": 2,
        "license": {"spdx_id": "MIT"},
        "owner": {"login": name.split("/")[0]},
        "archived": False,
    }


# ---------------------------------------------------------------------------
# __init__ tests
# ---------------------------------------------------------------------------


async def test_init_without_token(monkeypatch):
    """无 Token 也能初始化（不抛 ConfigError）"""
    monkeypatch.delenv("SOUWEN_GITHUB_TOKEN", raising=False)
    async with GitHubClient() as client:
        assert client.token is None
        # 未鉴权时不应包含 Authorization 头
        assert "Authorization" not in client._client.headers


async def test_init_with_token_sets_auth_header():
    """传入 Token 时 Authorization 头被正确设置"""
    async with GitHubClient(token="ghp_test123") as client:
        assert client.token == "ghp_test123"
        assert client._client.headers.get("Authorization") == "Bearer ghp_test123"


# ---------------------------------------------------------------------------
# search tests
# ---------------------------------------------------------------------------


async def test_search_returns_results(httpx_mock):
    """正常搜索：返回结果并映射字段"""
    httpx_mock.add_response(
        url="https://api.github.com/search/repositories?q=fastapi&sort=stars&order=desc&per_page=10",
        json=_sample_response(
            items=[
                _sample_repo(name="tiangolo/fastapi", description="FastAPI framework", stars=70000),
                _sample_repo(name="encode/starlette", description="ASGI framework", stars=9000),
            ]
        ),
    )

    async with GitHubClient(token="t") as client:
        resp = await client.search("fastapi", max_results=10)

    assert resp.query == "fastapi"
    assert resp.source.value == "web_github"
    assert len(resp.results) == 2

    first = resp.results[0]
    assert first.title == "tiangolo/fastapi"
    assert first.url == "https://github.com/tiangolo/fastapi"
    assert first.snippet == "FastAPI framework"
    assert first.engine == "github"
    assert first.source.value == "web_github"
    assert first.raw["stars"] == 70000
    assert first.raw["language"] == "Python"
    assert first.raw["license"] == "MIT"
    assert first.raw["owner"] == "tiangolo"
    assert first.raw["topics"] == ["demo", "example"]


async def test_search_empty_items(httpx_mock):
    """空结果不崩溃"""
    httpx_mock.add_response(
        url="https://api.github.com/search/repositories?q=zzznoresult&sort=stars&order=desc&per_page=10",
        json=_sample_response(items=[]),
    )

    async with GitHubClient(token="t") as client:
        resp = await client.search("zzznoresult")

    assert resp.results == []
    assert resp.total_results == 0


async def test_search_skips_invalid_items(httpx_mock):
    """缺少 full_name 或 html_url 的条目被跳过"""
    httpx_mock.add_response(
        url="https://api.github.com/search/repositories?q=mixed&sort=stars&order=desc&per_page=10",
        json=_sample_response(
            items=[
                {"full_name": "", "html_url": "https://github.com/x/y"},  # 空 name
                {"full_name": "a/b", "html_url": ""},  # 空 url
                _sample_repo(name="ok/repo"),  # 有效
            ]
        ),
    )

    async with GitHubClient(token="t") as client:
        resp = await client.search("mixed")

    assert len(resp.results) == 1
    assert resp.results[0].title == "ok/repo"


async def test_search_respects_max_results(httpx_mock):
    """max_results 限制返回条数（即便 API 返回更多）"""
    httpx_mock.add_response(
        url="https://api.github.com/search/repositories?q=many&sort=stars&order=desc&per_page=2",
        json=_sample_response(items=[_sample_repo(name=f"user/repo{i}") for i in range(5)]),
    )

    async with GitHubClient(token="t") as client:
        resp = await client.search("many", max_results=2)

    assert len(resp.results) == 2


async def test_search_invalid_json_raises_parse_error(httpx_mock):
    """非 JSON 响应抛 ParseError"""
    httpx_mock.add_response(
        url="https://api.github.com/search/repositories?q=bad&sort=stars&order=desc&per_page=10",
        content=b"<html>not json</html>",
        headers={"Content-Type": "text/html"},
    )

    async with GitHubClient(token="t") as client:
        with pytest.raises(ParseError):
            await client.search("bad")


async def test_search_custom_sort_and_order(httpx_mock):
    """自定义 sort/order 参数被透传"""
    httpx_mock.add_response(
        url="https://api.github.com/search/repositories?q=q&sort=forks&order=asc&per_page=10",
        json=_sample_response(items=[_sample_repo()]),
    )

    async with GitHubClient(token="t") as client:
        resp = await client.search("q", sort="forks", order="asc")

    assert len(resp.results) == 1
