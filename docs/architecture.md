# SouWen 架构概览

> 本文档描述 SouWen 当前的架构。核心原则：**所有数据源元数据 + 执行适配集中到 `registry/` 单一事实源**，避免"同一份信息散落多处手工维护、频繁漂移"。

---

## 1. 分层图

```
┌────────────────────────────────────────────────────────────────┐
│ 展示层 Presentation                                            │
│   souwen.cli/*        CLI（按 domain 拆分）                    │
│   souwen.server/*     FastAPI（按 domain 拆分）                │
│   souwen.integrations/mcp/*  MCP 协议集成                      │
│   panel/              Web UI（4 皮肤 + 共享 core）             │
├────────────────────────────────────────────────────────────────┤
│ 应用入口 Application API                                        │
│   souwen.search            search(domain=, capability=) 派发   │
│   souwen.search            search_all(domains=)                │
│   souwen.web.fetch         fetch_content(urls, providers=)     │
│   souwen.web.wayback       WaybackClient                       │
├────────────────────────────────────────────────────────────────┤
│ 注册表层 Registry —— 单一事实源                                │
│   souwen.registry.adapter    SourceAdapter / MethodSpec        │
│   souwen.registry.meta       SourceMeta 与 catalog 查询        │
│   souwen.registry.sources    94 个内置 _reg(...) 声明（权威） │
│   souwen.registry.loader     字符串懒加载（避免启动 import）  │
│   souwen.registry.views      by_domain / by_capability / ...   │
├────────────────────────────────────────────────────────────────┤
│ 真实 Client 模块 Concrete Clients                              │
│   paper/  patent/  web/*                                      │
│   社交、视频、知识、办公、抓取和归档实现均使用真实模块路径       │
├────────────────────────────────────────────────────────────────┤
│ 平台层 Platform —— 所有域共用的基础设施                         │
│   souwen.core.http_client       SouWenHttpClient / OAuthClient │
│   souwen.core.scraper.base      BaseScraper                    │
│   souwen.core.rate_limiter      Token Bucket + 滑窗            │
│   souwen.core.retry             tenacity 重试                  │
│   souwen.core.session_cache     OAuth token 持久化             │
│   souwen.core.fingerprint       curl_cffi 指纹                 │
│   souwen.core.exceptions        全部异常类型                   │
│   souwen.core.parsing           HTML/JSON 辅助                 │
│   souwen.core.concurrency       per-loop Semaphore（D12）      │
│   souwen.models                 Pydantic 模型（SourceType 等） │
└────────────────────────────────────────────────────────────────┘
```

**依赖方向**：展示层 → 应用入口 → 注册表层 ↔ 真实 Client 模块；平台层被任何层引用。Client 模块之间不互相依赖。

---

## 2. 核心抽象：`SourceAdapter`

```python
@dataclass(frozen=True, slots=True)
class SourceAdapter:
    name: str                                    # 'openalex' / 'tavily' / ...
    domain: str                                  # paper|patent|web|social|...
    integration: str                             # open_api|scraper|official_api|self_hosted
    description: str
    config_field: str | None                     # SouWenConfig 对应字段（None=零配置）
    client_loader: Callable[[], type]            # lazy("souwen.paper.openalex:OpenAlexClient")
    methods: Mapping[str, MethodSpec]            # capability → MethodSpec
    extra_domains: frozenset[str] = frozenset()  # 跨域（当前仅允许 "fetch"）
    default_enabled: bool = True                 # 高风险源设 False
    default_for: frozenset[str] = frozenset()    # {"paper:search"} 声明默认源
    tags: frozenset[str] = frozenset()           # {"high_risk"} / ...
    auth_requirement: str | None = None          # none|optional|required|self_hosted
    credential_fields: tuple[str, ...] = ()      # 支持多字段凭据
    optional_credential_effect: str | None = None
    risk_level: str = "low"                      # low|medium|high
    risk_reasons: frozenset[str] = frozenset()
    distribution: str = "core"                   # core|extra|plugin
    package_extra: str | None = None
    stability: str = "stable"                    # stable|beta|experimental|deprecated
    usage_note: str | None = None                # 用户级提示（如"仅支持 DOI OA 查找"），不参与可用性判定

@dataclass(frozen=True, slots=True)
class MethodSpec:
    method_name: str                             # Client 上的方法名
    param_map: Mapping[str, str] = {}            # 'limit' → 'per_page' 的映射
    pre_call: Callable[[dict], dict] | None = None  # 复杂变换逃生舱
```

### 为什么需要 MethodSpec

各 Client 的 search 参数名各不相同：

```
OpenAlex.search(query, per_page=, ...)
Crossref.search(query, rows=, ...)
arXiv.search(query, max_results=, ...)
PubMed.search(query, retmax=, ...)
HuggingFace.search(query, top_n=, ...)
PatentsView.search(query=<dict>, ...)  # 查询结构是 {"_contains": ...}
EPO OPS.search(cql_query=, range_end=, ...)
USPTO ODP.search_applications(query=, per_page=, ...)  # 方法名都不一样
```

如果用一张大 dict 把这些 lambda 硬映射，每加一个源都要改多处。改由 adapter 声明：

```python
_reg(SourceAdapter(
    name="uspto_odp", domain="patent", ...,
    client_loader=lazy("souwen.patent.uspto_odp:UsptoOdpClient"),
    methods={"search": MethodSpec("search_applications", {"limit": "per_page"})},
))

_reg(SourceAdapter(
    name="patentsview", ...,
    methods={"search": MethodSpec("search", {"limit": "per_page"}, pre_call=_pv_pre_call)},
))
```

### 懒加载

注册表模块导入时**不**加载 93 个内置源对应的 Client：

```python
client_loader=lazy("souwen.paper.openalex:OpenAlexClient")
# ...
client_cls = adapter.client_loader()  # 此刻才 importlib.import_module
```

`lazy()` 基于 `functools.lru_cache` 保证同一路径只解析一次。

### Source Catalog 治理维度

`SourceAdapter` 的元数据被拆成几个正交维度，避免把"是否需要 Key"、"怎么接入"和"是否适合默认启用"混在一个 tier 里：

| 维度 | 字段 | 用途 |
|---|---|---|
| 接入方式 | `integration` | 描述技术路径：`open_api` / `scraper` / `official_api` / `self_hosted` |
| 鉴权要求 | `auth_requirement` / `credential_fields` | 描述运行前是否需要凭据，支持可选凭据和多字段凭据 |
| 可选凭据收益 | `optional_credential_effect` | 标注可选 Key 是提升限流、配额、质量、个性化还是礼貌访问 |
| 风险治理 | `risk_level` / `risk_reasons` | 控制默认启用和默认搜索范围,解释反爬、封号、配额成本等原因 |
| 分发范围 | `distribution` / `package_extra` | 表示核心内置、可选依赖或外部插件,以及建议 extra 组 |
| 成熟度 | `stability` | 区分 stable / beta / experimental / deprecated |
| 用户提示 | `usage_note` | 描述源运行时的限制或注意事项(如 unpaywall "仅支持 DOI OA 查找"、`stability="deprecated"` 源的修复进度);doctor / API / Panel 会作为消息后缀展示,**不参与可用性判定** |

兼容字段仍保留：`needs_config`、`config_field`、`tags={"high_risk"}` 与 `v0_all_sources:exclude` 会派生到新的 catalog 视图中。

---

## 3. Domain × Capability 矩阵

**10 个 domain + 横切 `fetch`**：

| Domain | 说明 | 常见 capability |
|---|---|---|
| `paper` | 学术论文 | search, get_detail |
| `patent` | 专利 | search, get_detail |
| `web` | 通用网页搜索 | search, search_news, search_images, search_videos |
| `social` | 社交平台 | search |
| `video` | 视频平台 | search, get_trending, get_detail, get_transcript |
| `knowledge` | 百科/知识库 | search, get_detail |
| `developer` | 开发者社区 | search, search_users, get_detail |
| `cn_tech` | 中文技术社区 | search |
| `office` | 企业/办公 | search |
| `archive` | 档案/历史 | archive_lookup, archive_save |
| `fetch` *(横切)* | 内容抓取 | fetch |

**12 个标准 capability**：`search` / `search_news` / `search_images` / `search_videos` / `search_articles` / `search_users` / `get_detail` / `get_trending` / `get_transcript` / `fetch` / `archive_lookup` / `archive_save`。

非标准能力使用命名空间前缀（D8），如 `exa:find_similar` / `unpaywall:find_oa`——注册表接受任意字符串 capability，但只有标准 12 个参与门面自动派发。

### 跨域能力

有些源同时可做搜索和抓取（`extra_domains={"fetch"}`）：

| 源 | 主 domain | fetch 方法 |
|---|---|---|
| Tavily | web | `extract` |
| Firecrawl | web | `scrape` |
| Exa | web | `contents` |
| Wayback | archive | `fetch` |

---

## 4. 并发与超时

- **per-event-loop Semaphore**（D12）：`core.concurrency.get_semaphore(channel)` 按当前 running loop 存 `WeakKeyDictionary[loop, Semaphore]`。同 loop 多次调用返回同一个；跨 `asyncio.new_event_loop()` 自动隔离；loop 被 GC 后自动清理。
- **两个独立 channel**：`search` 与 `web`，互不阻塞。
- **单源超时上限 15s**，受 `SouWenConfig.timeout` 约束；超时源丢弃，不影响其他源。
- **异常隔离**：单源抛异常（ConfigError / RateLimitError / 其他）时只记 log，不阻塞其他源。

## 5. 限流与反爬

见 [anti-scraping.md](anti-scraping.md)。要点：

- **TLS 指纹**：`curl_cffi` 为 15+ 爬虫类源伪装 Chrome/Safari TLS ClientHello
- **Token Bucket + 滑窗双层限流**：每源独立
- **WARP 五模式**：wireproxy / kernel / usque / warp-cli / external
- **SSRF 防护**：fetch 入口的重定向跟踪 + 私网/回环/链路本地 IP 黑名单；Scrapling 浏览器模式额外安装 Playwright 请求拦截

## 6. 配置

- **层级优先级**：env > `./souwen.yaml` > `~/.config/souwen/config.yaml` > `.env` > 默认值
- **频道级覆盖**：每个源可独立配 proxy / http_backend / base_url / headers / params（见 `SouWenConfig.sources`）
- 完整字段列表见 [configuration.md](configuration.md)

## 7. 扩展：新增一个数据源

**最少只改 2 处**：

1. 在真实实现模块写 Client（论文/专利使用 `souwen.paper.*` / `souwen.patent.*`；网页、社交、视频、知识、办公、抓取和归档相关实现使用 `souwen.web.*`；继承 `SouWenHttpClient` / `BaseScraper`）
2. 在 `src/souwen/registry/sources/` 加一个 `_reg(SourceAdapter(...))`

如需 API Key，加第 3 处：`SouWenConfig` 加字段。完整流程见 [adding-a-source.md](adding-a-source.md)。

## 8. 插件系统（外部扩展）

注册表除了承载内置的 94 个 `_reg()`，还能在运行时**通过外部插件**追加新的
`SourceAdapter`，让第三方 / 私有源在不改主仓代码的前提下被 SouWen 发现。

### 双模式加载

插件可以通过两种方式部署，二者使用同一套 entry_points 机制：

| 模式 | 安装命令 | 适用场景 |
|---|---|---|
| **运行时发现** | `pip install superweb2pdf` | 第三方包单独分发；与 SouWen 解耦升级 |
| **打包嵌入** | `pip install -e ".[web2pdf]"` | Docker / 一键部署；插件依赖随 SouWen extras 自动拉取 |

Docker 镜像示例：`pip install ".[server,tls,web2pdf]"`。
两种模式都依赖同一个 `[project.entry-points."souwen.plugins"]` 声明，
SouWen 启动时统一通过 `importlib.metadata` 扫描发现。

### 加载流程

```
┌─────────────────────────────────────────────────────────────────┐
│  registry/__init__.py 导入                                       │
│      ↓                                                           │
│  1. import sources       —— 触发 94 个内置 _reg()，填满 _REGISTRY │
│      ↓                                                           │
│  2. plugin.load_plugins()                                        │
│       ├─ discover_entrypoint_plugins()                           │
│       │     扫描 importlib.metadata entry_points(group=          │
│       │     "souwen.plugins")，逐个 ep.load() → _coerce_to_     │
│       │     adapters() → _reg_external()                         │
│       └─ load_config_plugins(config.plugins)                     │
│             解析 "module:attr" 字符串列表，同上                  │
│      ↓                                                           │
│  3. _reg_external(adapter)                                       │
│       与已有源重名 → 记 warning 跳过（不抛）                    │
│       否则插入 _REGISTRY 并加入 _EXTERNAL_PLUGINS                │
└─────────────────────────────────────────────────────────────────┘
```

外部插件名出现在 `external_plugins()` 视图里，便于 CLI / `/sources` 端点审计。

### 与内置注册的关键差异

| 维度 | 内置 `_reg()` | 外部 `_reg_external()` |
|---|---|---|
| 声明位置 | `registry/sources/` | 第三方包的 entry point |
| 重名 | 抛 `ValueError`（启动失败） | 记 warning 跳过 |
| 一致性测试 | 必跑 `tests/registry/test_consistency.py` | 不强制 |
| 暴露视图 | 同上 | 额外出现在 `external_plugins()` |

### Fetch Handler 注册表

`fetch` 域的派发不在 registry 层，而在 [`souwen.web.fetch`](../src/souwen/web/fetch.py)
的独立 dict `_FETCH_HANDLERS: dict[str, FetchHandler]`：

```python
FetchHandler = Callable[..., Awaitable[FetchResponse]]

_FETCH_HANDLERS["builtin"]      = _handle_builtin
_FETCH_HANDLERS["jina_reader"]  = _handle_jina_reader
# ... 22 个内置 provider
```

外部插件通过 `register_fetch_handler(provider, handler)` 加入这张表，让
`souwen.web.fetch.fetch_content(providers=["my_source"])` 能派发到自己的实现。

> 设计原因：fetch 调用的入参形态（`urls`/`timeout`/各种 provider 私有 kwarg）
> 与 `MethodSpec` 的统一入参不完全对齐，单独一张 handler 表更直接。
> SourceAdapter 负责"出现在 registry / `souwen sources`"，handler 负责"能被
> fetch 真正派发"，二者互补。

### 对接规范

完整的插件对接契约（SourceAdapter / MethodSpec / Client / Fetch handler / 配置 /
打包 / 测试）见 [docs/plugin-integration-spec.md](plugin-integration-spec.md)。

---

## 9. 结构一致性测试（护栏）

`tests/registry/test_consistency.py` 含 21 项硬断言，CI 每次 PR 必跑：

- capability 全部在标准集或命名空间形式
- extra_domains 只允许 `fetch`
- MethodSpec.method_name 在 Client 类上真实存在
- param_map 的目标参数名是方法签名里的参数
- config_field / credential_fields 在 `SouWenConfig.model_fields` 里存在
- default_for 的 key 能解析为 (domain, capability) 且都合法
- 注册表无重名
- `ALL_SOURCES` 与 `registry.as_all_sources_dict()` 派生一致
- high_risk 源不在任何默认源集
- `resolve_params` 对所有 adapter/method 不抛异常
- SourceType 枚举 ⊆ registry.enum_values（通过规范化映射）
- 所有标准 capability 都有源实现
- 每个 domain 至少有一个源支持 search / archive_lookup
- fetch 提供者 ≥ 10 个

## 10. 公开 API 入口

注册表是单一事实源，但提供多条便捷入口：

- `from souwen.paper import OpenAlexClient`、`from souwen.web.tavily import TavilyClient` 等真实模块 import 路径
- 顶层 CLI 动词：`souwen search paper`、`souwen fetch`、`souwen wayback cdx` 等
- REST 路径：`/api/v1/search/paper`、`/api/v1/fetch` 等
- `SouWenConfig` 字段名稳定（只增不改）

详见 [CHANGELOG.md](../CHANGELOG.md)。
