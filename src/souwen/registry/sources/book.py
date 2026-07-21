"""Built-in book catalog source declarations."""

from __future__ import annotations

from souwen.registry.sources._helpers import MethodSpec, SourceAdapter, _P_PER_PAGE, _reg, lazy

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
