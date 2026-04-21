"""Bilibili MCP 工具定义与分发（精简版：搜索 + 抓取）

为 SouWen MCP 服务器扩展 Bilibili 专属工具，聚焦核心使命：

    - bilibili_search          视频搜索
    - bilibili_search_users    用户搜索
    - bilibili_search_articles 专栏文章搜索
    - bilibili_video_details   按 BV 号抓取视频详情

派生功能（评论 / 字幕 / AI 摘要 / 热门 / 排行 / 相关推荐 /
用户信息 / 用户视频列表）属于独立的 bili-cli 项目范畴，本仓库不再提供。

设计原则：
    - 工具定义与分发分离，便于 mcp_server.py 一处导入注册
    - 所有工具异常都被捕获并返回结构化错误，绝不抛出（由调用方 mcp_server 处理）
    - Pydantic 模型统一通过 model_dump(mode="json") 序列化
    - mcp 库为可选依赖，import 失败时模块仍可被加载（工具列表返回空）

主要函数：
    get_bilibili_tools() -> list[Tool]
        - 返回所有 Bilibili 工具的 MCP Tool 定义
    dispatch_bilibili_tool(name, arguments) -> Any | None
        - 按工具名分发到 BilibiliClient 方法；不匹配返回 None 由上层兜底
"""

from __future__ import annotations

from typing import Any

try:
    from mcp.types import Tool

    HAS_MCP = True
except ImportError:
    HAS_MCP = False
    Tool = None  # type: ignore[assignment,misc]


_BILIBILI_TOOL_NAMES: tuple[str, ...] = (
    "bilibili_search",
    "bilibili_search_users",
    "bilibili_search_articles",
    "bilibili_video_details",
)


def is_bilibili_tool(name: str) -> bool:
    """判断给定工具名是否属于 Bilibili 工具集"""
    return name in _BILIBILI_TOOL_NAMES


def get_bilibili_tools() -> list[Any]:
    """返回 Bilibili 工具的 MCP Tool 定义列表

    Returns:
        list[Tool]：MCP SDK 未安装时返回空列表
    """
    if not HAS_MCP:
        return []

    return [
        Tool(
            name="bilibili_search",
            description=(
                "搜索 Bilibili 视频。返回视频标题、作者、播放量、链接等聚合结果。"
                "适用于：找视频、查 UP 主作品、关键词调研。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词"},
                    "max_results": {
                        "type": "integer",
                        "default": 10,
                        "description": "最大返回条数（B 站单页上限 50）",
                    },
                    "order": {
                        "type": "string",
                        "default": "totalrank",
                        "description": "排序方式：totalrank/click/pubdate/dm/stow",
                    },
                },
                "required": ["keyword"],
            },
        ),
        Tool(
            name="bilibili_search_users",
            description="按关键词搜索 Bilibili 用户（UP 主）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "用户关键词"},
                    "page": {"type": "integer", "default": 1, "description": "页码"},
                    "max_results": {
                        "type": "integer",
                        "default": 10,
                        "description": "最大返回条数",
                    },
                },
                "required": ["keyword"],
            },
        ),
        Tool(
            name="bilibili_search_articles",
            description=(
                "按关键词搜索 Bilibili 专栏文章。返回文章标题、作者、分类、"
                "阅读/点赞/评论量、封面图与文章链接。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词"},
                    "page": {"type": "integer", "default": 1, "description": "页码"},
                    "max_results": {
                        "type": "integer",
                        "default": 10,
                        "description": "最大返回条数（B 站单页上限 50）",
                    },
                },
                "required": ["keyword"],
            },
        ),
        Tool(
            name="bilibili_video_details",
            description=(
                "通过 BV 号获取 Bilibili 视频详情，包括标题、简介、UP 主、"
                "时长、统计数据（播放/点赞/收藏等）、标签、分区。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "bvid": {"type": "string", "description": "视频 BV 号，例如 BV1xx411c7mD"},
                },
                "required": ["bvid"],
            },
        ),
    ]


def _dump(obj: Any) -> Any:
    """统一序列化：Pydantic 模型 -> JSON 兼容 dict；其他类型原样返回"""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [_dump(x) for x in obj]
    if isinstance(obj, tuple):
        return [_dump(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _dump(v) for k, v in obj.items()}
    return obj


async def dispatch_bilibili_tool(name: str, arguments: dict) -> Any:
    """按工具名分发 Bilibili 工具调用

    Args:
        name: MCP 工具名
        arguments: 工具参数字典

    Returns:
        JSON 兼容结构（dict / list / 原始类型）；
        若 name 不属于 Bilibili 工具集，返回特殊 sentinel None —
        调用方需在外层结合 is_bilibili_tool 判断。
    """
    from souwen.web.bilibili.client import BilibiliClient

    if name == "bilibili_search":
        async with BilibiliClient() as client:
            response = await client.search(
                arguments["keyword"],
                max_results=int(arguments.get("max_results", 10)),
                order=str(arguments.get("order", "totalrank")),
            )
            return _dump(response)

    if name == "bilibili_search_users":
        async with BilibiliClient() as client:
            users = await client.search_users(
                arguments["keyword"],
                page=int(arguments.get("page", 1)),
                max_results=int(arguments.get("max_results", 10)),
            )
            return _dump(users)

    if name == "bilibili_search_articles":
        async with BilibiliClient() as client:
            articles = await client.search_articles(
                arguments["keyword"],
                page=int(arguments.get("page", 1)),
                max_results=int(arguments.get("max_results", 10)),
            )
            return _dump(articles)

    if name == "bilibili_video_details":
        async with BilibiliClient() as client:
            detail = await client.get_video_details(str(arguments["bvid"]))
            return _dump(detail)

    return None
