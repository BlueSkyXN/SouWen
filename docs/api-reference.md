# API 接口参考

> SouWen 公开 API、数据模型、CLI 命令与 MCP 工具

> **架构提示**：搜索路由派发到 `souwen.search`，内容抓取使用 `souwen.web.fetch`，数据源选择统一来自 `souwen.registry`（单一事实源）。新增数据源不需要改路由，参见 [adding-a-source.md](./adding-a-source.md)。

> **⚠️ 声明：本项目仅供 Python 学习与技术研究使用。**
> 涵盖的学习方向包括：API 对接与聚合、全栈开发（FastAPI + React）、爬虫技术（TLS 指纹 / 浏览器池化 / 反爬绕过）、CLI 开发（Rich / Click）、异步编程（asyncio / httpx）等。
> 请勿将本项目用于任何违反相关法律法规或第三方服务条款的用途。

## Python API

### 统一搜索入口

```python
from souwen import search, search_papers, search_patents, web_search
```

#### `search(query, domain="paper", **kwargs)` → `list[SearchResponse]`

统一调度器，根据 `domain` 路由到对应搜索函数。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | `str` | — | 搜索关键词；会先 `strip()`，strip 后不能为空 |
| `domain` | `str` | `"paper"` | `"paper"` / `"patent"` / `"web"` |
| `**kwargs` | — | — | 传递给对应搜索函数 |

#### `search_papers(query, sources: str | list[str] | None = None, per_page=10, **kwargs)` → `list[SearchResponse]`

并发多源论文搜索。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | `str` | — | 搜索关键词；会先 `strip()`，strip 后不能为空 |
| `sources` | `str \| list[str] \| None` | `null`（registry `paper:search` 当前为 `["openalex", "crossref", "arxiv", "dblp", "pubmed", "biorxiv"]`） | 数据源或数据源列表；单个字符串会归一化为单元素列表 |
| `per_page` | `int` | `10` | 每个源返回结果数 |

#### `search_patents(query, sources: str | list[str] | None = None, per_page=10, **kwargs)` → `list[SearchResponse]`

并发多源专利搜索。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | `str` | — | 搜索关键词；会先 `strip()`，strip 后不能为空 |
| `sources` | `str \| list[str] \| None` | `null`（registry `patent:search` 当前为 `["google_patents"]`） | 数据源或数据源列表；单个字符串会归一化为单元素列表 |
| `per_page` | `int` | `10` | 每个源返回结果数 |

#### `web_search(query, engines: str | list[str] | None = None, max_results_per_engine=10)` → `WebSearchResponse`

并发多引擎网页搜索 + URL 去重。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | `str` | — | 搜索关键词；会先 `strip()`，strip 后不能为空 |
| `engines` | `str \| list[str] \| None` | `null`（registry `web:search` 当前为 `["duckduckgo", "bing"]`） | 引擎或引擎列表；单个字符串会归一化为单元素列表 |
| `max_results_per_engine` | `int` | `10` | 每个引擎最大结果数 |

搜索 source / engine 必须同时存在于 registry 且被当前 `SOUWEN_EDITION` 允许。省略 `sources` / `engines` 时，默认源会按 edition 静默过滤；显式点名当前 edition 不允许的 source / engine 会抛出 `EditionError`。REST API 会映射为 `403`。

### 网页内容抓取

```python
from souwen.web.fetch import fetch_content, validate_fetch_url
```

#### `fetch_content(urls: str | list[str], providers: str | list[str] | None = None, strategy="fallback", timeout=30.0, skip_ssrf_check=False, selector=None, start_index=0, max_length=None, respect_robots_txt=False)` → `FetchResponse`

多提供者内容抓取，支持 24 个提供者。默认 `fallback` 按 URL 补抓失败项；`fanout` 会并发执行所有 provider，并返回全部 provider 结果，适合质量对比和调试。provider 必须同时存在于 registry 且被当前 `SOUWEN_EDITION` 允许；重运行时 provider（如 `crawl4ai` / `scrapling` / `newspaper` / `readability` / `arxiv_fulltext`）需要 `full`。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `urls` | `str \| list[str]` | — | 目标 URL 或 URL 列表；单个字符串会归一化为单元素列表 |
| `providers` | `str \| list[str] \| None` | `["builtin"]` | 提供者或提供者列表；单个字符串会归一化为单元素列表。提供者: builtin / jina_reader / arxiv_fulltext / tavily / firecrawl / xcrawl / kimi_code / exa / metaso / crawl4ai / scrapling / scrapfly / diffbot / scrapingbee / zenrows / scraperapi / apify / cloudflare / wayback / newspaper / readability / mcp / site_crawler / deepwiki |
| `strategy` | `"fallback" \| "fanout"` | `"fallback"` | 多 provider 策略：`fallback` 按 URL 顺序补失败项；`fanout` 返回所有 provider 结果 |
| `timeout` | `float` | `30.0` | 每个 URL 超时秒数 |
| `skip_ssrf_check` | `bool` | `False` | 跳过 SSRF 校验（仅内部使用） |
| `selector` | `str \| None` | `None` | CSS 选择器，仅提取匹配元素（builtin / scrapling 支持） |
| `start_index` | `int` | `0` | 内容起始切片位置 |
| `max_length` | `int \| None` | `None` | 内容最大长度，超出则截断 |
| `respect_robots_txt` | `bool` | `False` | 是否遵守 robots.txt（provider 支持时生效） |

#### `validate_fetch_url(url)` → `tuple[bool, str]`

SSRF 防护 URL 校验（DNS 解析 + 非规范 IPv4 数字写法拒绝 + 私有/保留 IP 拦截）。

### Citation enrichment

```python
from souwen import get_citation_count, get_incoming_citations, get_references
```

OpenCitations 是 citation enrichment，不是关键词 paper search，也不会加入
`search_papers()` 默认 fan-out。`identifier` 支持 DOI、PMID 或 OMID；裸 DOI 与
`https://doi.org/...` 会规范化为 `doi:...`。`max_edges` 是 SouWen 的本地输出上限，
不是 OpenCitations upstream pagination；响应的 `truncated=true` 表示只返回了本地上限内的边。

| Python API | 返回值 | 说明 |
|---|---|---|
| `get_citation_count(identifier)` | `CitationCountResponse` | 被引计数 |
| `get_incoming_citations(identifier, max_edges=100)` | `CitationGraphResponse` | incoming citation edges |
| `get_references(identifier, max_edges=100)` | `CitationGraphResponse` | outgoing reference edges |

Citation data 带 OpenCitations source URL、OCI、retrieval time 及 `CC0-1.0` rights；它们不表示被引作品的全文访问、开放获取或再分发许可。

### 配置管理

```python
from souwen import get_config, reload_config
```

#### `get_config()` → `SouWenConfig`

获取全局配置单例（`@lru_cache` 缓存）。

#### `reload_config()` → `SouWenConfig`

清除缓存并重新加载配置。

### PDF 全文获取

```python
from souwen.paper import fetch_pdf
```

#### `fetch_pdf(paper)` → `Path | None`

5 级回退链自动获取论文 PDF：

1. `paper.pdf_url` 直接下载
2. Unpaywall OA 查询
3. CORE 全文查询
4. DOI 重定向解析
5. Sci-Hub 回退

## 数据模型

### PaperResult

```python
class PaperResult(BaseModel):
    source: str                     # 数据来源
    title: str                      # 标题
    authors: list[Author]           # 作者列表
    abstract: str | None            # 摘要
    doi: str | None                 # DOI
    year: int | None                # 发表年份
    publication_date: date | None   # 发表日期
    journal: str | None             # 期刊
    venue: str | None               # 会议/期刊
    citation_count: int | None      # 引用次数
    open_access_url: str | None     # OA 链接
    pdf_url: str | None             # PDF 链接
    source_url: str                 # 源链接
    tldr: str | None                # TLDR 摘要（Semantic Scholar）
    raw: dict                       # 原始响应
```

### PatentResult

```python
class PatentResult(BaseModel):
    source: str                     # 数据来源
    title: str                      # 标题
    patent_id: str                  # 公开号/申请号
    application_number: str | None  # 申请号
    publication_date: date | None   # 公开日
    filing_date: date | None        # 申请日
    applicants: list[Applicant]     # 申请人
    inventors: list[str]            # 发明人
    abstract: str | None            # 摘要
    claims: str | None              # 权利要求
    ipc_codes: list[str]            # IPC 分类号
    cpc_codes: list[str]            # CPC 分类号
    family_id: str | None           # 专利族 ID
    legal_status: str | None        # 法律状态
    pdf_url: str | None             # PDF 链接
    source_url: str                 # 源链接
    raw: dict                       # 原始响应
```

### WebSearchResult

```python
class WebSearchResult(BaseModel):
    source: str                     # 数据来源
    title: str                      # 标题
    url: str                        # 链接
    snippet: str                    # 摘要片段
    engine: str                     # 搜索引擎名
    raw: dict                       # 原始响应
```

### FetchResult

```python
class FetchResult(BaseModel):
    url: str                                    # 请求 URL
    final_url: str                              # 重定向后最终 URL
    title: str = ""                             # 页面标题
    content: str = ""                           # 提取正文（优先 Markdown）
    content_format: Literal["markdown", "text", "html"] = "markdown"
    content_truncated: bool = False             # 内容是否因 max_length 被截断
    next_start_index: int | None = None          # 续读起点（仅截断时设置）
    source: str = ""                            # 提供者标识
    snippet: str = ""                           # 摘要（前 500 字）
    published_date: str | None = None           # 发布日期
    author: str | None = None                   # 作者
    error: str | None = None                    # 错误信息（无错误为 None）
    raw: dict = {}                              # 原始响应
```

### FetchResponse

```python
class FetchResponse(BaseModel):
    urls: list[str]                             # 请求 URL 列表
    results: list[FetchResult]                  # 抓取结果
    total: int = 0                              # 总数
    total_ok: int = 0                           # 成功数
    total_failed: int = 0                       # 失败数
    providers: list[str] = []                   # 请求的提供者列表
    strategy: str = "fallback"                  # 使用的抓取策略
    provider: str | None = None                 # Deprecated: 单 provider 摘要字段；2.1.0 GA 后移除
    meta: dict = {}                             # 元数据
```

> `FetchResponse.provider` 仅为 v2.0 RC 过渡字段。新代码应读取
> `providers`、`meta.selected_provider` 和每条 `FetchResult.source`。
> 模型会在单 provider 响应中自动同步 `provider` 与 `providers[0]`，多 provider
> 响应仍保持 `provider: null`。

### SearchResponse

```python
class SearchResponse(BaseModel):
    query: str                      # 搜索词
    source: str                     # 数据来源
    total_results: int | None       # 总结果数
    results: list[PaperResult] | list[PatentResult] | list[WebSearchResult]
    page: int = 1                   # 当前页
    per_page: int = 10              # 每页数量
```

### Author / Applicant

```python
class Author(BaseModel):
    name: str
    affiliation: str | None = None
    orcid: str | None = None

class Applicant(BaseModel):
    name: str
    country: str | None = None
```

## CLI 命令

### 搜索

```bash
# 图书搜索（work 级书目）
souwen search book <query> [--sources/-s SRC1,SRC2] [--limit/-n 5] [--json/-j]

# 论文搜索
souwen search paper <query> [--sources/-s SRC1,SRC2] [--limit/-n 5] [--json/-j]

# 专利搜索
souwen search patent <query> [--sources/-s SRC1,SRC2] [--limit/-n 5] [--json/-j]

# 网页搜索
souwen search web <query> [--engines/-e ENG1,ENG2] [--limit/-n 10] [--json/-j]
```

输出格式：
- 默认：Rich 表格（论文显示 Title/Year/Citations/DOI/Source）
- `--json`：JSON 格式（适合管道处理，如 `| jq '.[]'`）

### 配置

```bash
souwen config show    # 显示当前配置（API Key 脱敏）
souwen config init    # 生成 souwen.yaml 模板
souwen config backend [--default auto|curl_cffi|httpx] [--set source=backend]
souwen config proxy [--proxy URL] [--add-pool URL] [--remove-pool URL]
souwen config source <name> [--enable/--disable] [--proxy inherit|none|warp|URL]
souwen config source <name> [--backend auto|curl_cffi|httpx] [--base-url URL]
```

`config backend` 的 `--default` 以及 `--set source=backend` 中的 `source` / `backend`
会先清理首尾空白，再校验合法值。
`config proxy` 的 `--proxy`、`--add-pool`、`--remove-pool` 会先清理 URL 首尾空白；
`--proxy` 为空会清除当前全局代理，`--add-pool` / `--remove-pool` 清理后不能为空。
`config source` 的 `<name>`、`--proxy`、`--backend`、`--base-url` 会先清理首尾空白。
`--proxy` 接受 `inherit` / `none` / `warp` 或合法代理 URL；`--base-url` 仅接受
`http` / `https` URL。CLI 修改只影响当前进程，持久化仍需写入 `souwen.yaml`。

### 数据源

```bash
souwen sources                         # 列出公开 Source Catalog
souwen sources --json                  # 输出与 /api/v1/sources 一致的 JSON
souwen sources --available-only        # 仅列出静态 gate 与当前 runtime 均可用的源
souwen sources --category web_general  # 按正式 catalog category 过滤
souwen sources --capability search     # 按能力过滤
```

### 健康检查

```bash
souwen doctor                  # 检查所有数据源静态状态（默认 live=false，不联网）
souwen doctor --live --source openalex --timeout 5
souwen doctor edition          # 检查当前 edition 声明能力与可用能力
souwen doctor edition --json   # 输出 machine-readable edition 自检结果
```

`souwen doctor` 默认只做本地配置、registry、edition 和依赖可导入性检查，不访问真实外部服务。
加 `--live` 后会对静态可用且支持 `search` capability 的源执行最小真实搜索探测；
`--source` 可重复传入以限制探测范围，`--timeout` 控制单源超时。

`doctor edition --json` 的 `probe` 字段只做当前进程的 importability 级别自检，
用于对比 source、fetch provider、optional package extra、LLM protocol、MCP 和预装插件的声明能力与实际安装能力；
其中 `probe.package_extras` 以 `declared` / `available` / `reason` 暴露 optional extra 到 import module 的映射和缺失原因。该自检不会联网、启动浏览器、检查 WARP 系统状态或验证真实凭据。

### 内容抓取

```bash
# 抓取网页内容（默认 builtin，零配置）
souwen fetch <urls...> [--provider/-p builtin] [--strategy fallback] [--timeout/-t 30] [--json/-j]

# 示例
souwen fetch https://example.com                      # 内置抓取
souwen fetch https://a.com https://b.com -p jina_reader  # Jina Reader
souwen fetch https://example.com -p builtin -p jina_reader --strategy fallback  # 逐 URL 补抓
souwen fetch https://example.com -p builtin -p jina_reader --strategy fanout    # 多 provider 对比
souwen fetch https://example.com --json               # JSON 输出
```

### API 服务

```bash
souwen serve [--port 8000]   # 启动 FastAPI 服务
```

启动后可访问 OpenAPI 文档：`GET /docs`

### 插件管理

```bash
souwen plugins list [--health]            # 列出所有插件，--health 附加健康检查列
souwen plugins info <name>                # 查看插件详情
souwen plugins enable <name>              # 启用（重启后生效）
souwen plugins disable <name>             # 禁用并尽力卸载运行时（重启后完全生效）
souwen plugins health <name>              # 调用插件 health_check（与 API 同源）
souwen plugins reload                     # 重新扫描 entry-point 插件（追加加载）
souwen plugins install <package>          # 通过 pip 安装（需 SOUWEN_ENABLE_PLUGIN_INSTALL=1）
souwen plugins uninstall <package>        # 卸载（同上）
souwen plugins new <name>                 # 生成插件项目骨架
```

`plugins` 命令会清理 `<name>` / `<package>` 的首尾空白，清理后为空会直接失败。
`plugins new <name>` 还要求 `<name>` 是小写字母开头、字母或数字结尾，
仅含小写字母/数字/下划线，且不能是 Python 关键字。
`install` / `uninstall` 失败时不会把 raw pip 输出打印到终端，只显示标准化错误；
`reload` 失败项也只显示插件名和标准化错误，不打印插件加载异常原文；存在失败项时
CLI 以非零退出码结束。

完整生命周期、目录机制与故障排查请见 [plugin-management.md](./plugin-management.md)。

## HTTP API（Server 模式）

### 认证：三角色系统

SouWen 支持三级角色认证（Guest/User/Admin）：

| 角色 | Token 来源 | 可访问端点 |
|------|------------|-----------|
| Guest 游客 | 无 Token（需 `guest_enabled=true`） | 搜索（受限源、限速） |
| User 用户 | `user_password` | 搜索 + `/api/v1/sources` + `/api/v1/doctor` |
| Admin 管理员 | `admin_password` | 全部端点 |

**密码优先级：**

- 用户端点：`user_password` > Guest 开关 > 拒绝访问
- 管理端点：`admin_password` > 本地显式开放开关 > 拒绝访问
- Admin Token 自动满足所有低级别端点（Admin ⊃ User ⊃ Guest）
- 显式将 `user_password` 设为空字符串 `""` 表示开放用户端点；生产部署应设置 `admin_password`。

**请求格式：** `Authorization: Bearer <password>`

若上游代理必须占用标准 `Authorization`（例如 private Hugging Face Space 使用 HF READ
token 通过 edge），可以把 SouWen 应用层密码放在 `X-SouWen-Token: <password>`。该 header
是上游代理专用通道，不替代普通部署的 Bearer 约定；两个 header 同时存在时 custom header
优先，显式无效值不会回退到 `Authorization`。外层 HF token 与内层 SouWen admin password
必须使用不同 secrets，不能复用。

**角色自检：** `GET /api/v1/whoami` — 返回当前角色、角色权限 `features`、当前 `edition` 和独立的 `edition_capabilities`，用于前端 UI 动态渲染。`features` 表示当前 token 角色是否可访问某类端点；`edition_capabilities` 表示当前 `SOUWEN_EDITION` 是否包含 LLM、WARP 模式、fetch provider，以及当前运行环境是否检测到 full 版预装插件候选包。

`/whoami` 还会返回鉴权状态字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `guest_enabled` | `bool` | 当前配置是否允许 Guest 角色 |
| `user_password_set` | `bool` | 当前是否配置了有效 `user_password` |
| `admin_password_set` | `bool` | 当前是否配置了有效 `admin_password` |
| `admin_open` | `bool` | 当前请求是否通过无密码 admin-open 模式获得 Admin 角色；只有未配置 `admin_password` 且显式设置 `SOUWEN_ADMIN_OPEN=1` 时才应为 `true` |

> ⚠️ 当未设置管理密码时，管理端点默认拒绝访问。仅在本地开发或 CI 冒烟测试中使用 `SOUWEN_ADMIN_OPEN=1` 显式开放；生产部署务必设置 `admin_password`。

### 错误响应格式

所有 4xx/5xx 错误统一为：

```json
{
  "error": "rate_limited",
  "detail": "请求过于频繁，每 60 秒最多 60 次",
  "request_id": "a1b2c3d4e5f6"
}
```

`error` 字段（机器可读错误码）映射：

| HTTP 状态码 | error 码 |
|-------------|----------|
| 400 | `bad_request` |
| 401 | `unauthorized` |
| 403 | `forbidden` |
| 404 | `not_found` |
| 422 | `validation_error` |
| 429 | `rate_limited` |
| 500 | `internal_error` |
| 502 | `bad_gateway` |
| 503 | `service_unavailable` |
| 504 | `gateway_timeout` |
| 其他 | `error` |

### 速率限制

搜索端点（`/api/v1/search/*`）默认 **60 请求 / 60 秒 / IP**（基于内存滑动窗口）。
当配置了 `trusted_proxies`（CIDR 列表）时，会从受信代理转发的 `X-Forwarded-For` 提取真实 IP，否则使用 TCP 直连地址。

触发限流时返回 `429`，并附带以下响应头：

| 响应头 | 含义 |
|--------|------|
| `Retry-After` | 建议重试前等待的秒数 |
| `X-RateLimit-Limit` | 窗口内最大请求数 |
| `X-RateLimit-Remaining` | 窗口内剩余配额（429 时为 `0`） |
| `X-RateLimit-Reset` | 配额重置的 Unix 时间戳（秒） |

### 基础端点

#### `GET /health`

健康检查，无需认证。用于容器编排（K8s）存活探针。

**响应示例：**
```json
{
  "status": "ok",
  "version": "2.0.0rc1",
  "source_sha": "0123456789abcdef0123456789abcdef01234567"
}
```

> `version` 动态返回当前 `souwen.__version__`。`source_sha` 是可选 runtime provenance：
> 只接受 `SOUWEN_SOURCE_SHA` 或 `runtime.source.sha` 提供的 40 位 Git SHA，并统一为
> 小写；本地源码运行、未注入或值不合法时为 `null`。Release/container/binary 验收必须
> 将非空 `source_sha` 与 immutable candidate SHA 比对，版本相同不能替代 SHA 证明。

#### `GET /readiness`

K8s readiness 探针。仅做本地检查（配置可加载 + 数据源注册表非空），不触发任何网络调用，避免探针超时。

**响应示例（就绪）：**
```json
{
  "ready": true,
  "version": "2.0.0rc1",
  "source_sha": "0123456789abcdef0123456789abcdef01234567",
  "error": null
}
```

**响应示例（503 未就绪）：**
```json
{
  "ready": false,
  "version": "2.0.0rc1",
  "source_sha": null,
  "error": "source registry is empty"
}
```

`source_sha` 的来源、格式和 RC 比对规则与 `/health` 相同；`ready=true` 只证明本地配置与
registry 就绪，不证明外部 provider live 可达。

#### `GET /` 与 `GET /panel`

- 当 `expose_docs=true`（默认）时，`GET /` 重定向到 `/docs`（Swagger UI）。
- 当 `expose_docs=false` 时，`GET /` 返回 JSON 元信息（`{name, version, panel, docs}`）。
- `GET /panel` 返回管理面板 HTML（不含在 OpenAPI schema 中）；浏览器侧的完整入口通常写作 `/panel#/`，其中 `#` 后内容由前端 router 处理。

`/panel` 的 HTML 经内存缓存，并附带：

```
ETag: "<sha256-16hex>"
Cache-Control: public, max-age=3600
```

客户端在 `If-None-Match` 命中时返回 **304 Not Modified**（仅头部 `ETag`，无响应体）。支持 RFC 7232 通配符 `*` 和逗号分隔的 ETag 列表。

---

### 搜索端点 (`/api/v1/...`)

受 `check_search_auth` 与 `rate_limit_search` 双重保护。
搜索 source / engine 必须存在于 registry 且被当前 `SOUWEN_EDITION` 允许。默认源会按 edition 过滤；显式请求当前 edition 不允许的 source / engine 返回 `403`。

#### `GET /api/v1/search/book`

搜索 work 级图书书目。默认 source 由 registry `book:search` 派生，当前仍只有
`open_library`；Internet Archive 和 Wikisource 都必须显式传入相应的
`sources=internet_archive` 或 `sources=wikisource`，不加入默认 fan-out。Wikisource search
只允许 `zh` / `en` 站点，默认 `zh`；REST search 只返回目录 metadata，不读取页面正文、revision
或子页。要读取一个明确页面及有界 revision，请使用 Python API
`get_wikisource_page_detail()`，而不是假定存在 REST detail endpoint。

搜索结果包含 typed identifiers、受限 edition metadata、`collections` 馆藏归属和 resource
access state。Internet Archive 的文件链接只是外部资源元数据，不会触发借阅、阅读或下载；
Wikisource 的 `content_format`、正文 size / truncation、页面与 revision provenance，以及站点
贡献许可和底本 rights 都是不同字段/证据层。两者都不从外部链接或站点托管本身推断下载、全球
public domain 或再分发权利；Wikisource runtime 不导入 dumps，也不递归遍历页面或子页。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `q` | string (1-500) | *(必填)* | 搜索关键词；会先 `strip()`，strip 后不能为空 |
| `sources` | string \| null | `null`（registry `book:search`） | 数据源列表，逗号分隔 |
| `per_page` | int (1-100) | `10` | 每个数据源返回结果数 |
| `timeout` | float (1-300) \| null | `null` | 端点硬超时（秒），超时返回 504 |

**错误状态码：** `403 forbidden`（source 存在但当前 edition 不允许）、`502 bad_gateway`（所有数据源均失败）、`504 gateway_timeout`（超过 `timeout`）。

#### `GET /api/v1/search/paper`

#### `GET /api/v1/citations/count`

Query parameter `identifier` is a DOI, PMID or OMID. Returns typed citation count metadata.

#### `GET /api/v1/citations/incoming`

Query parameter `identifier`; optional `max_edges` (1..1000) is a local output cap, not upstream pagination.

#### `GET /api/v1/citations/references`

Query parameter `identifier`; optional `max_edges` uses the same local-cap semantics as incoming edges.

搜索学术论文（多源并联）。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `q` | string (1-500) | *(必填)* | 搜索关键词；会先 `strip()`，strip 后不能为空 |
| `sources` | string \| null | `null`（registry `paper:search` 当前为 `openalex,crossref,arxiv,dblp,pubmed,biorxiv`） | 数据源列表，逗号分隔 |
| `per_page` | int (1-100) | `10` | 每个数据源返回结果数 |
| `timeout` | float (1-300) \| null | `null` | 端点硬超时（秒），超时返回 504；`null` 表示无超时 |

**响应示例：**
```json
{
  "query": "transformer",
  "sources": ["openalex", "arxiv"],
  "results": [ ... ],
  "total": 20,
  "meta": {
    "requested": ["openalex", "arxiv"],
    "succeeded": ["openalex", "arxiv"],
    "failed": []
  }
}
```

**错误状态码：** `403 forbidden`（source 存在但当前 edition 不允许）、`502 bad_gateway`（所有数据源均失败）、`504 gateway_timeout`（超过 `timeout`）。

#### `GET /api/v1/search/patent`

搜索专利。参数与 paper 一致，仅默认源不同：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `q` | string (1-500) | *(必填)* | 搜索关键词；会先 `strip()`，strip 后不能为空 |
| `sources` | string \| null | `null`（registry `patent:search` 当前为 `google_patents`） | 数据源列表，逗号分隔 |
| `per_page` | int (1-100) | `10` | 每个数据源返回结果数 |
| `timeout` | float (1-300) \| null | `null` | 端点硬超时（秒），超时返回 504 |

#### `GET /api/v1/search/web`

搜索网页（多引擎并联 + URL 去重）。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `q` | string (1-500) | *(必填)* | 搜索关键词；会先 `strip()`，strip 后不能为空 |
| `engines` | string \| null | `null`（registry `web:search` 当前为 `duckduckgo,bing`） | 搜索引擎，逗号分隔 |
| `per_page` | int (1-50) | `10` | 每引擎最大结果数（**主名称**） |
| `max_results` | int (1-50) \| null | `null` | `per_page` 的别名；显式提供时**优先级高于 `per_page`** |
| `timeout` | float (1-300) \| null | `null` | 端点硬超时（秒），超时返回 504 |

> 新调用建议使用 `per_page`，以便和论文、专利搜索端点保持一致。

**错误状态码：** `403 forbidden`（engine 存在但当前 edition 不允许）、`502 bad_gateway`（所有搜索引擎均失败）、`504 gateway_timeout`（超过 `timeout`）。

#### `POST /api/v1/search/web/enriched`

以显式、已注册的 concrete LLM-search source 搜索资料，再可选地通过既有 SSRF-safe
`fetch_content()` 管线补充正文摘录。该接口是对 `GET /api/v1/search/web` 的**新增**能力；旧
GET endpoint 的请求和响应契约不变。

请求中的 `sources` 只接受 Registry 注册的 concrete source ID。每个 source 已固定绑定
scheme 与 model，因此接口不接受 `model`、`model_id`、`scheme_id`、`api_key` 或
`base_url`。默认 `source_strategy="single"` 时必须只提供一个 source；`fanout` 和
`first_success` 必须显式指定。

**请求字段：**

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | string (1-500) | *(必填)* | 搜索关键词；首尾空白会移除 |
| `sources` | string[] (1-10) | *(必填)* | concrete source IDs；不能重复 |
| `source_strategy` | `single` \| `fanout` \| `first_success` | `single` | `single` 必须恰好一个 source |
| `max_results_per_source` | int (1-50) | `10` | 每次 source attempt 的结果上限 |
| `deduplicate` | boolean | `true` | 按 canonical URL 合并 discovery provenance |
| `fetch.enabled` | boolean | `true` | 是否调用安全 fetch 管线 |
| `fetch.providers` | string[] \| null | `null` | 可选 fetch provider allowlist，不传则沿用 fetch 默认策略 |
| `fetch.strategy` | `fallback` \| `fanout` | `fallback` | fetch provider 调度策略 |
| `fetch.max_pages` | int (1-20) | `5` | 最多抓取的去重页面数 |
| `fetch.max_excerpt_chars` | int (1-4000) | `500` | 每条 extractive excerpt 字符上限 |
| `fetch.include_content` | boolean | `false` | 是否返回有界的真实正文 |
| `fetch.max_content_chars` | int (1-20000) | `4000` | 每条正文字符上限 |
| `budget.max_total_seconds` | float (1-300) | `120` | 搜索与 fetch 的共享端点硬超时 |
| `budget.max_source_attempts` | int (1-10) | `1` | 最多执行的 concrete source attempt 数 |

**响应语义：**

- `results[]` 只包含通过非空 title + HTTP(S) URL 硬门槛的资料。`discoveries[]` 保留每条
  source provenance；不会返回 provider raw response、gateway URL 或凭据。
- `meta.source_outcomes` 区分 `success_with_results`、`success_empty`、`timeout` 与
  `failed`。至少一个 source 成功时返回 `200`，其余失败以 `meta.partial=true` 表示。
- `meta.visible_search_calls` 只统计响应中可见的 search call；它不是费用推断。provider
  未明确给出 metered calls 或 cost 时，相应字段为 `null`，不会伪造 `0`。
- `usage` 为本阶段的保守 usage 视图；synthesis 尚未启用，token/cost 字段可为 `null`。

**错误状态码：** `422 unprocessable_entity`（未知 source、非 concrete source、非法
identity override 或请求字段不合规）、`403 forbidden`（当前 edition 不允许）、`409 conflict`
（source 默认关闭或被显式禁用）、`502 bad_gateway`（所有 source 都不可用）、`504
gateway_timeout`（共享 budget 耗尽；未完成任务会被取消）。

#### `GET /api/v1/sources`

列出公开 Source Catalog。未设置 `user_password` 时开放；设置 `user_password` 后要求 User+，即使启用 guest 模式也不降级开放。返回值从运行时 live registry 派生，内置源和运行时插件都以 `sources[]` 列表返回；源被禁用、必须凭据缺失、自建实例未配置或当前 `SOUWEN_EDITION` 不允许时仍保留 catalog 条目，但 `available=false`。Optional runtime importability 通过独立的 `runtime_available` / `runtime_reason` 返回，不改变既有字段 `available`；本地有效可执行性要求合取两轴。

**响应示例：**
```json
{
  "sources": [
    {
      "name": "openalex",
      "domain": "paper",
      "category": "paper",
      "capabilities": ["search"],
      "description": "OpenAlex 开放学术数据",
      "auth_requirement": "optional",
      "credential_fields": ["openalex_api_key"],
      "missing_credential_fields": ["openalex_api_key"],
      "credentials_satisfied": true,
      "configured_credentials": false,
      "config_valid": true,
      "config_reason": "",
      "risk_level": "low",
      "stability": "stable",
      "distribution": "core",
      "default_for": ["paper:search"],
      "min_edition": "pro",
      "edition_available": true,
      "edition_reason": "",
      "runtime_available": true,
      "runtime_reason": "",
      "available": true
    }
  ],
  "categories": [
    {
      "key": "paper",
      "label": "学术论文",
      "order": 10,
      "domain": "paper",
      "description": "论文、预印本、开放学术索引和文献库。"
    }
  ],
  "defaults": {
    "paper:search": ["openalex", "crossref", "arxiv", "dblp", "pubmed", "biorxiv"]
  }
}
```

关键字段语义：

| 字段 | 说明 |
|---|---|
| `sources[]` | 公开 Source Catalog 条目列表，前端和 CLI 应按 `domain`/`category`/`capabilities` 过滤 |
| `categories[]` | 正式展示分类，包含 `key`、`label`、`order`、`domain` 与说明 |
| `defaults` | `domain:capability` 到默认源名列表的映射 |
| `domain` | 能力归属域，如 `paper` / `patent` / `web` / `fetch` |
| `category` | 正式 catalog 分类，如 `web_general` / `web_professional` / `knowledge` |
| `capabilities` | 源声明的能力，如 `search` / `fetch` / `get_detail` |
| `auth_requirement` | 鉴权要求：`none` / `optional` / `required` / `self_hosted` |
| `credential_fields` | 完整凭据字段，多字段凭据会列出全部字段 |
| `missing_credential_fields` | 当前未配置或无效的字段路径；共享 gateway 使用 value-free dotted path，不返回配置值 |
| `credentials_satisfied` | 当前配置是否满足运行时凭据要求；免配置和可选凭据源为 `true` |
| `configured_credentials` | 用户是否实际配置了该源声明的凭据 |
| `config_valid` / `config_reason` | source 配置是否满足静态约束；无效 identity override 只返回 value-free 字段路径 |
| `min_edition` | 使用该源所需的最低功能档位：`basic` / `pro` / `full` |
| `edition_available` | 当前 `SOUWEN_EDITION` 是否允许该源 |
| `edition_reason` | `edition_available=false` 时的不可用原因；允许时为空字符串 |
| `runtime_available` | 当前进程能否加载 client implementation 与声明的 optional dependency；不联网、不检查凭据 |
| `runtime_reason` | `runtime_available=false` 时的缺依赖、稳定脱敏 loader 原因或 edition 未探测原因；公开响应不回显任意 loader exception 文本 |
| `available` | 静态 catalog gate：等于未禁用、`credentials_satisfied=true` 且 `edition_available=true`；不代表上游实时可达，也不等于 `stability` |
| `risk_level` | 默认调度风险：`low` / `medium` / `high` |
| `distribution` | 分发范围：`core` / `extra` / `plugin` |
| `stability` | Registry 声明的接入成熟度：`stable` / `beta` / `experimental` / `deprecated`；不是实时连通性结果 |

数据源 catalog 字段和运行时可见性的总览见 [data-sources.md](./data-sources.md)。

#### `GET /api/v1/doctor`

用户可读的数据源状态摘要，要求 User+ 权限（本地未配置 `user_password` 且未启用 guest 模式时按 User 处理）。返回字段与 `GET /api/v1/admin/doctor` 相同，但不提供任何写入能力。

可选 query 参数：

| 参数 | 类型 | 默认 | 说明 |
|---|---:|---:|---|
| `live` | `bool` | `false` | 显式执行真实联网探测；默认只返回静态配置状态 |
| `source` | `string[]` | — | `live=true` 时只探测指定 source，可重复 |
| `timeout` | `float` | `5.0` | 单源 live probe 超时秒数，范围 `0.5` 到 `60.0` |

默认 `live=false`，端点只评估 registry 声明、当前 edition、频道启用状态、凭据和
本地依赖，不访问外部服务；此时 `probe_mode="static"`、顶层 `live_probe=null`，
`sources[].live_probe` 也为 `null`。显式 `live=true` 时，只对静态可用且支持
`search` capability 的目标源执行最小真实搜索；顶层 `live_probe` 汇总本次
`ok` / `failed` / `skipped`，对应 `sources[].live_probe` 记录当次观测。未被选择或
不满足探测条件的源不会被伪装成 live success，live probe 也不会改写静态
`status`、`available` 或 registry `stability`。REST 响应保留超时、限流和失败等
观测类别，但不会回显 provider/loader 的任意 exception 文本；本地 CLI 仍可用于详细诊断。

顶层 `edition` 是当前 `SOUWEN_EDITION`，每个 `sources[]` 条目包含
`min_edition` / `edition_available` / `edition_reason`、`runtime_available` /
`runtime_reason`、`credentials_satisfied`、`config_available` / `config_reason` 和
`available`，用于把“需升级”“运行依赖缺失”“缺凭据”“手动禁用”和成熟度状态分开。
其中 `runtime_available` 只检查当前进程能否加载实现与声明的 optional dependency，
不会实例化 browser 或联网；当前 edition 明确禁止的源不会加载其 client/module，而是返回
`runtime_available=false` 与稳定的 `runtime not probed because ...` 原因。`config_available` 是
enabled 与 required credentials 的合取；
最终静态 `available` 是 edition、runtime、config 与可用 status 的合取。`available` 汇总
`ok` / `limited` / `warning` / `degraded`，`degraded_total` 统计
`limited` / `warning` / `degraded`；`degraded` 是 `degraded_total` 的同义字段，
精确状态计数请读取 `status_counts.degraded`。

---

### 管理端点 (`/api/v1/admin/...`)

> 管理端点由 `require_auth` 强制保护，验证 `admin_password`。
> 未设置管理密码时，管理端点默认返回 `401 Unauthorized`；只有设置 `SOUWEN_ADMIN_OPEN=1` 才会显式开放。

#### `GET /api/v1/admin/config`

查看当前配置。JSON 响应会递归脱敏敏感字段；字段名包含
`key` / `secret` / `token` / `password` / `auth` / `authorization` /
`cookie` / `sessdata` / `session` / `sid` / `jwt` / `csrf` / `xsrf`
等含义时，非空值显示为 `"***"`；snake_case、hyphen-case、camelCase
和常见 compact 写法（如 `apiKey` / `apikey` / `accessToken` /
`sessionid` / `csrftoken`）都会按敏感字段处理。非敏感字段中的 URL
也会遮蔽 userinfo 以及敏感 query/fragment 参数，例如代理 URL 中的
用户名、密码、`token`、`apiKey`。`llm_search_gateways` 属于额外保护的配置域：
其中每个 gateway 的 `base_url` 也始终显示为 `"***"`，避免暴露 private gateway 地址。

**响应示例：**
```json
{
  "admin_password": "***",
  "semantic_scholar_key": "***",
  "rate_limit_per_minute": 30,
  ...
}
```

#### `POST /api/v1/admin/config/reload`

重新加载配置（从 YAML 和环境变量）。

**响应示例：**
```json
{ "status": "ok", "password_set": true }
```

#### `GET /api/v1/admin/config/yaml`

读取当前 YAML 配置文件内容。若当前目录和用户配置目录都没有配置文件，则返回内置默认模板，`path=null`。

**响应示例：**
```json
{
  "content": "server:\n  host: 0.0.0.0\n  port: 49265\n",
  "path": "/home/user/.config/souwen/config.yaml"
}
```

#### `PUT /api/v1/admin/config/yaml`

保存 YAML 配置文件并重新加载。服务端会先做 YAML 语法校验、废弃鉴权字段检查和 `SouWenConfig` dry-run 校验，再原子写入配置文件；当前无配置文件时写入用户配置目录。dry-run 校验失败时，错误响应只返回字段路径和错误原因，不回显原始输入值。

**请求体：**
```json
{
  "content": "server:\n  host: 0.0.0.0\n  port: 49265\n"
}
```

**响应示例：**
```json
{
  "content": "server:\n  host: 0.0.0.0\n  port: 49265\n",
  "path": "/home/user/.config/souwen/config.yaml"
}
```

#### `GET /api/v1/admin/doctor`

管理员路径的数据源状态检查，query 参数、响应 shape 和 static/live 语义与
`GET /api/v1/doctor` 一致。默认 `live=false`，不会执行实时连通性探测；显式传
`live=true` 才会返回 `probe_mode="live"`、顶层 `live_probe` 汇总和对应的
`sources[].live_probe`。顶层 `edition` 是当前 `SOUWEN_EDITION`；每个
`sources[]` 条目分别返回 edition、runtime importability、configuration/credentials、
static status 与 live probe 轴。当源在当前 edition 不可用且未被手动禁用时，
`status="unavailable"` 且 `message` 为升级原因；runtime 缺失同样会静态
`unavailable`，但原因独立保存在 `runtime_reason`。静态 `available` 和声明式
`stability` 都不能当作 live 成功证据。

状态语义与 Panel 展示规则应以本节和管理端 schema 为准；面向用户的排障路径会在 GitHub Wiki 中提供。

下例展示未加载外部插件的干净 `edition=pro` 环境 static shape；具体状态计数会随 edition、
已安装 optional dependency、频道启用和凭据配置变化。此条件下 `total=97` 对应当前内置
registered catalog；加载外部插件后 `total` 会随 live registry 增加。

**响应示例：**
```json
{
  "total": 97,
  "ok": 39,
  "available": 50,
  "degraded": 11,
  "degraded_total": 11,
  "failed": 45,
  "limited": 9,
  "warning": 2,
  "missing_key": 40,
  "unavailable": 5,
  "disabled": 0,
  "edition": "pro",
  "probe_mode": "static",
  "live_probe": null,
  "status_counts": {
    "ok": 39,
    "limited": 9,
    "warning": 2,
    "missing_key": 40,
    "unavailable": 5
  },
  "sources": [
    {
      "name": "openalex",
      "category": "paper",
      "status": "limited",
      "integration_type": "open_api",
      "required_key": "openalex_api_key",
      "key_requirement": "optional",
      "auth_requirement": "optional",
      "credential_fields": ["openalex_api_key"],
      "optional_credential_effect": "quota",
      "risk_level": "low",
      "risk_reasons": [],
      "distribution": "core",
      "package_extra": null,
      "stability": "stable",
      "usage_note": "Freemium API；无 Key 预算较低，耗尽返回 429；openalex_email 不再发送",
      "min_edition": "pro",
      "edition": "pro",
      "edition_available": true,
      "edition_reason": "",
      "runtime_available": true,
      "runtime_reason": "",
      "credentials_satisfied": true,
      "config_available": true,
      "config_reason": "",
      "available": true,
      "message": "免配置可用；设置 openalex_api_key 可提升配额（Freemium API；无 Key 预算较低，耗尽返回 429；openalex_email 不再发送）",
      "live_probe": null
    },
    {
      "name": "semantic_scholar",
      "category": "paper",
      "status": "limited",
      "integration_type": "official_api",
      "required_key": "semantic_scholar_api_key",
      "key_requirement": "optional",
      "credential_fields": ["semantic_scholar_api_key"],
      "optional_credential_effect": "rate_limit",
      "min_edition": "pro",
      "edition": "pro",
      "edition_available": true,
      "edition_reason": "",
      "runtime_available": true,
      "runtime_reason": "",
      "credentials_satisfied": true,
      "config_available": true,
      "config_reason": "",
      "available": true,
      "message": "免配置可用；设置 semantic_scholar_api_key 可提升限流"
    }
  ]
}
```

#### `GET /api/v1/admin/ping`

轻量管理端存活探测。该端点仍受 Admin Bearer Token 保护，用于确认认证链路和管理路由可用。

**响应示例：**
```json
{ "status": "ok" }
```

#### `GET /api/v1/admin/warp`

获取 WARP 代理当前状态；`last_error` 等自由文本会先做敏感信息脱敏，避免返回代理凭据、token、Cookie 或 session 值；文本中的 URL 也会掩码敏感 query/fragment 参数值。

**响应示例：**
```json
{
  "status": "enabled",
  "mode": "wireproxy",
  "owner": "shell",
  "socks_port": 1080,
  "http_port": 0,
  "ip": "104.28.x.x",
  "pid": 12345,
  "protocol": "wireguard",
  "proxy_type": "socks5"
}
```

#### `GET /api/v1/admin/warp/modes`

列出所有 WARP 模式的可用性、协议、代理类型、部署要求和 edition 约束。

**模式：** `wireproxy` / `kernel` / `usque` / `warp-cli` / `external`

`basic` 只允许 `auto`、`wireproxy` 和 `external`；`pro` / `full` 可使用全部模式。
管理端仍返回所有模式，并通过 `min_edition`、`edition_available`、`edition_reason`
说明当前 `SOUWEN_EDITION` 是否允许该模式。

`external` 模式返回的代理展示 URL 会掩码 URL 中的用户名、密码和敏感 query/fragment 参数值。

**响应示例：**
```json
{
  "modes": [
    {
      "id": "usque",
      "name": "usque (MASQUE/QUIC)",
      "protocol": "masque",
      "installed": true,
      "requires_privilege": false,
      "docker_only": false,
      "proxy_types": ["socks5", "http"],
      "min_edition": "pro",
      "edition_available": true,
      "edition_reason": "",
      "description": "MASQUE/QUIC 协议，现代化方案，支持 SOCKS5 和 HTTP 代理"
    }
  ]
}
```

#### `POST /api/v1/admin/warp/enable`

启用 Cloudflare WARP 代理；失败响应会脱敏底层错误中的代理凭据、token、Cookie 和 session 值；错误文本中的 URL 也会掩码敏感 query/fragment 参数值。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `mode` | string | `"auto"` | 模式: `auto` / `wireproxy` / `kernel` / `usque` / `warp-cli` / `external` |
| `socks_port` | int (1-65535) | `1080` | SOCKS5 端口 |
| `http_port` | int (0-65535) | `0` | HTTP 代理端口（`0` 表示不启用；适用于 `usque` 等支持 HTTP 代理的模式） |
| `endpoint` | string \| null | `null` | 自定义 WARP Endpoint |

**响应示例：**
```json
{ "ok": true, "mode": "wireproxy", "ip": "104.28.x.x" }
```

**错误响应 (400)：**
```json
{ "detail": "wireproxy binary not found" }
```

**错误状态码：** `403`（目标模式存在但当前 edition 不允许）、`400`（未知模式、组件缺失或启动失败）。

#### `POST /api/v1/admin/warp/register`

注册新的 Cloudflare WARP 账号。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `backend` | string | `"wgcf"` | 注册后端：`wgcf`（WireGuard 配置）/ `usque`（MASQUE 配置） |

**响应示例：**
```json
{ "ok": true, "backend": "wgcf", "config_path": ".../wgcf-raw.conf" }
```

#### `POST /api/v1/admin/warp/test`

测试当前 WARP 代理连接，返回出口 IP、端口、模式与协议。

**响应示例：**
```json
{
  "ok": true,
  "ip": "104.28.x.x",
  "port": 1080,
  "mode": "usque",
  "protocol": "masque",
  "proxy_type": "both"
}
```

#### `GET /api/v1/admin/warp/config`

获取当前 WARP 相关配置项；`warp_license_key` 和 `warp_team_token` 仅返回是否已配置，代理 URL 中的用户名、密码和敏感 query/fragment 参数值会被掩码。

**响应示例：**
```json
{
  "warp_enabled": false,
  "warp_mode": "auto",
  "warp_socks_port": 1080,
  "warp_http_port": 0,
  "warp_endpoint": null,
  "warp_bind_address": "127.0.0.1",
  "warp_startup_timeout": 15,
  "warp_device_name": null,
  "warp_usque_transport": "auto",
  "warp_external_proxy": null,
  "warp_usque_path": null,
  "warp_usque_config": null,
  "warp_gost_args": null,
  "has_license_key": false,
  "has_team_token": false,
  "has_proxy_auth": false
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `warp_bind_address` | string | 代理监听地址，例如 `127.0.0.1` 或 `0.0.0.0` |
| `warp_startup_timeout` | int | 启动后健康检查等待秒数 |
| `warp_device_name` | string \| null | 注册 WARP 时使用的设备标识 |
| `warp_usque_transport` | string | `usque` 传输模式：`auto` / `quic` / `http2` |
| `has_proxy_auth` | bool | 是否已配置 `warp_proxy_username` / `warp_proxy_password` |

#### `GET /api/v1/admin/warp/components`

列出运行时可管理的 WARP 组件安装状态，覆盖 `usque`、`wireproxy`、`wgcf` 等二进制。

**响应示例：**
```json
{
  "components": [
    {
      "name": "usque",
      "installed": true,
      "version": "3.0.0",
      "path": "/app/data/bin/usque"
    }
  ]
}
```

#### `POST /api/v1/admin/warp/components/install`

从 GitHub Releases 下载并安装指定 WARP 组件。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `component` | string | *(必填)* | 组件名：`usque` / `wireproxy` / `wgcf` |
| `version` | string \| null | `null` | 版本号；留空使用内置默认版本 |

#### `POST /api/v1/admin/warp/components/uninstall`

卸载运行时安装的 WARP 组件，不影响系统或镜像预装组件。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `component` | string | *(必填)* | 组件名 |

#### `POST /api/v1/admin/warp/disable`

禁用 WARP 代理；失败响应会脱敏底层错误中的代理凭据、token、Cookie 和 session 值；错误文本中的 URL 也会掩码敏感 query/fragment 参数值。

**响应示例：**
```json
{ "ok": true }
```

#### `POST /api/v1/admin/warp/switch`

一步切换 WARP 模式：先禁用当前模式，再以目标模式启动。失败时不会返回底层敏感错误，详细信息保留在服务端日志。
目标模式受 `SOUWEN_EDITION` 约束；当前 edition 不允许时返回 `403`，且不会先禁用现有 WARP。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `mode` | string | *(必填)* | 目标模式：`wireproxy` / `kernel` / `usque` / `warp-cli` / `external` 等 |
| `socks_port` | int (1-65535) | `1080` | SOCKS5 端口 |
| `http_port` | int (0-65535) | `0` | HTTP 代理端口（`0` 表示不启用） |
| `endpoint` | string \| null | `null` | 自定义 WARP Endpoint |

#### `GET /api/v1/admin/warp/events`

WARP 状态变更 SSE 流。客户端使用 `EventSource` 连接，服务端约每 2 秒检查一次状态，状态变化或心跳周期到达时推送当前状态 JSON；推送的 `last_error` 同样会脱敏凭据、token、Cookie、session 值和 URL 中的敏感 query/fragment 参数值。

---

### 插件管理端点 (`/api/v1/admin/plugins/...`)

> 受 `require_auth` 强制保护。Web Panel 与 CLI（`souwen plugins ...`）共用这组端点，
> 完整的用户视角说明参见 [plugin-management.md](./plugin-management.md)。
> `{name}` 路径参数与请求体 `package` 字段会先做首尾空白清理；清理后为空返回 `422`，
> 不会继续调用插件管理器。

#### `GET /api/v1/admin/plugins`

列出所有已加载、可用、禁用的插件，并附带是否需要重启与 install 开关。

**响应示例：**
```json
{
  "plugins": [
    {
      "name": "superweb2pdf",
      "package": "superweb2pdf",
      "version": "0.3.1",
      "status": "loaded",
      "source": "entry_point",
      "first_party": true,
      "description": "SuperWeb2PDF — 网页截图转 PDF（基于 Playwright Chromium）",
      "error": null,
      "source_adapters": ["superweb2pdf"],
      "fetch_handlers": ["superweb2pdf"],
      "restart_required": false
    }
  ],
  "restart_required": false,
  "install_enabled": false
}
```

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| `plugins[*].status` | string | `loaded` / `available` / `disabled` / `error`；`available` 表示目录可见但当前进程未加载，若同时有 `version` 则说明包已安装、需要重新扫描或重启生效 |
| `plugins[*].source` | string | `entry_point` / `catalog` / `config_path` |
| `plugins[*].first_party` | bool | 是否为官方维护插件（来自目录元数据） |
| `restart_required` | bool | 服务端是否有任何 enable / disable / install / uninstall 操作未生效 |
| `install_enabled` | bool | 是否允许 `install` / `uninstall`（受 `SOUWEN_ENABLE_PLUGIN_INSTALL=1` 控制） |

#### `GET /api/v1/admin/plugins/{name}`

查询单个插件详情。`name` 不存在或未加载时返回 `404`；`name` 首尾空白会被清理。

#### `GET /api/v1/admin/plugins/{name}/health`

调用插件的 `health_check`。仅对已加载插件可用，未加载返回 `404`；插件未声明 `health_check` 时返回：

```json
{ "status": "ok", "message": "no health check defined" }
```

声明了 `health_check` 时，端点透传插件返回的 dict（约定至少包含 `status` 字段，常见值：
`ok` / `healthy` / `degraded` / `error`）。`health_check` 可以是同步函数直接返回
`dict`，也可以是 `async def`；同步函数返回 coroutine 会被视为声明错误。

#### `POST /api/v1/admin/plugins/{name}/enable`

把插件从禁用列表中移除（重启后生效）。响应：

```json
{ "success": true, "restart_required": true, "message": "插件 'superweb2pdf' 已启用..." }
```

#### `POST /api/v1/admin/plugins/{name}/disable`

把插件加入禁用列表，**并尽力在运行时卸载** adapter / fetch handler 与执行 `on_shutdown`
（异步钩子会被 await）。完整禁用需要重启。

#### `POST /api/v1/admin/plugins/install`

通过 `pip` 安装允许列表中的插件包；需要 `SOUWEN_ENABLE_PLUGIN_INSTALL=1`。
`package` 首尾空白会被清理，清理后为空返回 `422`。该运行时端点只接受允许列表中的
distribution name，不接受 URL、PEP 508 direct reference 或任意 pip 参数。

**请求体 shape（name-only，不是 direct reference）：**
```json
{ "package": "superweb2pdf" }
```

**当前公共索引未提供该 distribution 时的响应：**
```json
{
  "success": false,
  "package": "superweb2pdf",
  "restart_required": false,
  "message": "操作失败，详见服务端日志"
}
```

> 服务端会净化 pip 原始输出，仅返回标准化的 `success` / `message` 字段；详细错误打印到服务端日志。
> 如果未启用，会返回 `success=false` 与说明性 message，HTTP 状态码仍为 200。

> **SuperWeb2PDF 安装边界**：当前 `superweb2pdf` 没有可依赖的 PyPI distribution。
> SouWen 的 `web2pdf` extra 使用固定 commit archive 的 PEP 508 direct reference，
> URL 同时附带 `#sha256=` hash，`pyproject.toml` 声明 Hatch
> `allow-direct-references = true`；Docker 的
> `WEB2PDF_PACKAGE` 使用同一 archive。应在构建镜像、wheel 安装环境或受控 CI 中通过
> `.[web2pdf]` / `.[edition-full]` 安装并验证 entry point、fetch handler 和 Playwright
> runtime。上面的 name-only API 请求只展示允许列表与失败 shape；除非受控 package index
> 真实提供该 distribution，否则不能用它替代 fixed-commit direct-reference 安装，更不能
> 据此证明当前 archive 已安装。

#### `POST /api/v1/admin/plugins/uninstall`

反向操作，请求/响应字段同上。

#### `POST /api/v1/admin/plugins/reload`

重新扫描 `souwen.plugins` entry points，**追加加载**未在禁用列表中的新插件，
不会触碰已加载的旧插件实例。

**响应：**
```json
{
  "loaded": ["superweb2pdf"],
  "errors": [],
  "message": "插件重新扫描完成，新增加载 1 个，错误 0 个。"
}
```

---

### 内容抓取端点 (`/api/v1/fetch`)

受 `require_auth`（管理密码）与 `rate_limit_search` 双重保护。

#### `POST /api/v1/fetch`

抓取网页内容，支持 24 个提供者。默认 `fallback` 按 URL 补抓失败项；`fanout` 会并发返回所有 provider 结果。provider 必须同时存在于 registry 且被当前 `SOUWEN_EDITION` 允许；重运行时 provider（如 `crawl4ai` / `scrapling` / `newspaper` / `readability` / `arxiv_fulltext`）需要 `full`。

**请求体 (JSON)：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `urls` | `list[str]` (1-20) | *(必填)* | 目标 URL 列表 |
| `provider` | `string` | `"builtin"` | 单 provider 请求字段；新代码优先使用 `providers` |
| `providers` | `list[str] \| null` | `null` | 多 provider 列表；提供时优先于 `provider`。可选：`builtin` / `jina_reader` / `arxiv_fulltext` / `tavily` / `firecrawl` / `xcrawl` / `kimi_code` / `exa` / `metaso` / `crawl4ai` / `scrapling` / `scrapfly` / `diffbot` / `scrapingbee` / `zenrows` / `scraperapi` / `apify` / `cloudflare` / `wayback` / `newspaper` / `readability` / `mcp` / `site_crawler` / `deepwiki` |
| `strategy` | `"fallback" \| "fanout"` | `"fallback"` | 多 provider 策略：`fallback` 按 URL 顺序补失败项；`fanout` 返回所有 provider 结果 |
| `timeout` | `float` (1-120) | `30` | 每 URL 超时秒数 |
| `selector` | `string \| null` | `null` | CSS 选择器，仅提取匹配元素（builtin / scrapling 支持） |
| `start_index` | `integer` (≥0) | `0` | 内容起始切片位置 |
| `max_length` | `integer \| null` (≥0) | `null` | 内容最大长度，超出则截断 |
| `respect_robots_txt` | `boolean` | `false` | 是否遵守 robots.txt（provider 支持时生效） |

**请求示例：**
```json
{
  "urls": ["https://example.com/article"],
  "providers": ["builtin", "jina_reader"],
  "strategy": "fallback",
  "timeout": 30
}
```

**响应示例：**
```json
{
  "urls": ["https://example.com/article"],
  "results": [
    {
      "url": "https://example.com/article",
      "final_url": "https://example.com/article",
      "title": "示例文章",
      "content": "# 示例文章\n\n正文内容...",
      "content_format": "markdown",
      "content_truncated": false,
      "next_start_index": null,
      "source": "builtin",
      "snippet": "正文内容...",
      "published_date": "2024-01-01",
      "author": "作者",
      "error": null,
      "raw": {}
    }
  ],
  "total": 1,
  "total_ok": 1,
  "total_failed": 0,
  "provider": null,
  "providers": ["builtin", "jina_reader"],
  "strategy": "fallback",
  "meta": {
    "strategy": "fallback",
    "requested_providers": ["builtin", "jina_reader"],
    "attempted": {
      "https://example.com/article": ["builtin"]
    },
    "selected_provider": {
      "https://example.com/article": "builtin"
    },
    "ssrf_blocked": 0
  }
}
```

`provider` 是响应里的 deprecated 过渡字段；当一次请求涉及多个 provider 时，
请以 `providers`、`meta.selected_provider` 和 `results[].source` 为准。

**错误状态码：** `400`（无效提供者）、`403`（provider 存在但当前 edition 不允许）、`504`（超时）

**安全特性：**
- SSRF 防护：DNS 解析 + 非规范 IPv4 数字写法拒绝 + 私有/保留 IP 拦截
- 重定向安全：每一跳校验目标 IP，防止多跳 SSRF 攻击
- Scrapling 浏览器模式：`dynamic` / `stealthy` 会对 navigation、子资源、XHR/fetch 等浏览器请求安装同一套 SSRF 拦截
- 管理密码认证：需要 `admin_password`

### LLM 摘要端点

下列端点需要当前 `SOUWEN_EDITION` 包含 LLM 能力：`basic` 返回 `403`；`pro` / `full`
才继续检查 `llm.enabled` 和 API Key，未启用或未配置时返回 `503`。`/api/v1/summarize`
受搜索鉴权保护，`/api/v1/fetch/summarize` 同时会触发 fetch 能力并受对应速率限制。

#### `POST /api/v1/summarize`

搜索并生成摘要。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | string (1-500) | *(必填)* | 搜索查询 |
| `domain` | string | `"paper"` | 搜索域：`paper` / `patent` / `web` |
| `sources` | `list[str] \| null` | `null` | 指定数据源 |
| `per_page` | int (1-50) | `10` | 每源结果数 |
| `mode` | `"brief" \| "detailed" \| "academic" \| null` | `null` | 摘要模式；默认使用 `llm.default_mode` |
| `model` | string \| null | `null` | 可选模型覆盖 |
| `max_tokens` | int \| null | `null` | 可选最大 token 数 |
| `temperature` | float \| null | `null` | 可选温度覆盖 |
| `system_prompt` | string \| null | `null` | 自定义系统 prompt |

**错误状态码：** `403`（当前 edition 不包含 LLM）、`503`（LLM 未启用或未配置 API Key）。

#### `POST /api/v1/fetch/summarize`

抓取 URL 页面内容并逐页生成摘要。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `urls` | `list[str]` (1-10) | *(必填)* | 待抓取并摘要的 URL 列表 |
| `provider` | string | `"builtin"` | 单 Fetch 提供者字段；新请求优先使用 `providers` |
| `providers` | `list[str]` \| null | `null` | Fetch 提供者列表；提供时优先于 `provider` |
| `strategy` | `"fallback" \| "fanout"` | `"fallback"` | 多 provider 策略：`fallback` 按 URL 补失败项，`fanout` 返回全部 provider 结果 |
| `timeout` | float (5-120) | `30.0` | 每 URL 超时秒数 |
| `mode` | `"brief" \| "detailed" \| "academic" \| null` | `null` | 摘要模式；默认使用 `llm.default_mode` |
| `model` | string \| null | `null` | 可选模型覆盖 |
| `max_tokens` | int \| null | `null` | 可选最大 token 数 |
| `temperature` | float \| null | `null` | 可选温度覆盖 |
| `system_prompt` | string \| null | `null` | 自定义系统 prompt |

**错误状态码：** `403`（当前 edition 不包含 LLM，或 fetch provider 存在但当前 edition 不允许）、`503`（LLM 未启用或未配置 API Key）、`504`（fetch 超时）。

## MCP 工具

SouWen 支持 [Model Context Protocol](https://modelcontextprotocol.io/)，可作为 AI Agent 的工具服务。

### 启动

```bash
python -m souwen.integrations.mcp_server
```

直接安装 core 时需另行安装 `pip install mcp`；`edition-basic`、`edition-pro` 与
更高 edition 已包含 MCP SDK。

### 工具列表

#### `search_papers`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | string | — | 搜索关键词 |
| `sources` | string \| array | `null`（registry `paper:search` 当前为 `["openalex", "crossref", "arxiv", "dblp", "pubmed", "biorxiv"]`） | 数据源或数据源列表 |
| `limit` | int | `5` | 每源返回数量 |

返回：JSON `SearchResponse` 数组

#### `search_patents`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | string | — | 搜索关键词 |
| `sources` | string \| array | `null`（registry `patent:search` 当前为 `["google_patents"]`） | 数据源或数据源列表 |
| `limit` | int | `5` | 结果数 |

返回：JSON `SearchResponse` 数组

#### `web_search`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | string | — | 搜索关键词 |
| `engines` | string \| array | `null`（registry `web:search` 当前为 `["duckduckgo", "bing"]`） | 引擎或引擎列表 |
| `limit` | int | `10` | 每引擎最大结果数 |

返回：JSON `SearchResponse` 对象

MCP 搜索工具的 `sources` / `engines` 与 Python API 一致。显式请求当前 `SOUWEN_EDITION` 不允许的 source / engine 时，工具调用会返回对应的 edition 错误文本。`fetch_content` 工具的 schema 会按当前 `edition` 只列出可执行的 fetch provider；显式传入当前版本不允许的已知 provider 时同样返回 edition 错误文本。

#### `get_status`

无参数。返回所有数据源的健康状态报告。

#### `fetch_content`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `urls` | string \| array | — | 待抓取的 URL 或 URL 列表 |
| `provider` | string | `"builtin"` | 单内容提取提供者字段；新请求优先使用 `providers`。默认 `builtin`（零配置）。工具 schema 的可选项按当前 `edition` 过滤；例如 `basic` 只列出 `builtin` / `mcp` / `site_crawler`，`pro` 追加 API/远端服务类 provider，`full` 追加 `crawl4ai` / `scrapling` / `newspaper` / `readability` / `arxiv_fulltext` 等重运行时 provider |
| `providers` | string \| array \| null | `null` | 内容提取提供者或提供者列表；提供时优先于 `provider` |
| `strategy` | `"fallback" \| "fanout"` | `"fallback"` | 多 provider 策略：`fallback` 按 URL 补失败项，`fanout` 返回全部 provider 结果 |

返回：JSON `FetchResponse` 对象（含 `results`、`total`、`total_ok`、`total_failed`）。

内置 fetch provider 全量集合（MCP 工具 schema 会再按当前 `edition` 过滤）可选：`builtin` / `jina_reader` / `arxiv_fulltext` / `tavily` / `firecrawl` / `xcrawl` / `kimi_code` / `exa` / `metaso` / `crawl4ai` / `scrapling` / `scrapfly` / `diffbot` / `scrapingbee` / `zenrows` / `scraperapi` / `apify` / `cloudflare` / `wayback` / `newspaper` / `readability` / `mcp` / `site_crawler` / `deepwiki`。

#### `extract_links`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `url` | string | — | 目标页面 URL；会先 `strip()`，strip 后不能为空 |
| `base_url_filter` | string | `null` | URL 前缀过滤；提供时会先 `strip()`，strip 后为空则按未提供处理 |
| `limit` | int | `100` | 最大返回链接数（1-1000） |

返回：JSON `LinksResponse` 对象。

#### `parse_sitemap`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `url` | string | — | Sitemap URL 或站点根 URL；会先 `strip()`，strip 后不能为空 |
| `discover` | bool | `false` | 是否从 robots.txt 自动发现 sitemap |
| `limit` | int | `1000` | 最大返回条目数 |

返回：JSON `SitemapResponse` 对象。

#### Bilibili 工具

| 工具 | 说明 |
|------|------|
| `bilibili_search` | 搜索 Bilibili 视频 |
| `bilibili_search_users` | 按关键词搜索 Bilibili 用户 |
| `bilibili_search_articles` | 按关键词搜索 Bilibili 专栏文章 |
| `bilibili_video_details` | 按 BV 号抓取视频详情 |

MCP server 的 `list_tools` 会返回当前完整工具 schema；插件加载后，
`fetch_content.provider/providers` 的可选 provider 会随 registry 可见源扩展。

---

## 多媒体与扩展端点

下列端点由真实 route 模块接入，统一受 `check_search_auth` + `rate_limit_search` 保护。

### 新闻 / 图片 / 视频

#### `GET /api/v1/search/news`

通过 registry 的 `web:search_news` 默认源派发；内置默认源是 `duckduckgo_news`。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `q` | string (1-500) | *(必填)* | 关键词；会先 `strip()`，strip 后不能为空 |
| `sources` | string \| null | `null` | 新闻搜索源，逗号分隔；默认来自当前 registry 的 `web:search_news` |
| `max_results` | int (1-100) | `20` | 最大结果数 |
| `region` | string | `wt-wt` | 区域（`wt-wt`=全球，`cn-zh`=中国） |
| `safesearch` | string | `moderate` | `on` / `moderate` / `off` |
| `time_range` | string \| null | `null` | 时间范围（`d` / `w` / `m`）；为空表示不限 |
| `timeout` | float (1-120) \| null | `null` | 端点硬超时秒数 |

#### `GET /api/v1/search/images`

通过 registry 的 `web:search_images` 默认源派发；内置默认源是 `duckduckgo_images`。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `q` | string (1-500) | *(必填)* | 关键词；会先 `strip()`，strip 后不能为空 |
| `sources` | string \| null | `null` | 图片搜索源，逗号分隔；默认来自当前 registry 的 `web:search_images` |
| `max_results` | int (1-100) | `20` | 最大结果数 |
| `region` | string | `wt-wt` | 区域（`wt-wt`=全球，`cn-zh`=中国） |
| `safesearch` | string | `moderate` | `on` / `moderate` / `off` |
| `timeout` | float (1-120) \| null | `null` | 端点硬超时秒数 |

#### `GET /api/v1/search/videos`

通过 registry 的 `web:search_videos` 默认源派发；内置默认源是 `duckduckgo_videos`。
参数同 `/search/images`，`sources` 默认来自 `web:search_videos`，返回
`title / duration / publisher / thumbnail / embed_url` 等字段。

### YouTube Data API

需配置 `youtube_api_key`，缺失时返回 `503`。

| 端点 | 主要参数 | 说明 |
|------|----------|------|
| `GET /api/v1/youtube/trending` | `region`, `category`, `max_results` | 按地区/分类拉取热门视频；`region` 会先 `strip()` 并转大写，strip 后不能为空；`category` 会先 `strip()`，strip 后为空则按未提供处理 |
| `GET /api/v1/youtube/video/{video_id}` | `video_id` | 视频详情（含播放/点赞/评论统计）；`video_id` 会先 `strip()`，strip 后不能为空 |
| `GET /api/v1/youtube/transcript/{video_id}` | `lang` | 提取字幕（**零配额**，页面抓取方式）；`video_id` 和 `lang` 会先 `strip()`，strip 后不能为空 |

### Wayback Machine（archive 域）

| 端点 | 认证 | 主要参数 | 说明 |
|------|------|----------|------|
| `GET /api/v1/wayback/cdx` | 访客 | `url`, `from`, `to`, `limit`, `filter_status`, `collapse` | URL 历史快照列表；`url` 会先 `strip()`，strip 后不能为空 |
| `GET /api/v1/wayback/check` | 访客 | `url`, `timestamp` | 快照可用性查询；`url` 会先 `strip()`，strip 后不能为空 |
| `POST /api/v1/admin/wayback/save` | 管理 | `url`, `timeout` | 触发即时存档（IA 全局速率约 15 次/分钟）；请求体 `url` 会先 `strip()`，strip 后不能为空 |

### 链接与 sitemap 工具（fetch 域）

需要管理密码（含 SSRF 风险）。

| 端点 | 主要参数 | 说明 |
|------|----------|------|
| `GET /api/v1/links` | `url`, `base_url`, `limit` (1-1000) | 提取页面 `<a href>` 链接，去重 + SSRF 过滤；`url` 会先 `strip()`，strip 后不能为空 |
| `GET /api/v1/sitemap` | `url`, `discover`, `limit` (1-50000) | 解析 sitemap.xml / sitemap index / gzip；`url` 会先 `strip()`，strip 后不能为空；`discover=true` 时从 robots.txt 自动发现 |

### Bilibili（video / social 域）

`prefix=/api/v1/bilibili`，受访客认证保护。错误码映射：`BilibiliNotFound→404`、`BilibiliAuthRequired→401`、`BilibiliRateLimited→429`、`BilibiliRiskControl→403`、`BilibiliError→502`。

| 端点 | 主要参数 | 说明 |
|------|----------|------|
| `GET /api/v1/bilibili/video/{bvid}` | `bvid` | 视频详情（标题、UP、统计、标签）；`bvid` 会先 `strip()`，strip 后不能为空 |
| `GET /api/v1/bilibili/search` | `keyword`, `max_results` (1-50), `order` | 视频搜索；`keyword` 会先 `strip()`，strip 后不能为空（`order` ∈ totalrank/click/pubdate/dm/stow） |
| `GET /api/v1/bilibili/search/users` | `keyword`, `page`, `max_results` | 用户搜索；`keyword` 会先 `strip()`，strip 后不能为空 |
| `GET /api/v1/bilibili/search/articles` | `keyword`, `page`, `max_results` | 专栏文章搜索；`keyword` 会先 `strip()`，strip 后不能为空 |

### 数据源频道配置（admin）

| 端点 | 说明 |
|------|------|
| `GET /api/v1/admin/sources/config` | 列出所有源的频道配置（`enabled / proxy / http_backend / base_url / timeout / has_api_key / credentials_satisfied / missing_credential_fields / config_valid / config_reason / min_edition / edition_available / edition_reason / headers / params / category / integration_type`，以及 source catalog 字段）；`proxy` / `base_url` 会隐藏 URL userinfo、secret query 和 secret fragment；LLM-search gateway source 不回显 private base URL |
| `GET /api/v1/admin/sources/config/{source_name}` | 单源频道配置；`source_name` 会先 `strip()`，strip 后为空返回 `422`，未知源返回 `404`；`proxy` / `base_url` 同样以脱敏视图返回 |
| `PUT /api/v1/admin/sources/config/{source_name}` | JSON 体更新单源运行时配置（避免 Key 入日志），重启不持久化；`source_name/proxy/http_backend/base_url` 会先 `strip()`，`source_name` strip 后为空返回 `422`；`timeout` 为 `null` 时清除 override，否则必须在 1..300 秒；`proxy` / `base_url` 不接受脱敏占位符 `***`，避免把只读展示值写回真实配置 |
| `GET /api/v1/admin/proxy` / `PUT` | 全局 `proxy` 与 `proxy_pool` 读写（含 SOCKS 依赖检查）；读响应和 `PUT` 成功响应会隐藏 URL userinfo、secret query 和 secret fragment；`proxy` 和 `proxy_pool[]` 会先 `strip()`，`proxy` strip 后为空则清空配置，`proxy_pool[]` strip 后为空返回 `422`，脱敏占位符 `***` 返回 `422` |
| `GET /api/v1/admin/http-backend` / `PUT` | HTTP 后端总览与按源覆盖（`auto`/`curl_cffi`/`httpx`）；`PUT` 的 `default/source/backend` 会先 `strip()`，`source` 和 `backend` 必须同时提供 |

请求体示例（`PUT /api/v1/admin/sources/config/duckduckgo`）：

```json
{
  "enabled": true,
  "proxy": "warp",
  "http_backend": "curl_cffi",
  "timeout": 15
}
```

单源配置响应会额外包含：

| 字段 | 说明 |
|---|---|
| `has_api_key` | 是否显式配置了该源声明的凭据字段；免配置源为 `false`，表示没有 Key，而不是不可用 |
| `credentials_satisfied` | 该源运行所需凭据是否满足；`auth_requirement="none"` / `optional` 源通常为 `true` |
| `missing_credential_fields` | 当前缺失或无效的配置字段路径；不包含配置值 |
| `config_valid` / `config_reason` | 静态 source 配置是否合法；原因只包含字段路径，不包含提交值 |
| `min_edition` / `edition_available` / `edition_reason` | 当前 `SOUWEN_EDITION` 是否允许该源；管理端仍返回全部源，不按 edition 隐藏 |
| `proxy` / `base_url` | 配置视图会隐藏 URL userinfo、secret query 和 secret fragment；这些脱敏显示值只用于读取，不能原样提交回 `PUT` |
| `timeout` | 可选 provider-attempt timeout override；`null` 表示未覆盖，普通 web source 仍受 15 秒 cap |
| `headers` / `params` | 频道级附加配置视图；字段名包含 key/token/secret/password/auth/authorization/cookie/sessdata/session/sid/jwt/csrf/xsrf 等敏感含义时值会显示为 `***`，覆盖 snake_case、hyphen-case、camelCase 和常见 compact 写法 |
| `auth_requirement` / `key_requirement` | `none` / `optional` / `required` / `self_hosted` |
| `credential_fields` | 完整凭据字段列表 |
| `risk_level` / `risk_reasons` | 风险等级和原因 |
| `distribution` / `package_extra` | 推荐安装/治理边界 |
| `stability` | Registry 声明的接入成熟度，不是 live probe 或实时可用性 |
| `usage_note` | 用户级提示文案,Panel / CLI 作为状态消息后缀展示;不参与可用性判定 |

> 完整字段语义见 [configuration.md](./configuration.md#数据源频道配置sources)。
