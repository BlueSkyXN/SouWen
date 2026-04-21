"""Bilibili MCP 工具定义与分发

为 SouWen MCP 服务器扩展 Bilibili 专属工具，覆盖搜索、视频详情、
用户信息、评论、字幕、AI 摘要、热门、排行、相关推荐、用户搜索等场景。

设计原则：
    - 工具定义与分发分离，便于 mcp_server.py 一处导入注册
    - 所有工具异常都被捕获并返回结构化错误，绝不抛出
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
    "bilibili_video_details",
    "bilibili_user_info",
    "bilibili_user_videos",
    "bilibili_comments",
    "bilibili_subtitles",
    "bilibili_ai_summary",
    "bilibili_popular",
    "bilibili_ranking",
    "bilibili_related",
    "bilibili_search_users",
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
        Tool(
            name="bilibili_user_info",
            description=(
                "通过 UID 获取 Bilibili 用户信息（昵称、签名、等级、粉丝数、"
                "关注数、投稿数、大会员、认证、直播状态等）。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "mid": {"type": "integer", "description": "用户 UID"},
                },
                "required": ["mid"],
            },
        ),
        Tool(
            name="bilibili_user_videos",
            description="获取指定 UP 主的投稿视频列表（分页）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "mid": {"type": "integer", "description": "用户 UID"},
                    "page": {"type": "integer", "default": 1, "description": "页码（从 1 开始）"},
                    "page_size": {
                        "type": "integer",
                        "default": 30,
                        "description": "每页条数",
                    },
                },
                "required": ["mid"],
            },
        ),
        Tool(
            name="bilibili_comments",
            description=("获取 Bilibili 视频评论列表，按指定方式排序，可累积跨多页。"),
            inputSchema={
                "type": "object",
                "properties": {
                    "bvid": {"type": "string", "description": "视频 BV 号"},
                    "sort": {
                        "type": "integer",
                        "default": 1,
                        "description": "排序：0=时间, 1=点赞, 2=回复",
                    },
                    "max_comments": {
                        "type": "integer",
                        "default": 30,
                        "description": "最大返回评论数",
                    },
                },
                "required": ["bvid"],
            },
        ),
        Tool(
            name="bilibili_subtitles",
            description=(
                "获取 Bilibili 视频字幕（CC 字幕），优先返回中文。"
                "返回字幕分行内容与拼接的全文，适合做视频摘要、翻译、检索。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "bvid": {"type": "string", "description": "视频 BV 号"},
                },
                "required": ["bvid"],
            },
        ),
        Tool(
            name="bilibili_ai_summary",
            description=(
                "获取 Bilibili 官方 AI 视频摘要（如视频已被 AI 处理）。"
                "result_type=0 表示该视频暂无 AI 摘要。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "bvid": {"type": "string", "description": "视频 BV 号"},
                },
                "required": ["bvid"],
            },
        ),
        Tool(
            name="bilibili_popular",
            description="获取 Bilibili 当前热门视频列表（首页热门）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "page": {"type": "integer", "default": 1, "description": "页码"},
                    "page_size": {
                        "type": "integer",
                        "default": 20,
                        "description": "每页条数",
                    },
                },
            },
        ),
        Tool(
            name="bilibili_ranking",
            description=("获取 Bilibili 排行榜视频列表。可指定分区与排行类型。"),
            inputSchema={
                "type": "object",
                "properties": {
                    "rid": {
                        "type": "integer",
                        "default": 0,
                        "description": "分区 ID，0 表示全站",
                    },
                    "type": {
                        "type": "string",
                        "default": "all",
                        "description": "排行类型：all/origin/rookie 等",
                    },
                },
            },
        ),
        Tool(
            name="bilibili_related",
            description="获取与指定视频相关的推荐视频列表。",
            inputSchema={
                "type": "object",
                "properties": {
                    "bvid": {"type": "string", "description": "视频 BV 号"},
                },
                "required": ["bvid"],
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

    if name == "bilibili_video_details":
        async with BilibiliClient() as client:
            detail = await client.get_video_details(str(arguments["bvid"]))
            return _dump(detail)

    if name == "bilibili_user_info":
        async with BilibiliClient() as client:
            info = await client.get_user_info(int(arguments["mid"]))
            return _dump(info)

    if name == "bilibili_user_videos":
        async with BilibiliClient() as client:
            videos, total = await client.get_user_videos(
                int(arguments["mid"]),
                page=int(arguments.get("page", 1)),
                page_size=int(arguments.get("page_size", 30)),
            )
            return {"total": total, "videos": _dump(videos)}

    if name == "bilibili_comments":
        async with BilibiliClient() as client:
            comments = await client.get_comments(
                str(arguments["bvid"]),
                sort=int(arguments.get("sort", 1)),
                max_comments=int(arguments.get("max_comments", 30)),
            )
            return _dump(comments)

    if name == "bilibili_subtitles":
        async with BilibiliClient() as client:
            subs = await client.get_subtitles(str(arguments["bvid"]))
            return _dump(subs)

    if name == "bilibili_ai_summary":
        async with BilibiliClient() as client:
            summary = await client.get_ai_summary(str(arguments["bvid"]))
            return _dump(summary)

    if name == "bilibili_popular":
        async with BilibiliClient() as client:
            videos = await client.get_popular(
                page=int(arguments.get("page", 1)),
                page_size=int(arguments.get("page_size", 20)),
            )
            return _dump(videos)

    if name == "bilibili_ranking":
        async with BilibiliClient() as client:
            videos = await client.get_ranking(
                rid=int(arguments.get("rid", 0)),
                type=str(arguments.get("type", "all")),
            )
            return _dump(videos)

    if name == "bilibili_related":
        async with BilibiliClient() as client:
            videos = await client.get_related(str(arguments["bvid"]))
            return _dump(videos)

    if name == "bilibili_search_users":
        async with BilibiliClient() as client:
            users = await client.search_users(
                arguments["keyword"],
                page=int(arguments.get("page", 1)),
                max_results=int(arguments.get("max_results", 10)),
            )
            return _dump(users)

    return None
