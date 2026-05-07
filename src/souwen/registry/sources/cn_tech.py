"""Built-in source declarations for this catalog segment."""

from __future__ import annotations

from souwen.registry.sources._helpers import (
    MethodSpec,
    SourceAdapter,
    lazy,
    _reg,
    _P_MAX_RESULTS,
)

# ═════════════════════════════════════════════════════════════
# 10. cn_tech（9 源）
# ═════════════════════════════════════════════════════════════

_reg(
    SourceAdapter(
        name="csdn",
        domain="cn_tech",
        integration="scraper",
        description="CSDN 技术博客搜索",
        config_field=None,
        client_loader=lazy("souwen.web.csdn:CSDNClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)

_reg(
    SourceAdapter(
        name="juejin",
        domain="cn_tech",
        integration="scraper",
        description="稀土掘金技术文章搜索",
        config_field=None,
        client_loader=lazy("souwen.web.juejin:JuejinClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)

_reg(
    SourceAdapter(
        name="linuxdo",
        domain="cn_tech",
        integration="open_api",
        description="LinuxDo 论坛搜索（Discourse）",
        config_field=None,
        client_loader=lazy("souwen.web.linuxdo:LinuxDoClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)

_reg(
    SourceAdapter(
        name="nodeseek",
        domain="cn_tech",
        integration="scraper",
        description="NodeSeek 社区搜索（DDG site:nodeseek.com）",
        config_field=None,
        client_loader=lazy("souwen.web.nodeseek:NodeSeekClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)

_reg(
    SourceAdapter(
        name="hostloc",
        domain="cn_tech",
        integration="scraper",
        description="HostLoc 论坛搜索（DDG site:hostloc.com）",
        config_field=None,
        client_loader=lazy("souwen.web.hostloc:HostLocClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)

_reg(
    SourceAdapter(
        name="v2ex",
        domain="cn_tech",
        integration="scraper",
        description="V2EX 社区搜索（DDG site:v2ex.com）",
        config_field=None,
        client_loader=lazy("souwen.web.v2ex:V2EXClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)

_reg(
    SourceAdapter(
        name="coolapk",
        domain="cn_tech",
        integration="scraper",
        description="Coolapk 社区搜索（DDG site:coolapk.com）",
        config_field=None,
        client_loader=lazy("souwen.web.coolapk:CoolapkClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)

_reg(
    SourceAdapter(
        name="xiaohongshu",
        domain="cn_tech",
        integration="scraper",
        description="小红书搜索（DDG site:xiaohongshu.com）",
        config_field=None,
        client_loader=lazy("souwen.web.xiaohongshu:XiaohongshuClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)

_reg(
    SourceAdapter(
        name="community_cn",
        domain="cn_tech",
        integration="scraper",
        description="【已弃用兼容入口】中文社区聚合搜索（请改用 linuxdo/nodeseek/hostloc/v2ex/coolapk/xiaohongshu）",
        config_field=None,
        client_loader=lazy("souwen.web.community_cn:CommunityCnClient"),
        methods={"search": MethodSpec("search", _P_MAX_RESULTS)},
    )
)
