"""Built-in book catalog source declarations."""

from __future__ import annotations

from souwen.registry.sources._helpers import MethodSpec, SourceAdapter, _P_PER_PAGE, _reg, lazy


def _wikisource_detail_params(params: dict[str, object]) -> dict[str, object]:
    """Drop generic capability pagination; page detail owns its explicit bounds."""
    params.pop("limit", None)
    return params


_reg(
    SourceAdapter(
        name="open_library",
        domain="book",
        category="book",
        integration="official_api",
        description="Open Library work、edition 与封面元数据（官方匿名 API）",
        config_field=None,
        auth_requirement="none",
        risk_level="low",
        distribution="core",
        stability="stable",
        usage_note="仅提供书目与上游资源链接；不会自动借阅、阅读或下载 Internet Archive 内容。",
        client_loader=lazy("souwen.book.open_library:OpenLibraryClient"),
        methods={
            "search": MethodSpec("search", _P_PER_PAGE),
            "get_detail": MethodSpec("get_by_work_id", {"id": "work_id"}),
        },
        default_for=frozenset({"book:search"}),
    )
)

_reg(
    SourceAdapter(
        name="librivox",
        domain="book",
        category="book",
        integration="official_api",
        description="LibriVox 有声书 metadata 与 RSS 链接（官方匿名 API）",
        config_field=None,
        auth_requirement="none",
        risk_level="low",
        distribution="core",
        stability="stable",
        usage_note="仅返回 metadata/RSS/外部链接，不下载音频；权利按记录与法域保守处理。",
        client_loader=lazy("souwen.book.librivox:LibriVoxClient"),
        methods={
            "search": MethodSpec("search", _P_PER_PAGE),
            "get_detail": MethodSpec("get_by_id", {"id": "audiobook_id"}),
        },
    )
)

_reg(
    SourceAdapter(
        name="internet_archive",
        domain="book",
        category="book",
        integration="official_api",
        description="Internet Archive 数字馆藏书目、扫描件与文件元数据（官方匿名 API）",
        config_field=None,
        auth_requirement="none",
        risk_level="low",
        distribution="core",
        stability="stable",
        usage_note="文件链接与 rights/access 状态逐条保留；不会自动借阅、阅读或下载。",
        client_loader=lazy("souwen.book.internet_archive:InternetArchiveClient"),
        methods={
            "search": MethodSpec("search", _P_PER_PAGE),
            "get_detail": MethodSpec("get_by_identifier", {"id": "identifier"}),
        },
    )
)

_reg(
    SourceAdapter(
        name="wikisource",
        domain="book",
        category="book",
        integration="official_api",
        description="受控中文/英文 Wikisource 站点的页面、revision 与有界正文读取（官方 MediaWiki API）",
        config_field=None,
        auth_requirement="none",
        risk_level="low",
        distribution="core",
        stability="stable",
        usage_note=(
            "仅读取明确页面与 revision；不导入 dumps、不递归子页，且不从站点托管推断底本全球公版或再分发权利。"
        ),
        client_loader=lazy("souwen.book.wikisource:WikisourceClient"),
        methods={
            "search": MethodSpec("search", _P_PER_PAGE),
            "get_detail": MethodSpec(
                "get_page_detail",
                {"query": "title", "id": "title"},
                pre_call=_wikisource_detail_params,
            ),
        },
    )
)

_reg(
    SourceAdapter(
        name="library_of_congress",
        domain="book",
        category="book",
        integration="official_api",
        description="Library of Congress 书目与数字馆藏元数据（官方匿名 JSON API）",
        config_field=None,
        auth_requirement="none",
        risk_level="low",
        distribution="core",
        stability="stable",
        usage_note="数字资源、rights 与 access 逐条保留；不下载资源或推断再分发权利。",
        client_loader=lazy("souwen.book.library_of_congress:LibraryOfCongressClient"),
        methods={
            "search": MethodSpec("search", _P_PER_PAGE),
            "get_detail": MethodSpec("get_by_id", {"id": "record_id"}),
        },
    )
)
