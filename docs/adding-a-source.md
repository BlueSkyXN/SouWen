# 添加一个新数据源（V1 指南）

> 在 V1 架构下，新增一个数据源 = **改 1-2 处文件**：实现 Client + 在 `registry/sources/` 注册。
> 不再需要去改 `search.py` / `web/search.py` / `models.py` / `registry/meta.py` 的多份分发表。

## 全景

```
1. 实现 Client 类（按需选基类：BaseClient / OAuthClient / BaseScraper）
        │
        ▼
2. 在 src/souwen/registry/sources/ 添加 _reg(SourceAdapter(...))
        │
        ▼
3. 若需要 API Key/凭证：在 src/souwen/config/models.py 的 SouWenConfig 加字段
        │
        ▼
4. （可选）把默认源标记为 default_for=frozenset({"<domain>:<capability>"})
        │
        ▼
5. 跑 pytest tests/registry/test_consistency.py & 写源自身的单元测试
```

## 1. 实现 Client

按集成方式选择基类：

| 集成 | 基类 | 路径 | 何时用 |
|------|------|------|--------|
| 标准 REST API | `SouWenHttpClient` | `souwen.core.http_client` | 大多数官方 API |
| OAuth2 client_credentials | `OAuthClient` | `souwen.core.http_client` | EPO OPS、CNIPA 等需要 token 流的 API |
| HTML/SERP 爬取 | `BaseScraper` | `souwen.core.scraper.base` | DuckDuckGo / Bing / Google Patents 等 |

> 老路径 `souwen.http_client` / `souwen.scraper.base` 仍可用（V0 兼容 shim），新代码请用 `souwen.core.*`。

### 示例：official_api 论文源

```python
# src/souwen/paper/my_source.py
from __future__ import annotations

from souwen.config import get_config
from souwen.core.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse, SourceType


class MySourceClient(SouWenHttpClient):
    """My Source 论文检索客户端。"""

    def __init__(self, api_key: str | None = None) -> None:
        cfg = get_config()
        self.api_key = api_key or cfg.resolve_api_key("my_source", "my_source_api_key")
        super().__init__(
            base_url=cfg.resolve_base_url("my_source", "https://api.example.com"),
            headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
            source_name="my_source",  # 让频道级 base_url/proxy/headers 生效
        )

    async def search(self, query: str, per_page: int = 10) -> SearchResponse:
        resp = await self.get("/search", params={"q": query, "limit": per_page})
        data = resp.json()
        results = [self._parse(item) for item in data.get("items", [])]
        return SearchResponse(
            query=query,
            source=SourceType.my_source,
            total_results=data.get("total"),
            results=results,
            per_page=per_page,
        )

    def _parse(self, item: dict) -> PaperResult:
        return PaperResult(
            source=SourceType.my_source,
            title=item["title"],
            authors=[Author(name=a["name"]) for a in item.get("authors", [])],
            doi=item.get("doi"),
            year=item.get("year"),
            source_url=item.get("url", ""),
            raw=item,
        )
```

要点：

- **以 `source_name=` 调用基类构造器**，这样频道配置（`sources.my_source.proxy / base_url / headers`）会自动生效。
- 用 `cfg.resolve_api_key(name, legacy_field)` 让"频道 `api_key`"优先于全局 flat key。
- 异常由基类负责：`401/403→AuthError`、`429→RateLimitError`、`5xx→SourceUnavailableError`。Client 内部抛业务异常即可。

## 2. 在 registry 注册

打开 `src/souwen/registry/sources/`，按域插入新条目：

```python
# === paper（19 源） 区段末尾追加 ===
_reg(SourceAdapter(
    name="my_source",
    domain="paper",
    integration="official_api",
    description="My Source 论文检索（含全文链接）",
    config_field="my_source_api_key",
    needs_config=True,                      # 旧兼容字段：必须配 Key 才能工作
    auth_requirement="required",            # none / optional / required / self_hosted
    credential_fields=("my_source_api_key",),
    risk_level="low",
    distribution="core",
    client_loader=lazy("souwen.paper.my_source:MySourceClient"),
    methods={
        "search": MethodSpec(
            "search",
            param_map=_P_PER_PAGE,         # {"limit": "per_page"} 速记
        ),
    },
    default_for=frozenset(),                # 不进默认源；想进默认就写 {"paper:search"}
    tags=frozenset({"v0_category:professional"}),
))
```

字段速查：

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | ✅ | 全局唯一，建议小写下划线 |
| `domain` | ✅ | 见 `DOMAINS ∪ {FETCH_DOMAIN}`：paper/patent/web/social/video/knowledge/developer/cn_tech/office/archive/fetch |
| `integration` | ✅ | `open_api` / `official_api` / `self_hosted` / `scraper` |
| `description` | ✅ | UI / `/api/v1/sources` 展示文案 |
| `config_field` | 推荐 | `SouWenConfig` 的字段名；零配置源传 `None` |
| `client_loader` | ✅ | 必须用 `lazy("module.path:ClassName")`，避免启动 import 全部 Client |
| `methods` | ✅ | `capability → MethodSpec` 映射，至少包含一项（如 `"search"`） |
| `extra_domains` | — | 跨域能力，**目前仅允许 `frozenset({"fetch"})`**（如 Tavily 同时是 web 搜索引擎和 fetch provider） |
| `default_enabled` | — | UI 默认是否勾选；高风险源（google/baidu/twitter）建议 `False` |
| `default_for` | — | 形如 `{"paper:search"}`，声明此源是否进入 `(domain, capability)` 默认集 |
| `tags` | — | `{"high_risk"}`；内置 web 源可用 `v0_category:*`，外部 web 插件用公开 `category:general/professional` |
| `needs_config` | 推荐 | 显式声明是否"必须配置才能工作"（None 时按 integration 推断） |
| `auth_requirement` | 推荐 | `none` / `optional` / `required` / `self_hosted`；新代码优先使用它 |
| `credential_fields` | 推荐 | 完整凭据字段；多字段 OAuth 源列全，如 `("client_id", "client_secret")` |
| `optional_credential_effect` | 可选 | 可选凭据收益：`rate_limit` / `quota` / `politeness` / `personalization` 等 |
| `risk_level` / `risk_reasons` | 推荐 | `low` / `medium` / `high` 与原因标签，用于默认启用和运维提示 |
| `distribution` / `package_extra` | 推荐 | `core` / `extra` / `plugin` 与建议 optional dependency 组 |
| `stability` | 推荐 | `stable` / `beta` / `experimental` / `deprecated` |
| `usage_note` | 可选 | 用户级提示文案(如 `"仅支持 DOI OA 查找"`、`"公开搜索端点已变更,当前接入待修复"`);doctor / API / Panel 会把它附加到状态消息末尾,**不参与可用性判定**。`stability="deprecated"` / `experimental` + scraper 的源建议显式声明该字段 |

### 鉴权与分发口径

`integration` 只描述"怎么接入"，不描述 Key 强度。官方 API 也可能匿名可用，可通过可选 Key 提升限流；爬虫源也可能有登录态 Cookie。新增源时优先按下面的组合声明：

| 场景 | 推荐声明 |
|---|---|
| 完全免配置 | `auth_requirement="none"`, `config_field=None` |
| 可选 Key 提高限流/配额 | `auth_requirement="optional"`, `needs_config=False`, `optional_credential_effect="rate_limit"` |
| 必须凭据 | `auth_requirement="required"`, `credential_fields=(...)` |
| 自建实例 | `auth_requirement="self_hosted"`, `config_field="<source>_url"`；必须声明 URL/凭据字段 |
| 纯抓取 / fetch provider | `domain="fetch"`, `methods={"fetch": MethodSpec("fetch")}` |
| 重依赖或长尾源 | `distribution="extra"` 并设置 `package_extra`，或作为外部插件发布 |

关于 `MethodSpec.param_map`：

```python
# 大多数源走声明式重命名
methods={"search": MethodSpec("search", {"limit": "per_page"})}

# 极少数需要复杂入参变换，用 pre_call 逃生舱
def _wrap_query(native: dict) -> dict:
    return {"query": {"_contains": {"patent_title": native["query"]}}, "page_size": native["limit"]}

methods={"search": MethodSpec("search", pre_call=_wrap_query)}
```

## 3. 在 SouWenConfig 加字段（仅当需要 API Key）

```python
# src/souwen/config/models.py
class SouWenConfig(BaseModel):
    # ===== 论文数据源 =====
    ...
    my_source_api_key: str | None = None  # My Source API Key
```

环境变量自动派生为 `SOUWEN_MY_SOURCE_API_KEY`。同时记得在 `souwen.example.yaml` 的 `paper:` 段加一行注释，方便用户发现。

## 4. （可选）让源进入默认集

希望 `souwen search paper "xxx"` 默认就会调用你的源？在 `SourceAdapter` 上加 `default_for`：

```python
default_for=frozenset({"paper:search"}),
```

`registry.defaults_for("paper", "search")` 会按"声明顺序"返回所有标了 `paper:search` 的源，门面层据此构建默认源列表。

> ⚠️ 高风险源（带 `tags={"high_risk"}`）应**保持 `default_for` 为空**，避免默认调用时被风控直接 ban——`tests/registry/test_consistency.py::test_high_risk_not_default` 会强制校验这一点。

## 5. 测试

### 一致性测试（必须通过）

```bash
pytest tests/registry/test_consistency.py -v
```

它会自动校验：

1. `client_loader` 指向的类真实存在；
2. `MethodSpec.method_name` 在该类上可解析；
3. `MethodSpec.param_map` 的目标参数名是方法签名的真实参数；
4. `config_field`（若非 None）确实存在于 `SouWenConfig`；
5. `credential_fields` 中每个字段也存在于 `SouWenConfig`；
6. `default_for` 形如 `<domain>:<capability>` 且都合法；
7. capability 在标准集 `CAPABILITIES` 里或为 `xxx:yyy` 命名空间形式；
8. `extra_domains` 仅允许 `{"fetch"}`；
9. 注册表无重名；
10. `ALL_SOURCES` 派生与 registry 对齐；
11. 高风险源未进入默认集；
12. source catalog 的 auth/risk/distribution/stability 字段均在枚举范围内；
13. `resolve_params` 能完整覆盖每个 adapter（不抛异常）。

### 源自身的单元测试

放到 `tests/test_<domain>/test_my_source.py`，用 `pytest-httpx` mock：

```python
import pytest
from souwen.paper.my_source import MySourceClient

@pytest.mark.asyncio
async def test_my_source_search(httpx_mock):
    httpx_mock.add_response(
        url="https://api.example.com/search?q=transformer&limit=10",
        json={"items": [{"title": "Attention Is All You Need", "year": 2017}], "total": 1},
    )
    async with MySourceClient(api_key="test") as client:
        resp = await client.search("transformer", per_page=10)
    assert len(resp.results) == 1
    assert resp.results[0].title == "Attention Is All You Need"
```

## 6. 验证端到端

```bash
# CLI（注册表自动暴露）
souwen sources | grep my_source
souwen search paper "transformer" -s my_source -n 3

# REST
souwen serve &
curl 'http://localhost:8000/api/v1/sources' | jq '.paper[] | select(.name=="my_source")'
curl 'http://localhost:8000/api/v1/search/paper?q=transformer&sources=my_source&per_page=3'
```

## 常见陷阱

- **忘了 `lazy()`**：直接 `client_loader=lambda: MySourceClient` 会让 registry 在导入期就 import 你的 Client，破坏启动延迟优化。
- **`needs_config` 与 `config_field` 不一致**：可选 Key 的源（如 `openalex` / `github` / `doaj`）需显式 `needs_config=False` 或 `auth_requirement="optional"`，否则会被推断为"必须配置"。
- **`scraper` 类源忘了走 BaseScraper**：直接用 `httpx.AsyncClient` 会缺失 TLS 指纹与礼貌爬取，被风控的几率显著上升。详见 [anti-scraping.md](./anti-scraping.md)。
- **`extra_domains` 滥用**：V1 初期仅允许 `{"fetch"}`。需要跨更多域请先在 `local/` 写 RFC 讨论。
- **没在 `souwen.example.yaml` 加注释**：用户找不到字段是 V1 之后最高频的工单来源，请补上。

## 7. 替代方案：作为外部插件发布

如果数据源不打算合入主仓（私有、实验性或商业插件），可以作为独立 Python 包发布。
SouWen 通过 setuptools entry_points 或配置文件自动发现外部插件。

完整对接规范见 [plugin-integration-spec.md](./plugin-integration-spec.md)。

## 交叉引用

- 配置字段总览：[configuration.md](./configuration.md)
- 反爬 / 代理 / WARP：[anti-scraping.md](./anti-scraping.md)
- 后端 API 契约（`/api/v1/sources` 自动列出新源）：[api-reference.md](./api-reference.md)
- 通用贡献流程 / V0 兼容规则：[contributing.md](./contributing.md)
- 外部插件对接规范：[plugin-integration-spec.md](./plugin-integration-spec.md)
